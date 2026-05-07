#!/usr/bin/env python3
# Copyright (c) 2021-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
IPC-based UTXO cache flush logger — 1:1 equivalent of
contrib/tracing/log_utxocache_flush.py.

Reads NDJSON from stdin and processes the stdio_bus USDT-mirror of the
utxocache:flush tracepoint (emitted in src/validation.cpp right next to
TRACEPOINT(utxocache, flush, ...)).

Fields consumed from params.type == "utxocache_flush":
    duration_us, mode, coins_count, coins_mem_usage, is_flush_for_prune

Output (identical columns to log_utxocache_flush.py):
    Duration (µs)   Mode          Coins Count    Memory Usage    Flush for Prune
"""

import json
import sys


FLUSH_MODES = ["NONE", "IF_NEEDED", "PERIODIC", "FORCE_FLUSH", "FORCE_SYNC"]


def _fmt_row(duration_us, mode, coins_count, coins_mem_usage, is_prune):
    mode_str = FLUSH_MODES[mode] if 0 <= mode < len(FLUSH_MODES) else f"MODE_{mode}"
    mem_str = "%.2f kB" % (coins_mem_usage / 1000)
    return "%-15d %-12s %-15d %-15s %-8s" % (
        duration_us, mode_str, coins_count, mem_str, is_prune
    )


def main():
    # Header matches the eBPF version exactly.
    print("%-15s %-12s %-15s %-15s %-8s" % (
        "Duration (µs)", "Mode", "Coins Count", "Memory Usage", "Flush for Prune"
    ))
    print("Logging utxocache flushes. Ctrl-C to end...")
    sys.stdout.flush()

    total = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            env = json.loads(line)
        except json.JSONDecodeError:
            continue
        params = env.get("params") or {}
        if params.get("type") != "utxocache_flush":
            continue

        duration_us = int(params.get("duration_us", 0))
        mode = int(params.get("mode", 0))
        coins_count = int(params.get("coins_count", 0))
        coins_mem_usage = int(params.get("coins_mem_usage", 0))
        is_prune = bool(params.get("is_flush_for_prune", False))

        print(_fmt_row(duration_us, mode, coins_count, coins_mem_usage, is_prune))
        sys.stdout.flush()
        total += 1

    print(json.dumps({"flushes": total}), file=sys.stderr)


if __name__ == "__main__":
    main()
