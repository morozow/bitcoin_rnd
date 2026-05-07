#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
IPC-based wallet coin-selection monitor.

Covers the four coin_selection USDT tracepoints:

  coin_selection:selected_coins            ->  type="coin_selection_selected_coins"
  coin_selection:normal_create_tx_internal ->  type="coin_selection_normal_create_tx"
  coin_selection:attempting_aps_create_tx  ->  type="coin_selection_attempting_aps"
  coin_selection:aps_create_tx_internal    ->  type="coin_selection_aps_create_tx"

No eBPF-equivalent script ships in contrib/tracing/ for coin selection, but
the USDT tracepoints are documented in doc/tracing.md, and this worker
produces the same fields so that they can be compared side-by-side with a
bpftrace one-liner.
"""

import argparse
import csv
import json
import sys
import time


TYPE_TO_TRACEPOINT = {
    "coin_selection_selected_coins": "coin_selection:selected_coins",
    "coin_selection_normal_create_tx": "coin_selection:normal_create_tx_internal",
    "coin_selection_attempting_aps": "coin_selection:attempting_aps_create_tx",
    "coin_selection_aps_create_tx": "coin_selection:aps_create_tx_internal",
}

CSV_FIELDS = [
    "tracepoint", "wallet_name", "core_ts_us", "ipc_worker_ts_us",
    "ipc_latency_us", "fee", "algorithm", "success", "use_aps",
]


def _type_of(event):
    params = event.get("params", {}) or {}
    return params.get("type") or event.get("method", ""), params


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    counts = {t: 0 for t in TYPE_TO_TRACEPOINT}
    csv_file = None
    csv_writer = None
    if args.csv:
        csv_file = open(args.csv, "w", newline="")
        csv_writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        csv_writer.writeheader()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type, params = _type_of(event)
        if event_type not in TYPE_TO_TRACEPOINT:
            continue

        counts[event_type] += 1
        core_ts = int(params.get("timestamp_us") or 0)
        ipc_now = int(time.monotonic() * 1_000_000)
        ipc_latency = (ipc_now - core_ts) if core_ts else 0

        if args.verbose:
            print(f"[{TYPE_TO_TRACEPOINT[event_type]}] "
                  f"wallet={params.get('wallet_name')} "
                  f"fee={params.get('fee', 0)} "
                  f"algo={params.get('algorithm', '')} "
                  f"success={params.get('success', '')} "
                  f"use_aps={params.get('use_aps', '')}")

        if csv_writer:
            csv_writer.writerow({
                "tracepoint": TYPE_TO_TRACEPOINT[event_type],
                "wallet_name": params.get("wallet_name", ""),
                "core_ts_us": core_ts,
                "ipc_worker_ts_us": ipc_now,
                "ipc_latency_us": ipc_latency,
                "fee": params.get("fee", 0),
                "algorithm": params.get("algorithm", ""),
                "success": params.get("success", ""),
                "use_aps": params.get("use_aps", ""),
            })

    if csv_file:
        csv_file.close()
    print(json.dumps(counts), file=sys.stderr)


if __name__ == "__main__":
    main()
