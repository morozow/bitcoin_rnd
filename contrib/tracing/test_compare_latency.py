#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
End-to-end smoke test for the latency benchmark harness.

Generates synthetic eBPF and IPC CSVs, runs compare_latency.py, and checks
that the output contains expected tracepoint rows.
"""

import csv
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        ipc_csv = os.path.join(tmp, "ipc.csv")
        ebpf_csv = os.path.join(tmp, "ebpf.csv")
        merged_csv = os.path.join(tmp, "merged.csv")

        ipc_fields = ["tracepoint", "event_type", "event_id",
                      "core_ts_us", "ipc_worker_ts_us",
                      "ipc_latency_us", "params"]
        with open(ipc_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=ipc_fields)
            w.writeheader()
            for i in range(50):
                w.writerow({
                    "tracepoint": "mempool:added",
                    "event_type": "mempool_added",
                    "event_id": f"tx_{i}",
                    "core_ts_us": 1_000_000 + i * 100,
                    "ipc_worker_ts_us": 1_000_300 + i * 100,
                    "ipc_latency_us": 300,
                    "params": "{}",
                })
                w.writerow({
                    "tracepoint": "utxocache:add",
                    "event_type": "utxocache_add",
                    "event_id": f"tx_{i}:0",
                    "core_ts_us": 1_000_050 + i * 100,
                    "ipc_worker_ts_us": 1_000_250 + i * 100,
                    "ipc_latency_us": 200,
                    "params": "{}",
                })

        ebpf_fields = ["tracepoint", "event_type", "event_id",
                       "core_ts_us", "ebpf_worker_ts_us",
                       "ebpf_latency_us", "params"]
        with open(ebpf_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=ebpf_fields)
            w.writeheader()
            for i in range(50):
                # eBPF has lower latency (100us) than IPC (300us / 200us).
                w.writerow({
                    "tracepoint": "mempool:added",
                    "event_type": "mempool_added",
                    "event_id": f"tx_{i}",
                    "core_ts_us": 1_000_000 + i * 100,
                    "ebpf_worker_ts_us": 1_000_100 + i * 100,
                    "ebpf_latency_us": 100,
                    "params": "{}",
                })
                w.writerow({
                    "tracepoint": "utxocache:add",
                    "event_type": "utxocache_add",
                    "event_id": f"tx_{i}:0",
                    "core_ts_us": 1_000_050 + i * 100,
                    "ebpf_worker_ts_us": 1_000_100 + i * 100,
                    "ebpf_latency_us": 50,
                    "params": "{}",
                })

        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "compare_latency.py"),
             "--ipc", ipc_csv, "--ebpf", ebpf_csv, "--out", merged_csv],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            print("compare_latency.py FAILED")
            print(proc.stderr)
            sys.exit(1)

        print(proc.stdout)

        # Sanity: merged CSV should have 100 rows (50+50) after header.
        with open(merged_csv) as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 101, f"expected 101 lines (header + 100), got {len(lines)}"

        # Sanity: the report should mention both tracepoints.
        assert "mempool:added" in proc.stdout
        assert "utxocache:add" in proc.stdout
        print("compare_latency smoke test OK")


if __name__ == "__main__":
    main()
