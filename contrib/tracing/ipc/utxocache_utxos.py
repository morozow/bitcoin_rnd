#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
IPC-based UTXO set monitor — equivalent to log_utxos.bt.

Receives the following events via stdin NDJSON:

  utxocache:add      ->  type="utxocache_add"
  utxocache:spent    ->  type="utxocache_spent"
  utxocache:uncache  ->  type="utxocache_uncache"

This script is deliberately minimal because utxocache:* is a hot-path
tracepoint (fires on every input/output). It counts events per type and
optionally emits a CSV row per event for later latency analysis.

USAGE:
  ./utxocache_utxos.py
  ./utxocache_utxos.py --csv /tmp/ipc_utxocache.csv --verbose
"""

import argparse
import csv
import json
import sys
import time


CSV_FIELDS = [
    "tracepoint", "event_id", "core_ts_us", "ipc_worker_ts_us",
    "ipc_latency_us", "value", "height", "is_coinbase",
]

TRACEPOINT_MAP = {
    "utxocache_add": "utxocache:add",
    "utxocache_spent": "utxocache:spent",
    "utxocache_uncache": "utxocache:uncache",
}

OP_NAMES = {
    "utxocache_add": "Added",
    "utxocache_spent": "Spent",
    "utxocache_uncache": "Uncache",
}


def _type_of(event):
    params = event.get("params", {}) or {}
    t = params.get("type") or event.get("method", "")
    return t, params


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None, help="Write CSV row per event here.")
    ap.add_argument("--verbose", action="store_true",
                    help="Print one human-readable line per event (like log_utxos.bt).")
    args = ap.parse_args()

    counts = {k: 0 for k in TRACEPOINT_MAP}
    latencies = {k: [] for k in TRACEPOINT_MAP}

    csv_file = None
    csv_writer = None
    if args.csv:
        csv_file = open(args.csv, "w", newline="")
        csv_writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        csv_writer.writeheader()

    if args.verbose:
        # Header mirrors the bpftrace output format: "%-7s %-71s %16s %7s %8s".
        print("%-7s %-71s %16s %7s %8s" % (
            "OP", "Outpoint", "Value", "Height", "Coinbase"
        ))

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type, params = _type_of(event)
        if event_type not in TRACEPOINT_MAP:
            continue

        counts[event_type] += 1
        core_ts = int(params.get("timestamp_us") or 0)
        ipc_now = int(time.monotonic() * 1_000_000)
        ipc_latency = (ipc_now - core_ts) if core_ts else 0
        if ipc_latency > 0:
            latencies[event_type].append(ipc_latency)

        txid = params.get("txid", "")
        vout = params.get("vout", 0)
        value = params.get("value", 0)
        height = params.get("height", 0)
        coinbase = bool(params.get("is_coinbase", False))

        if args.verbose:
            op = OP_NAMES[event_type]
            # bpftrace format: "OP   " + hash + ":" + "%-6d %16ld %7d %s"
            outpoint = f"{txid}:{vout:<6d}"
            print("%-7s %-71s %16d %7d %s" % (
                op, outpoint, value, height, "Yes" if coinbase else "No"
            ))

        if csv_writer:
            csv_writer.writerow({
                "tracepoint": TRACEPOINT_MAP[event_type],
                "event_id": f"{txid}:{vout}",
                "core_ts_us": core_ts,
                "ipc_worker_ts_us": ipc_now,
                "ipc_latency_us": ipc_latency,
                "value": value,
                "height": height,
                "is_coinbase": coinbase,
            })

    if csv_file:
        csv_file.close()

    summary = {
        "counts": counts,
        "p50_latency_us": {
            k: (sorted(v)[len(v) // 2] if v else 0) for k, v in latencies.items()
        },
        "p95_latency_us": {
            k: (sorted(v)[int(len(v) * 0.95)] if v else 0) for k, v in latencies.items()
        },
    }
    print(json.dumps(summary), file=sys.stderr)


if __name__ == "__main__":
    main()
