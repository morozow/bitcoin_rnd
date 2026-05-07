#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
IPC-based P2P connection monitor — equivalent to log_p2p_connections.bt.

Receives the following events via stdin NDJSON (one JSON-RPC envelope per line):

  net:inbound_connection          ->  type="peer_connection", inbound=true
  net:outbound_connection         ->  type="peer_connection", inbound=false
  net:closed_connection           ->  type="peer_closed"
  net:evicted_inbound_connection  ->  type="peer_evicted"
  net:misbehaving_connection      ->  type="peer_misbehaving"

For each event we print a human-readable line on stdout (so it can be diffed
against log_p2p_connections.bt output) and also write a structured CSV row to
stderr / --csv for later latency analysis.

USAGE (stdio_bus worker):
  echo '<ndjson>' | ./p2p_connections.py
  ./p2p_connections.py --csv /tmp/ipc_p2p.csv

Event envelope format produced by StdioBusSdkHooks::SerializeEvent():
  {"jsonrpc":"2.0","method":"stdio_bus.event","params":{"type":"peer_closed",...}}
"""

import argparse
import csv
import json
import sys
import time


CSV_FIELDS = [
    "tracepoint", "event_id", "core_ts_us", "ipc_worker_ts_us",
    "ipc_latency_us", "extra",
]


def _get_type(event):
    """Extract event type regardless of routing transformations."""
    method = event.get("method", "") or ""
    params = event.get("params", {}) or {}
    t = params.get("type")
    if t:
        return t, params
    # fallback: method name like "net.inbound_connection"
    return method, params


def _tracepoint_for(event_type):
    return {
        "peer_connection": "net:inbound_connection/net:outbound_connection",
        "peer_closed": "net:closed_connection",
        "peer_evicted": "net:evicted_inbound_connection",
        "peer_misbehaving": "net:misbehaving_connection",
    }.get(event_type, event_type)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=str, default=None,
                    help="Write structured CSV of event timings here.")
    args = ap.parse_args()

    csv_writer = None
    csv_file = None
    if args.csv:
        csv_file = open(args.csv, "w", newline="")
        csv_writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        csv_writer.writeheader()

    counts = {"inbound": 0, "outbound": 0, "closed": 0, "evicted": 0, "misbehaving": 0}

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type, params = _get_type(event)
        ipc_now_us = int(time.monotonic() * 1_000_000)
        core_ts = int(params.get("timestamp_us") or 0)
        ipc_latency = (ipc_now_us - core_ts) if core_ts else 0

        event_id = ""
        human = None

        if event_type == "peer_connection":
            inbound = bool(params.get("inbound", False))
            key = "inbound" if inbound else "outbound"
            counts[key] += 1
            event_id = f"peer={params.get('peer_id')}"
            human = (
                f"{'INBOUND' if inbound else 'OUTBOUND'} conn "
                f"{'from' if inbound else 'to'} {params.get('addr','?')}: "
                f"id={params.get('peer_id')}, type={params.get('conn_type')}, "
                f"network={params.get('network')}, "
                f"total={params.get('existing_connections')}"
            )
        elif event_type == "peer_closed":
            counts["closed"] += 1
            event_id = f"peer={params.get('peer_id')}"
            human = (
                f"CLOSED conn to {params.get('addr','?')}: "
                f"id={params.get('peer_id')}, type={params.get('conn_type')}, "
                f"network={params.get('network')}, "
                f"established={params.get('time_established')}"
            )
        elif event_type == "peer_evicted":
            counts["evicted"] += 1
            event_id = f"peer={params.get('peer_id')}"
            human = (
                f"EVICTED conn to {params.get('addr','?')}: "
                f"id={params.get('peer_id')}, type={params.get('conn_type')}, "
                f"network={params.get('network')}, "
                f"established={params.get('time_established')}"
            )
        elif event_type == "peer_misbehaving":
            counts["misbehaving"] += 1
            event_id = f"peer={params.get('peer_id')}"
            human = (
                f"MISBEHAVING conn id={params.get('peer_id')}, "
                f"message='{params.get('message','')}'"
            )

        if human:
            print(human)
            sys.stdout.flush()

        if csv_writer and human:
            csv_writer.writerow({
                "tracepoint": _tracepoint_for(event_type),
                "event_id": event_id,
                "core_ts_us": core_ts,
                "ipc_worker_ts_us": ipc_now_us,
                "ipc_latency_us": ipc_latency,
                "extra": json.dumps({
                    "conn_type": params.get("conn_type"),
                    "network": params.get("network"),
                }, separators=(",", ":")),
            })

    if csv_file:
        csv_file.close()

    print(json.dumps(counts), file=sys.stderr)


if __name__ == "__main__":
    main()
