#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
Side-by-side latency comparison between eBPF/USDT tracing and stdio_bus IPC.

Rationale
---------
We observe different per-event latency numbers on different hosts when
collecting Bitcoin Core telemetry via eBPF/USDT versus the newer stdio_bus
IPC path. To reason about this rigorously we need to collect BOTH streams
during the same workload and join them by a stable event identifier, then
compute the relevant deltas.

Input formats
-------------
Both CSVs must at minimum have these columns:

    tracepoint, event_id, core_ts_us, <worker>_ts_us

For IPC logs (produced by contrib/tracing/ipc/all_events_recorder.py):

    tracepoint, event_type, event_id, core_ts_us, ipc_worker_ts_us,
    ipc_latency_us, params

For eBPF logs, any CSV with at least (tracepoint, event_id, core_ts_us,
ebpf_worker_ts_us) will work. A tiny helper bpftrace/BCC script can produce
exactly that.

Output
------
A merged CSV and a stats report on stdout:

    tracepoint,event_id,
    ebpf_core_ts_us,ebpf_worker_ts_us,ebpf_latency_us,
    ipc_core_ts_us,ipc_worker_ts_us,ipc_latency_us,
    delta_ebpf_minus_ipc_us

USAGE
-----
    ./compare_latency.py \
        --ipc /tmp/ipc.csv \
        --ebpf /tmp/ebpf.csv \
        --out /tmp/merged.csv \
        [--tracepoint mempool:added] \
        [--percentiles 50,95,99]
"""

import argparse
import csv
import statistics
import sys
from collections import defaultdict


def _load(path, ts_column):
    """Load a CSV into {(tracepoint, event_id): [row...]} keeping order."""
    rows_by_key = defaultdict(list)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = {"tracepoint", "event_id", "core_ts_us", ts_column} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{path}: missing required columns: {sorted(missing)}")
        for row in reader:
            key = (row["tracepoint"], row["event_id"])
            rows_by_key[key].append(row)
    return rows_by_key


def _percentiles(values, pct):
    if not values:
        return {p: 0 for p in pct}
    sorted_v = sorted(values)
    out = {}
    n = len(sorted_v)
    for p in pct:
        idx = min(n - 1, max(0, int(round(p / 100.0 * (n - 1)))))
        out[p] = sorted_v[idx]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipc", required=True, help="IPC CSV (all_events_recorder.py output)")
    ap.add_argument("--ebpf", required=True, help="eBPF CSV (from bpftrace/BCC collector)")
    ap.add_argument("--out", required=True, help="Merged CSV destination")
    ap.add_argument("--tracepoint", default=None,
                    help="Restrict comparison to one tracepoint.")
    ap.add_argument("--percentiles", default="50,95,99",
                    help="Comma-separated percentiles to report.")
    args = ap.parse_args()

    pct = [int(x) for x in args.percentiles.split(",") if x]

    ipc_rows = _load(args.ipc, "ipc_worker_ts_us")
    ebpf_rows = _load(args.ebpf, "ebpf_worker_ts_us")

    matched = 0
    ipc_only = 0
    ebpf_only = 0

    by_tracepoint = defaultdict(lambda: {
        "ipc_latency": [],
        "ebpf_latency": [],
        "delta": [],
        "matched": 0,
    })

    with open(args.out, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow([
            "tracepoint", "event_id",
            "ebpf_core_ts_us", "ebpf_worker_ts_us", "ebpf_latency_us",
            "ipc_core_ts_us", "ipc_worker_ts_us", "ipc_latency_us",
            "delta_ebpf_minus_ipc_us",
        ])

        all_keys = set(ipc_rows) | set(ebpf_rows)
        for key in sorted(all_keys):
            if args.tracepoint and key[0] != args.tracepoint:
                continue

            ipc_list = ipc_rows.get(key, [])
            ebpf_list = ebpf_rows.get(key, [])

            if ipc_list and ebpf_list:
                # Pair in order; if counts mismatch, zip truncates.
                for ipc_row, ebpf_row in zip(ipc_list, ebpf_list):
                    ebpf_core = int(ebpf_row["core_ts_us"] or 0)
                    ebpf_worker = int(ebpf_row["ebpf_worker_ts_us"] or 0)
                    ipc_core = int(ipc_row["core_ts_us"] or 0)
                    ipc_worker = int(ipc_row["ipc_worker_ts_us"] or 0)
                    ebpf_lat = ebpf_worker - ebpf_core if ebpf_core else 0
                    ipc_lat = ipc_worker - ipc_core if ipc_core else 0
                    delta = ebpf_lat - ipc_lat
                    writer.writerow([
                        key[0], key[1],
                        ebpf_core, ebpf_worker, ebpf_lat,
                        ipc_core, ipc_worker, ipc_lat,
                        delta,
                    ])
                    matched += 1
                    bucket = by_tracepoint[key[0]]
                    bucket["ipc_latency"].append(ipc_lat)
                    bucket["ebpf_latency"].append(ebpf_lat)
                    bucket["delta"].append(delta)
                    bucket["matched"] += 1
            elif ipc_list:
                ipc_only += len(ipc_list)
            else:
                ebpf_only += len(ebpf_list)

    # Stats report.
    print(f"=== latency comparison ===")
    print(f"matched={matched} ipc_only={ipc_only} ebpf_only={ebpf_only}")
    print()
    header = (
        f"{'tracepoint':<55}"
        f"{'n':>8}"
        f"{'ebpf_p50':>12}{'ebpf_p95':>12}{'ebpf_p99':>12}"
        f"{'ipc_p50':>12}{'ipc_p95':>12}{'ipc_p99':>12}"
        f"{'delta_p50':>12}"
    )
    print(header)
    print("-" * len(header))
    for tp, stats in sorted(by_tracepoint.items()):
        if not stats["matched"]:
            continue
        e = _percentiles(stats["ebpf_latency"], pct)
        i = _percentiles(stats["ipc_latency"], pct)
        d = _percentiles(stats["delta"], pct)
        print(
            f"{tp:<55}"
            f"{stats['matched']:>8}"
            f"{e.get(50,0):>12}{e.get(95,0):>12}{e.get(99,0):>12}"
            f"{i.get(50,0):>12}{i.get(95,0):>12}{i.get(99,0):>12}"
            f"{d.get(50,0):>12}"
        )


if __name__ == "__main__":
    main()
