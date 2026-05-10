#!/usr/bin/env python3
# Copyright (c) 2021-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
IPC-based P2P traffic monitor — 1:1 equivalent of both
contrib/tracing/log_p2p_traffic.bt (simple text logger) and
contrib/tracing/p2p_monitor.py (interactive ncurses dashboard).

Reads NDJSON from stdin, parsing events emitted by StdioBusSdkHooks:

    net:inbound_message   -> params.type == "message"
    net:outbound_message  -> params.type == "outbound_message"

Fields captured 1:1 with USDT (peer_id, addr, conn_type, msg_type, size_bytes)
for both directions. Per-peer last-25-message history and in/out totals are
kept exactly as in p2p_monitor.py.

Two modes:
    * --log    plain text output, 1:1 with log_p2p_traffic.bt
    * default  ncurses Peer list + selectable per-peer message window
               (1:1 with p2p_monitor.py, minus the BCC-specific init)

USAGE:
    ./p2p_traffic.py --log                 # log mode (diff-able with .bt)
    ./p2p_traffic.py                       # interactive dashboard (tty)
    ./p2p_traffic.py --log --no-stdout     # send to stderr only (worker mode)
"""

import argparse
import curses
import json
import os
import sys
import threading
from curses import panel


# ---------------------------------------------------------------------------
# Data model (1:1 with p2p_monitor.py)
# ---------------------------------------------------------------------------

class Message:
    __slots__ = ("msg_type", "size", "inbound")

    def __init__(self, msg_type, size, inbound):
        self.msg_type = msg_type
        self.size = size
        self.inbound = inbound


class Peer:
    def __init__(self, peer_id, address, connection_type):
        self.id = peer_id
        self.address = address
        self.connection_type = connection_type
        self.last_messages = []
        self.total_inbound_msgs = 0
        self.total_inbound_bytes = 0
        self.total_outbound_msgs = 0
        self.total_outbound_bytes = 0

    def add_message(self, message):
        self.last_messages.append(message)
        if len(self.last_messages) > 25:
            self.last_messages.pop(0)
        if message.inbound:
            self.total_inbound_bytes += message.size
            self.total_inbound_msgs += 1
        else:
            self.total_outbound_bytes += message.size
            self.total_outbound_msgs += 1


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse(line):
    """Return (peer_id, addr, conn_type, msg_type, size, inbound) or None."""
    try:
        env = json.loads(line)
    except json.JSONDecodeError:
        return None
    params = env.get("params") or {}
    etype = params.get("type") or env.get("method", "")
    if etype == "message":
        return (
            int(params.get("peer_id", 0)),
            str(params.get("addr", "")),
            str(params.get("conn_type", "")),
            str(params.get("msg_type", "")),
            int(params.get("size_bytes", 0)),
            True,
        )
    if etype == "outbound_message":
        return (
            int(params.get("peer_id", 0)),
            str(params.get("addr", "")),
            str(params.get("conn_type", "")),
            str(params.get("msg_type", "")),
            int(params.get("size_bytes", 0)),
            False,
        )
    return None


# ---------------------------------------------------------------------------
# Log mode (1:1 with log_p2p_traffic.bt)
# ---------------------------------------------------------------------------

def _run_log(in_stream, suppress_stdout):
    sink = sys.stderr if suppress_stdout else sys.stdout
    counts = {"inbound": 0, "outbound": 0}
    for line in in_stream:
        line = line.strip()
        if not line:
            continue
        parsed = _parse(line)
        if not parsed:
            continue
        peer_id, addr, conn_type, msg_type, size, inbound = parsed
        if inbound:
            print(
                f"inbound '{msg_type}' msg from peer {peer_id} ({conn_type}, {addr}) "
                f"with {size} bytes",
                file=sink,
                flush=True,
            )
            counts["inbound"] += 1
        else:
            print(
                f"outbound '{msg_type}' msg to peer {peer_id} ({conn_type}, {addr}) "
                f"with {size} bytes",
                file=sink,
                flush=True,
            )
            counts["outbound"] += 1
    print(json.dumps(counts), file=sys.stderr)


# ---------------------------------------------------------------------------
# Curses mode (ported from p2p_monitor.py.loop/.render)
# ---------------------------------------------------------------------------

def _run_curses(stdscr):
    peers = {}

    def reader():
        for line in sys.stdin:
            parsed = _parse(line.strip())
            if not parsed:
                continue
            peer_id, addr, conn_type, msg_type, size, inbound = parsed
            if peer_id not in peers:
                peers[peer_id] = Peer(peer_id, addr, conn_type)
            peers[peer_id].add_message(Message(msg_type, size, inbound))

    threading.Thread(target=reader, daemon=True).start()

    stdscr.nodelay(1)
    cur_list_pos = 0
    win = curses.newwin(30, 70, 2, 7)
    win.erase()
    win.border(ord("|"), ord("|"), ord("-"), ord("-"),
               ord("-"), ord("-"), ord("-"), ord("-"))
    info_panel = panel.new_panel(win)
    info_panel.hide()

    ROWS_AVAILABLE_FOR_LIST = curses.LINES - 5
    scroll = 0

    while True:
        try:
            curses.napms(50)
            ch = stdscr.getch()
            peer_ids_sorted = sorted(peers.keys())
            if (ch == curses.KEY_DOWN or ch == ord("j")) and \
                    cur_list_pos < max(0, len(peer_ids_sorted) - 1) and info_panel.hidden():
                cur_list_pos += 1
                if cur_list_pos >= ROWS_AVAILABLE_FOR_LIST:
                    scroll += 1
            if (ch == curses.KEY_UP or ch == ord("k")) and cur_list_pos > 0 and info_panel.hidden():
                cur_list_pos -= 1
                if scroll > 0:
                    scroll -= 1
            if ch == ord('\n') or ch == ord(' '):
                if info_panel.hidden():
                    info_panel.show()
                else:
                    info_panel.hide()
            stdscr.erase()
            _render(stdscr, peers, cur_list_pos, scroll, ROWS_AVAILABLE_FOR_LIST, info_panel)
            panel.update_panels()
            stdscr.refresh()
        except KeyboardInterrupt:
            return


def _render(screen, peers, cur_list_pos, scroll, rows_available, info_panel):
    header_format = "%6s  %-20s  %-20s  %-22s  %-67s"
    row_format = "%6s  %-5d %9d byte  %-5d %9d byte  %-22s  %-67s"

    screen.addstr(0, 1, " P2P Message Monitor (IPC) ", curses.A_REVERSE)
    screen.addstr(1, 0,
                  " Navigate with UP/DOWN or J/K and select a peer with ENTER or SPACE",
                  curses.A_NORMAL)
    screen.addstr(3, 0,
                  header_format % ("PEER", "OUTBOUND", "INBOUND", "TYPE", "ADDR"),
                  curses.A_BOLD | curses.A_UNDERLINE)
    peer_list = sorted(peers.keys())[scroll:rows_available + scroll]
    for i, peer_id in enumerate(peer_list):
        peer = peers[peer_id]
        screen.addstr(i + 4, 0,
                      row_format % (peer.id, peer.total_outbound_msgs, peer.total_outbound_bytes,
                                    peer.total_inbound_msgs, peer.total_inbound_bytes,
                                    peer.connection_type, peer.address),
                      curses.A_REVERSE if i + scroll == cur_list_pos else curses.A_NORMAL)
        if i + scroll == cur_list_pos:
            info_window = info_panel.window()
            info_window.erase()
            info_window.border(ord("|"), ord("|"), ord("-"), ord("-"),
                               ord("-"), ord("-"), ord("-"), ord("-"))
            info_window.addstr(
                1, 1, f"PEER {peer.id} ({peer.address})".center(68),
                curses.A_REVERSE | curses.A_BOLD,
            )
            info_window.addstr(
                2, 1, f" OUR NODE{peer.connection_type:^54}PEER ",
                curses.A_BOLD,
            )
            for j, msg in enumerate(peer.last_messages):
                if msg.inbound:
                    info_window.addstr(
                        j + 3, 1,
                        "%68s" % f"<--- {msg.msg_type} ({msg.size} bytes) ",
                        curses.A_NORMAL,
                    )
                else:
                    info_window.addstr(
                        j + 3, 1,
                        f" {msg.msg_type} ({msg.size} byte) --->",
                        curses.A_NORMAL,
                    )


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", action="store_true",
                    help="Plain text mode (1:1 with log_p2p_traffic.bt).")
    ap.add_argument("--no-stdout", action="store_true",
                    help="In --log mode, write to stderr only (worker mode).")
    args = ap.parse_args()

    # Log mode chosen explicitly OR stdin is a pipe (typical worker case).
    if args.log or not sys.stdin.isatty():
        _run_log(sys.stdin, suppress_stdout=args.no_stdout)
        return

    curses.wrapper(_run_curses)


if __name__ == "__main__":
    main()
