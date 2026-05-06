#!/usr/bin/env python3
# Copyright (c) 2022-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
IPC-based UTXO cache flush monitor — equivalent to log_utxocache_flush.py.
Receives utxocache:flush events via stdin NDJSON.

Tracks: flush duration, mode, coins count, memory usage.
"""

import json
import sys
import time


class UTXOCacheStats:
    def __init__(self):
        self.flushes = []
        self.start_time = time.monotonic()

    def record_flush(self, duration_us, mode, coins_count, coins_mem_usage, is_prune):
        self.flushes.append({
            "duration_ms": duration_us / 1000.0,
            "mode": mode,
            "coins_count": coins_count,
            "coins_mem_mb": coins_mem_usage / (1024 * 1024),
            "is_prune": is_prune,
            "timestamp": time.monotonic(),
        })

    def summary(self):
        runtime = time.monotonic() - self.start_time
        durations = [f["duration_ms"] for f in self.flushes]
        return {
            "runtime_s": round(runtime, 2),
            "total_flushes": len(self.flushes),
            "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "max_duration_ms": round(max(durations), 2) if durations else 0,
            "total_coins_flushed": sum(f["coins_count"] for f in self.flushes),
        }


def main():
    stats = UTXOCacheStats()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = event.get("method", "")
        if method == "utxocache.flush":
            params = event.get("params", {})
            stats.record_flush(
                duration_us=params.get("duration_us", 0),
                mode=params.get("mode", 0),
                coins_count=params.get("coins_count", 0),
                coins_mem_usage=params.get("coins_mem_usage", 0),
                is_prune=params.get("is_prune", False),
            )
            s = stats.summary()
            print(
                f"[utxocache] flush #{s['total_flushes']} "
                f"duration={params.get('duration_us', 0)/1000:.1f}ms "
                f"coins={params.get('coins_count', 0)}",
                file=sys.stderr,
            )

    s = stats.summary()
    print(json.dumps(s, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
