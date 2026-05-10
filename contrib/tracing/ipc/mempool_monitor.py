#!/usr/bin/env python3
# Copyright (c) 2022-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
IPC-based mempool monitor — 1:1 equivalent of contrib/tracing/mempool_monitor.py.

Reads one JSON-RPC envelope per line from stdin, as produced by
StdioBusSdkHooks::SerializeEvent():

    {"jsonrpc":"2.0","method":"stdio_bus.event",
     "params":{"type":"mempool_added",...}}

Covers the same four USDT tracepoints:

    mempool:added     -> params.type == "mempool_added"
    mempool:removed   -> params.type == "tx_removed"
    mempool:replaced  -> params.type == "tx_replaced"
    mempool:rejected  -> params.type == "tx_rejected"

Keeps the exact same metrics as the eBPF version: count (total / 1m / 10m),
rate (total / 1m / 10m), sliding 10-minute timestamp windows per event type,
and per-event human-readable log line with feerate in sat/vB, including
"received N.N seconds ago" for removed/replaced events.

If a TTY is attached and --no-curses is not passed, a ncurses dashboard
identical to the eBPF script is drawn. Otherwise the script emits NDJSON
summaries on stderr and human-readable event lines on stdout — so it works
both as a stdio_bus worker and as a standalone CLI tool.

USAGE:
    cat events.ndjson | ./mempool_monitor.py --no-curses
    ./mempool_monitor.py                       # interactive dashboard (tty)
