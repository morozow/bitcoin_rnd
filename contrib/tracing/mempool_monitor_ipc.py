#!/usr/bin/env python3
# Copyright (c) 2022-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
IPC-based mempool monitor — same logic as mempool_monitor.py but receives
events via stdin (NDJSON) instead of eBPF/USDT tracepoints.

This is a stdio_bus worker: it reads JSON events from stdin and processes
them identically to how mempool_monitor.py processes eBPF events.

No root required. No BCC dependency. Works on Linux/macOS/Windows.
"""

import json
import sys
import time
from datetime import datetime, timezone


class MempoolStats:
    """Same metrics as mempool_monitor.py Dashboard.calculate_metrics()"""

    def __init__(self):
        self.counts = {"added": 0, "removed": 0, "rejected": 0, "replaced": 0}
        self.timestamps = {"added": [], "removed": [], "rejected": [], "replaced": []}
        self.start_time = time.monotonic()

    def record(self, event_type):
        if event_type in self.counts:
            self.counts[event_type] += 1
            self.timestamps[event_type].append(time.monotonic())

    def rate(self, event_type, window_sec=60):
        now = time.monotonic()
        recent = [t for t in self.timestamps[event_type] if now - t < window_sec]
        elapsed = min(window_sec, now - self.start_time)
        return len(recent) / elapsed if elapsed > 0 else 0

    def summary(self):
        runtime = time.monotonic() - self.start_time
        return {
            "runtime_s": round(runtime, 2),
            "counts": dict(self.counts),
            "rates_1m": {k: round(self.rate(k, 60), 2) for k in self.counts},
        }


def process_event(line, stats):
    """Process a single NDJSON event line — same data as eBPF tracepoints provide."""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return

    method = event.get("method", "")

    # Map our event methods to mempool_monitor event types
    if method == "mempool.tx_admission":
        params = event.get("params", {})
        if params.get("accepted", False):
            stats.record("added")
        else:
            stats.record("rejected")
    elif method == "mempool.tx_removed":
        stats.record("removed")
    elif method == "mempool.tx_replaced":
        stats.record("replaced")
    elif method == "block.validated":
        # Block events trigger batch removals — track for context
        pass


def main():
    stats = MempoolStats()
    event_count = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        process_event(line, stats)
        event_count += 1

        # Periodic summary to stderr (same as mempool_monitor curses refresh)
        if event_count % 100 == 0:
            s = stats.summary()
            print(
                f"[mempool_ipc] events={event_count} "
                f"added={s['counts']['added']} "
                f"rejected={s['counts']['rejected']} "
                f"rate={s['rates_1m']['added']:.1f}tx/s",
                file=sys.stderr,
            )

    # Final summary
    s = stats.summary()
    print(json.dumps(s), file=sys.stderr)


if __name__ == "__main__":
    main()
