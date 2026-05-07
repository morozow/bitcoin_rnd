#!/usr/bin/env python3
# Copyright (c) 2022-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
IPC-based block-connection benchmark — 1:1 equivalent of
contrib/tracing/connectblock_benchmark.bt.

Reads one JSON-RPC envelope per line from stdin, as produced by
StdioBusSdkHooks::SerializeEvent() for the stdio_bus USDT-mirror of
validation:block_connected (emitted in src/validation.cpp right next to
TRACEPOINT(validation, block_connected, ...)).

Fields consumed from params.type == "block_connected":
    hash, height, tx_count, inputs_count, sigops_cost, duration_ns

Arguments (same semantics as the bpftrace version):
    <start_height>            Only count blocks with height >= start_height
    <end_height>              Only count blocks with height <= end_height
                              (set to 0 to disable the upper bound)
    <logging_threshold_ms>    Log per-block info when duration_ms exceeds this

Output:
    * "Block N (hash)  T tx  I ins  S sigops  took D ms" per block over threshold
    * "BENCH B blk/s T tx/s I inputs/s S sigops/s (height H)" every second
    * "Took T ms to connect blocks between A and B." when end height is hit
    * log2 histogram of durations at EOF (printed to stderr).

USAGE (stdio_bus worker):
    ./connectblock_benchmark.py 300000 680000 1000
    ./connectblock_benchmark.py                 # defaults: 0 0 0 (log all)