"""

import argparse
import curses
import json
import os
import sys
import threading
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Event parsing (1:1 with eBPF struct fields)
# ---------------------------------------------------------------------------

class AddedEvent:
    __slots__ = ("hash", "vsize", "fee")

    def __init__(self, hash_, vsize, fee):
        self.hash = hash_
        self.vsize = vsize
        self.fee = fee


class RemovedEvent:
    __slots__ = ("hash", "reason", "vsize", "fee", "entry_time")

    def __init__(self, hash_, reason, vsize, fee, entry_time):
        self.hash = hash_
        self.reason = reason
        self.vsize = vsize
        self.fee = fee
        self.entry_time = entry_time


class RejectedEvent:
    __slots__ = ("hash", "reason")

    def __init__(self, hash_, reason):
        self.hash = hash_
        self.reason = reason


class ReplacedEvent:
    __slots__ = (
        "replaced_hash", "replaced_vsize", "replaced_fee",
        "replaced_entry_time",
        "replacement_hash", "replacement_vsize", "replacement_fee",
    )

    def __init__(self, replaced_hash, replaced_vsize, replaced_fee,
                 replaced_entry_time,
                 replacement_hash, replacement_vsize, replacement_fee):
        self.replaced_hash = replaced_hash
        self.replaced_vsize = replaced_vsize
        self.replaced_fee = replaced_fee
        self.replaced_entry_time = replaced_entry_time
        self.replacement_hash = replacement_hash
        self.replacement_vsize = replacement_vsize
        self.replacement_fee = replacement_fee


def _parse(line):
    """Parse a single NDJSON line into (ts, type_str, event_obj) or None."""
    try:
        env = json.loads(line)
    except json.JSONDecodeError:
        return None
    params = env.get("params") or {}
    etype = params.get("type") or env.get("method", "")
    ts = datetime.now(timezone.utc)

    if etype == "mempool_added":
        return ts, "added", AddedEvent(
            hash_=params.get("txid", ""),
            vsize=int(params.get("vsize", 0)),
            fee=int(params.get("fee", 0)),
        )
    if etype == "tx_removed":
        return ts, "removed", RemovedEvent(
            hash_=params.get("txid", ""),
            reason=params.get("reason", "unknown"),
            vsize=int(params.get("vsize", 0)),
            fee=int(params.get("fee", 0)),
            entry_time=int(params.get("entry_time", 0)),
        )
    if etype == "tx_rejected":
        return ts, "rejected", RejectedEvent(
            hash_=params.get("txid", ""),
            reason=params.get("reason", "unknown"),
        )
    if etype == "tx_replaced":
        return ts, "replaced", ReplacedEvent(
            replaced_hash=params.get("replaced_txid", ""),
            replaced_vsize=int(params.get("replaced_vsize", 0)),
            replaced_fee=int(params.get("replaced_fee", 0)),
            replaced_entry_time=0,  # not exposed on replacement mirror (RBF-site emits it)
            replacement_hash=params.get("replacement_txid", ""),
            replacement_vsize=int(params.get("replacement_vsize", 0)),
            replacement_fee=int(params.get("replacement_fee", 0)),
        )
    return None


# ---------------------------------------------------------------------------
# Dashboard (ported 1:1 from contrib/tracing/mempool_monitor.py)
# ---------------------------------------------------------------------------

class Dashboard:
    INFO_WIN_HEIGHT = 2
    EVENT_WIN_HEIGHT = 7

    def __init__(self, screen):
        screen.nodelay(True)
        curses.curs_set(False)
        self._screen = screen
        self._time_started = datetime.now(timezone.utc)
        self._timestamps = {"added": [], "removed": [], "rejected": [], "replaced": []}
        self._event_history = {"added": 0, "removed": 0, "rejected": 0, "replaced": 0}
        self._init_windows()

    @staticmethod
    def timestamp_age(timestamp):
        return (datetime.now(timezone.utc) - timestamp).total_seconds()

    def _init_windows(self):
        self._init_info_win()
        self._init_event_count_win()
        self._init_event_rate_win()
        self._init_event_log_win()

    @staticmethod
    def create_win(x, y, height, width, title=None):
        win = curses.newwin(height, width, x, y)
        if title:
            win.box()
            win.addstr(0, 2, title, curses.A_BOLD)
        return win

    def _init_info_win(self):
        self._info_win = Dashboard.create_win(0, 1, self.INFO_WIN_HEIGHT, 30)
        self._info_win.addstr(0, 0, "Mempool Monitor (IPC)", curses.A_REVERSE)
        self._info_win.addstr(1, 0, "Press CTRL-C to stop.", curses.A_NORMAL)
        self._info_win.refresh()

    def _init_event_count_win(self):
        self._event_count_win = Dashboard.create_win(
            3, 1, self.EVENT_WIN_HEIGHT, 37, title="Event count"
        )
        header = " {:<8} {:>8} {:>7} {:>7} "
        self._event_count_win.addstr(
            1, 1, header.format("Event", "total", "1 min", "10 min"), curses.A_UNDERLINE
        )
        self._event_count_win.refresh()

    def _init_event_rate_win(self):
        self._event_rate_win = Dashboard.create_win(
            3, 40, self.EVENT_WIN_HEIGHT, 42, title="Event rate"
        )
        header = " {:<8} {:>9} {:>9} {:>9} "
        self._event_rate_win.addstr(
            1, 1, header.format("Event", "total", "1 min", "10 min"), curses.A_UNDERLINE
        )
        self._event_rate_win.refresh()

    def _init_event_log_win(self):
        num_rows, num_cols = self._screen.getmaxyx()
        space_above = self.INFO_WIN_HEIGHT + 1 + self.EVENT_WIN_HEIGHT + 1
        box_win_height = max(5, num_rows - space_above)
        box_win_width = max(40, num_cols - 2)
        win_box = Dashboard.create_win(
            space_above, 1, box_win_height, box_win_width, title="Event log"
        )
        log_lines = box_win_height - 2
        log_line_len = box_win_width - 2 - 1
        win = win_box.derwin(log_lines, log_line_len, 1, 2)
        win.idlok(True)
        win.scrollok(True)
        win_box.refresh()
        win.refresh()
        self._event_log_win_box = win_box
        self._event_log_win = win

    def calculate_metrics(self, events):
        count, rate = {}, {}
        for event_ts, event_type, event_data in events:
            self._timestamps[event_type].append(event_ts)
        for event_type, ts in self._timestamps.items():
            self._event_history[event_type] += len(
                [t for t in ts if Dashboard.timestamp_age(t) >= 600]
            )
            ts = [t for t in ts if Dashboard.timestamp_age(t) < 600]
            self._timestamps[event_type] = ts
            count_1m = len([t for t in ts if Dashboard.timestamp_age(t) < 60])
            count_10m = len(ts)
            count_total = self._event_history[event_type] + len(ts)
            count[event_type] = (count_total, count_1m, count_10m)
            runtime = max(1.0, Dashboard.timestamp_age(self._time_started))
            rate_1m = count_1m / min(60, runtime)
            rate_10m = count_10m / min(600, runtime)
            rate_total = count_total / runtime
            rate[event_type] = (rate_total, rate_1m, rate_10m)
        return count, rate

    def _update_event_count(self, count):
        w = self._event_count_win
        row_format = " {:<8} {:>6}tx {:>5}tx {:>5}tx "
        for line, metric in enumerate(["added", "removed", "replaced", "rejected"]):
            w.addstr(2 + line, 1, row_format.format(metric, *count[metric]))
        w.refresh()

    def _update_event_rate(self, rate):
        w = self._event_rate_win
        row_format = " {:<8} {:>5.1f}tx/s {:>5.1f}tx/s {:>5.1f}tx/s "
        for line, metric in enumerate(["added", "removed", "replaced", "rejected"]):
            w.addstr(2 + line, 1, row_format.format(metric, *rate[metric]))
        w.refresh()

    def _update_event_log(self, events):
        w = self._event_log_win
        for event in events:
            w.addstr(Dashboard.parse_event(event) + "\n")
        w.refresh()

    def render(self, events):
        count, rate = self.calculate_metrics(events)
        self._update_event_count(count)
        self._update_event_rate(rate)
        self._update_event_log(events)
        events.clear()

    @staticmethod
    def parse_event(event):
        ts_dt, type_, data = event
        ts = ts_dt.strftime("%H:%M:%SZ")
        if type_ == "added":
            fr = (data.fee / data.vsize) if data.vsize else 0
            return (
                f"{ts} added {data.hash}"
                f" with feerate {fr:.2f} sat/vB"
                f" ({data.fee} sat, {data.vsize} vbytes)"
            )
        if type_ == "removed":
            fr = (data.fee / data.vsize) if data.vsize else 0
            age = (ts_dt.timestamp() - data.entry_time) if data.entry_time else 0.0
            return (
                f"{ts} removed {data.hash}"
                f" with feerate {fr:.2f} sat/vB"
                f" ({data.fee} sat, {data.vsize} vbytes)"
                f" received {age:.1f} seconds ago"
                f": {data.reason}"
            )
        if type_ == "rejected":
            return f"{ts} rejected {data.hash}: {data.reason}"
        if type_ == "replaced":
            fr_old = (data.replaced_fee / data.replaced_vsize) if data.replaced_vsize else 0
            fr_new = (data.replacement_fee / data.replacement_vsize) if data.replacement_vsize else 0
            age = (ts_dt.timestamp() - data.replaced_entry_time) if data.replaced_entry_time else 0.0
            return (
                f"{ts} replaced {data.replaced_hash}"
                f" with feerate {fr_old:.2f} sat/vB"
                f" received {age:.1f} seconds ago"
                f" ({data.replaced_fee} sat, {data.replaced_vsize} vbytes)"
                f" with {data.replacement_hash}"
                f" with feerate {fr_new:.2f} sat/vB"
                f" ({data.replacement_fee} sat, {data.replacement_vsize} vbytes)"
            )
        return f"{ts} {type_}"


# ---------------------------------------------------------------------------
# Non-interactive (worker) mode
# ---------------------------------------------------------------------------

def _run_worker(in_stream):
    counts = {"added": 0, "removed": 0, "rejected": 0, "replaced": 0}
    for line in in_stream:
        line = line.strip()
        if not line:
            continue
        parsed = _parse(line)
        if not parsed:
            continue
        ts, etype, data = parsed
        counts[etype] += 1
        print(Dashboard.parse_event((ts, etype, data)))
        sys.stdout.flush()
        if sum(counts.values()) % 100 == 0:
            print(
                f"[mempool_ipc] added={counts['added']} "
                f"removed={counts['removed']} "
                f"replaced={counts['replaced']} "
                f"rejected={counts['rejected']}",
                file=sys.stderr,
                flush=True,
            )
    print(json.dumps(counts), file=sys.stderr)


# ---------------------------------------------------------------------------
# Interactive (curses) mode
# ---------------------------------------------------------------------------

def _run_curses(stdscr):
    events = []
    dashboard = Dashboard(stdscr)

    def reader():
        for line in sys.stdin:
            parsed = _parse(line.strip())
            if parsed:
                events.append(parsed)

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    while True:
        try:
            curses.napms(50)
            dashboard.render(events)
        except KeyboardInterrupt:
            return


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-curses", action="store_true",
                    help="Disable the ncurses dashboard and run as a plain stdio_bus worker.")
    args = ap.parse_args()

    use_curses = (not args.no_curses) and sys.stdout.isatty() and os.isatty(sys.stdin.fileno() if sys.stdin.isatty() else -1)

    if use_curses:
        curses.wrapper(_run_curses)
    else:
        _run_worker(sys.stdin)


if __name__ == "__main__":
    main()
