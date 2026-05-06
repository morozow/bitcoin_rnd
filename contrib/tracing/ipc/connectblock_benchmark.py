#!/usr/bin/env python3
# Copyright (c) 2022-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
IPC-based block connection benchmark — same purpose as connectblock_benchmark.bt
but receives events via stdin (NDJSON) instead of eBPF/USDT tracepoints.

Measures block validation latency from the validation:block_connected tracepoint
equivalent data delivered over IPC.

This is a stdio_bus worker: reads JSON events from stdin, computes timing stats.
No root required. No bpftrace dependency. Works on Linux/macOS/Windows.
"""

import json
import sys
import time
from collections import defaultdict


class BlockTimingStats:
    """Same metrics as connectblock_benchmark.bt: block connection time histogram."""

    def __init__(self, threshold_ms=0):
        self.threshold_ms = threshold_ms
        self.timings_ms = []
        self.blocks_processed = 0
        self.blocks_over_threshold = 0
        self.start_time = time.monotonic()

    def record_block(self, received_us, validated_us, height, tx_count, accepted):
        if not accepted:
            return
        latency_ms = (validated_us - received_us) / 1000.0
        self.timings_ms.append(latency_ms)
        self.blocks_processed += 1

        if self.threshold_ms > 0 and latency_ms > self.threshold_ms:
            self.blocks_over_threshold += 1
            print(
                f"[block_bench] height={height} txs={tx_count} "
                f"latency={latency_ms:.1f}ms (>{self.threshold_ms}ms)",
                file=sys.stderr,
            )

    def histogram(self):
        """Produce histogram buckets similar to bpftrace @hist output."""
        if not self.timings_ms:
            return {}
        buckets = defaultdict(int)
        for t in self.timings_ms:
            # Log2 bucketing like bpftrace
            if t < 1:
                buckets["<1ms"] += 1
            elif t < 2:
                buckets["1-2ms"] += 1
            elif t < 4:
                buckets["2-4ms"] += 1
            elif t < 8:
                buckets["4-8ms"] += 1
            elif t < 16:
                buckets["8-16ms"] += 1
            elif t < 32:
                buckets["16-32ms"] += 1
            elif t < 64:
                buckets["32-64ms"] += 1
            elif t < 128:
                buckets["64-128ms"] += 1
            elif t < 256:
                buckets["128-256ms"] += 1
            elif t < 512:
                buckets["256-512ms"] += 1
            elif t < 1024:
                buckets["512-1024ms"] += 1
            else:
                buckets[">1024ms"] += 1
        return dict(buckets)

    def summary(self):
        runtime = time.monotonic() - self.start_time
        p50 = sorted(self.timings_ms)[len(self.timings_ms) // 2] if self.timings_ms else 0
        p95 = sorted(self.timings_ms)[int(len(self.timings_ms) * 0.95)] if self.timings_ms else 0
        p99 = sorted(self.timings_ms)[int(len(self.timings_ms) * 0.99)] if self.timings_ms else 0
        return {
            "runtime_s": round(runtime, 2),
            "blocks_processed": self.blocks_processed,
            "blocks_over_threshold": self.blocks_over_threshold,
            "latency_p50_ms": round(p50, 2),
            "latency_p95_ms": round(p95, 2),
            "latency_p99_ms": round(p99, 2),
            "histogram": self.histogram(),
        }


def main():
    threshold_ms = float(sys.argv[1]) if len(sys.argv) > 1 else 0
    stats = BlockTimingStats(threshold_ms=threshold_ms)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = event.get("method", "")
        if method == "block.validated":
            params = event.get("params", {})
            stats.record_block(
                received_us=params.get("received_us", 0),
                validated_us=params.get("validated_us", 0),
                height=params.get("height", -1),
                tx_count=params.get("tx_count", 0),
                accepted=params.get("accepted", False),
            )

        # Periodic report
        if stats.blocks_processed > 0 and stats.blocks_processed % 100 == 0:
            s = stats.summary()
            print(
                f"[block_bench] {s['blocks_processed']} blocks, "
                f"p50={s['latency_p50_ms']:.1f}ms p95={s['latency_p95_ms']:.1f}ms",
                file=sys.stderr,
            )

    # Final summary
    s = stats.summary()
    print(json.dumps(s, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