"""

import json
import sys
import threading
import time
from collections import defaultdict


# ---------------------------------------------------------------------------

class BenchState:
    def __init__(self, start_height, end_height, logging_threshold_ms):
        self.start_height = start_height
        self.end_height = end_height
        self.logging_threshold_ms = logging_threshold_ms

        # Aggregated counters (1-second flush, same as `interval:s:1` in .bt)
        self.blocks = 0
        self.transactions = 0
        self.inputs = 0
        self.sigops = 0
        self.height = 0

        # Global counters
        self.total_blocks = 0
        self.total_transactions = 0
        self.total_inputs = 0
        self.total_sigops = 0
        self.durations_ms = []

        # Bench window timing (between start_height and end_height)
        self.bench_start_ns = None
        self.bench_end_ns = None
        if start_height == 0:
            self.bench_start_ns = time.monotonic_ns()

    def in_range(self, height):
        if height < self.start_height:
            return False
        if self.end_height > 0 and height > self.end_height:
            return False
        return True

    def observe(self, hash_hex, height, txs, ins, sigops, duration_ns):
        duration_ms = duration_ns / 1e6

        if self.in_range(height):
            self.blocks += 1
            self.transactions += txs
            self.inputs += ins
            self.sigops += sigops
            self.height = height

            self.total_blocks += 1
            self.total_transactions += txs
            self.total_inputs += ins
            self.total_sigops += sigops
            self.durations_ms.append(duration_ms)

            # Bench window markers
            if height == self.start_height and self.start_height != 0:
                self.bench_start_ns = time.monotonic_ns()
                print(
                    f"Starting Connect Block Benchmark between height "
                    f"{self.start_height} and {self.end_height}.",
                    flush=True,
                )
            if self.end_height > 0 and height >= self.end_height and self.bench_end_ns is None:
                self.bench_end_ns = time.monotonic_ns()
                if self.bench_start_ns:
                    duration_ms_total = (self.bench_end_ns - self.bench_start_ns) / 1e6
                    print(
                        f"\nTook {duration_ms_total/1000.0:.0f} ms to connect the blocks "
                        f"between height {self.start_height} and {self.end_height}.",
                        flush=True,
                    )

        if self.logging_threshold_ms > 0 and duration_ms > self.logging_threshold_ms:
            print(
                f"Block {height} ({hash_hex})  {txs:4d} tx  {ins:5d} ins  "
                f"{sigops:5d} sigops  took {int(duration_ms):4d} ms",
                flush=True,
            )

    def flush_second(self):
        """Emit the 1-second BENCH line if anything happened."""
        if self.blocks > 0:
            print(
                f"BENCH {self.blocks:4d} blk/s {self.transactions:6d} tx/s "
                f"{self.inputs:7d} inputs/s {self.sigops:8d} sigops/s "
                f"(height {self.height})",
                flush=True,
            )
            self.blocks = 0
            self.transactions = 0
            self.inputs = 0
            self.sigops = 0


# ---------------------------------------------------------------------------
# log2 histogram (bpftrace-style buckets: [0,1), [1,2), [2,4), ..., [>1024))
# ---------------------------------------------------------------------------

def _log2_hist(durations_ms):
    buckets = defaultdict(int)
    edges = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
    for d in durations_ms:
        if d < 1:
            label = "< 1"
        else:
            placed = False
            for i, hi in enumerate(edges):
                if d < hi:
                    lo = edges[i - 1] if i > 0 else 1
                    label = f"[{lo}, {hi})"
                    placed = True
                    break
            if not placed:
                label = ">= 1024"
        buckets[label] += 1
    return dict(buckets)


def _print_histogram(hist):
    order = ["< 1", "[1, 2)", "[2, 4)", "[4, 8)", "[8, 16)", "[16, 32)",
             "[32, 64)", "[64, 128)", "[128, 256)", "[256, 512)", "[512, 1024)",
             ">= 1024"]
    print("\nHistogram of block connection times in milliseconds (ms).", file=sys.stderr)
    if not hist:
        print("(no blocks observed)", file=sys.stderr)
        return
    peak = max(hist.values())
    for label in order:
        n = hist.get(label, 0)
        if n == 0:
            continue
        bar = "@" * max(1, int((n / peak) * 40))
        print(f"  {label:<12} {n:>8}   {bar}", file=sys.stderr)


# ---------------------------------------------------------------------------

def main():
    argv = sys.argv[1:]
    start_height = int(argv[0]) if len(argv) >= 1 else 0
    end_height = int(argv[1]) if len(argv) >= 2 else 0
    logging_threshold_ms = int(argv[2]) if len(argv) >= 3 else 0

    if end_height and end_height < start_height:
        print(
            f"Error: start height ({start_height}) larger than end height ({end_height})!",
            file=sys.stderr,
        )
        sys.exit(1)

    if end_height > 0:
        print(
            f"ConnectBlock benchmark between height {start_height} and {end_height} inclusive",
            flush=True,
        )
    else:
        print(f"ConnectBlock logging starting at height {start_height}", flush=True)
    if logging_threshold_ms > 0:
        print(
            f"Logging blocks taking longer than {logging_threshold_ms} ms to connect.",
            flush=True,
        )

    state = BenchState(start_height, end_height, logging_threshold_ms)

    # Background thread: per-second BENCH output (like `interval:s:1` in bpftrace).
    stop = threading.Event()

    def ticker():
        while not stop.is_set():
            time.sleep(1.0)
            state.flush_second()

    t = threading.Thread(target=ticker, daemon=True)
    t.start()

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                env = json.loads(line)
            except json.JSONDecodeError:
                continue
            params = env.get("params") or {}
            # Only process validation:block_connected mirror events — same as
            # the single USDT probe the .bt script attaches to.
            if params.get("type") != "block_connected":
                continue

            state.observe(
                hash_hex=params.get("hash", ""),
                height=int(params.get("height", -1)),
                txs=int(params.get("tx_count", 0)),
                ins=int(params.get("inputs_count", 0)),
                sigops=int(params.get("sigops_cost", 0)),
                duration_ns=int(params.get("duration_ns", 0)),
            )
    finally:
        stop.set()
        state.flush_second()
        _print_histogram(_log2_hist(state.durations_ms))
        summary = {
            "total_blocks": state.total_blocks,
            "total_transactions": state.total_transactions,
            "total_inputs": state.total_inputs,
            "total_sigops": state.total_sigops,
            "sum_duration_ms": round(sum(state.durations_ms), 2),
        }
        print(json.dumps(summary), file=sys.stderr)


if __name__ == "__main__":
    main()
