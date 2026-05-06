#!/usr/bin/env python3
# Copyright (c) 2022-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
IPC-based P2P traffic monitor — equivalent to log_p2p_traffic.bt and p2p_monitor.py.
Receives net:inbound_message / net:outbound_message events via stdin NDJSON.

Tracks: peer_id, msg_type, msg_size, direction, rates per message type.
"""

import json
import sys
import time
from collections import defaultdict


class P2PTrafficStats:
    def __init__(self):
        self.msg_counts = defaultdict(int)  # msg_type -> count
        self.msg_bytes = defaultdict(int)   # msg_type -> total bytes
        self.peer_msgs = defaultdict(int)   # peer_id -> count
        self.total_inbound = 0
        self.total_outbound = 0
        self.total_bytes = 0
        self.start_time = time.monotonic()

    def record(self, peer_id, msg_type, size_bytes, direction="inbound"):
        self.msg_counts[msg_type] += 1
        self.msg_bytes[msg_type] += size_bytes
        self.peer_msgs[peer_id] += 1
        self.total_bytes += size_bytes
        if direction == "inbound":
            self.total_inbound += 1
        else:
            self.total_outbound += 1

    def summary(self):
        runtime = time.monotonic() - self.start_time
        total = self.total_inbound + self.total_outbound
        return {
            "runtime_s": round(runtime, 2),
            "total_messages": total,
            "inbound": self.total_inbound,
            "outbound": self.total_outbound,
            "total_bytes": self.total_bytes,
            "msg_rate": round(total / runtime, 2) if runtime > 0 else 0,
            "top_msg_types": dict(sorted(self.msg_counts.items(), key=lambda x: -x[1])[:10]),
            "peers_seen": len(self.peer_msgs),
        }


def main():
    stats = P2PTrafficStats()
    event_count = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = event.get("method", "")
        params = event.get("params", {})

        if method == "net.message_received":
            stats.record(
                peer_id=params.get("peer_id", 0),
                msg_type=params.get("msg_type", "unknown"),
                size_bytes=params.get("size_bytes", 0),
                direction="inbound",
            )
            event_count += 1
        elif method == "net.message_sent":
            stats.record(
                peer_id=params.get("peer_id", 0),
                msg_type=params.get("msg_type", "unknown"),
                size_bytes=params.get("size_bytes", 0),
                direction="outbound",
            )
            event_count += 1

        if event_count > 0 and event_count % 500 == 0:
            s = stats.summary()
            print(
                f"[p2p_traffic] msgs={s['total_messages']} "
                f"in={s['inbound']} out={s['outbound']} "
                f"rate={s['msg_rate']:.1f}msg/s "
                f"peers={s['peers_seen']}",
                file=sys.stderr,
            )

    s = stats.summary()
    print(json.dumps(s, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
