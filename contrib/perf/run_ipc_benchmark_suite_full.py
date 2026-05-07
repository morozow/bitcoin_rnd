#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Full IPC tracing benchmark suite — throughput (blocks/s) comparison for
every IPC worker, including the newly-added ones for full USDT tracepoint
parity.

This complements `run_ipc_benchmark_suite.py` (the original 4-scenario
suite) by adding the workers that cover the remaining 12 USDT tracepoints:

  - `p2p_connections`        (net:*_connection, 5 tracepoints)
  - `utxocache_utxos`        (utxocache:add/spent/uncache)
  - `coin_selection`         (coin_selection:*, 4 tracepoints)
  - `all_events_recorder`    (catch-all: every stdio_bus event)
  - `all_parity`             (all workers above running simultaneously)

Each scenario runs for N blocks on regtest, with -stdiobus=off then
-stdiobus=shadow, and reports blocks/s overhead identically to the
original suite.

Example output:

    SUMMARY: IPC Tracing Overhead by Scenario (full parity)
    =====================================================================
    Scenario                   Overhead     Baseline          IPC   Pass
    ---------------------------------------------------------------------
    block_benchmark              +4.79%      20.10b/s      19.51b/s      ✗
    mempool_monitor             +11.07%      19.80b/s      17.59b/s      ✗
    p2p_traffic                  +7.13%      19.54b/s      18.14b/s      ✗
    p2p_connections              +2.40%      20.11b/s      19.63b/s      ✓
    utxocache_utxos             +14.20%      19.99b/s      17.15b/s      ✗
    coin_selection               +0.10%      20.04b/s      20.02b/s      ✓
    all_events_recorder         +18.50%      20.10b/s      16.38b/s      ✗
    all_parity                  +35.70%      20.14b/s      12.95b/s      ✗

USAGE:
    python3 contrib/perf/run_ipc_benchmark_suite_full.py [--blocks=N]
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
IPC_DIR = REPO_ROOT / "contrib" / "tracing" / "ipc"
CONFIG_FILE = REPO_ROOT / "contrib" / "perf" / "stdiobus_trace.json"
BENCHMARK_SCRIPT = REPO_ROOT / "contrib" / "perf" / "stdio_bus_benchmark.py"
RESULTS_DIR = REPO_ROOT / "contrib" / "perf" / "results"

DEFAULT_BLOCKS = 500


def _pool(name, script, extra_args=None):
    """Build a stdiobus_trace.json pool entry for a single IPC worker."""
    args = [str(IPC_DIR / script)]
    if extra_args:
        args.extend(extra_args)
    return {
        "id": name,
        "command": sys.executable,
        "args": args,
        "instances": 1,
    }


def _tmp_csv(name):
    """Return a scratch CSV path for recorders that need --csv."""
    return str(RESULTS_DIR / f"{name}.csv")


def build_scenarios():
    """All scenarios. Original suite scenarios are repeated here so the
    report stands alone and includes the same rows for direct comparison."""
    return {
        # === Original scenarios (kept verbatim for apples-to-apples) ===
        "block_benchmark": {
            "description": "Block validation timing (validation:block_connected)",
            "config": {"pools": [_pool("block-bench", "connectblock_benchmark.py")]},
        },
        "mempool_monitor": {
            "description": "Mempool events (mempool:added/removed/replaced/rejected)",
            "config": {"pools": [_pool("mempool-mon", "mempool_monitor.py")]},
        },
        "p2p_traffic": {
            "description": "P2P traffic (net:inbound_message/outbound_message)",
            "config": {"pools": [_pool("p2p-traffic", "p2p_traffic.py")]},
        },

        # === New scenarios covering the remaining 12 USDT tracepoints ===
        "p2p_connections": {
            "description": "P2P connections (net:inbound/outbound/closed/evicted/misbehaving)",
            "config": {"pools": [
                _pool("p2p-connections", "p2p_connections.py",
                      ["--csv", _tmp_csv("p2p_connections")]),
            ]},
        },
        "utxocache_utxos": {
            "description": "UTXO set changes (utxocache:add/spent/uncache) — hot path",
            "config": {"pools": [
                _pool("utxocache-utxos", "utxocache_utxos.py",
                      ["--csv", _tmp_csv("utxocache_utxos")]),
            ]},
        },
        "coin_selection": {
            "description": "Wallet coin selection (coin_selection:*)",
            "config": {"pools": [
                _pool("coin-selection", "coin_selection.py",
                      ["--csv", _tmp_csv("coin_selection")]),
            ]},
        },
        "all_events_recorder": {
            "description": "Catch-all CSV recorder for every stdio_bus event",
            "config": {"pools": [
                _pool("all-events", "all_events_recorder.py",
                      ["--csv", _tmp_csv("all_events")]),
            ]},
        },

        # === Combined: every worker at once (worst-case back-pressure) ===
        "all_parity": {
            "description": "All parity workers running simultaneously",
            "config": {"pools": [
                _pool("block-bench", "connectblock_benchmark.py"),
                _pool("mempool-mon", "mempool_monitor.py"),
                _pool("p2p-traffic", "p2p_traffic.py"),
                _pool("p2p-connections", "p2p_connections.py",
                      ["--csv", _tmp_csv("p2p_connections_all")]),
                _pool("utxocache-utxos", "utxocache_utxos.py",
                      ["--csv", _tmp_csv("utxocache_utxos_all")]),
                _pool("coin-selection", "coin_selection.py",
                      ["--csv", _tmp_csv("coin_selection_all")]),
            ]},
        },
    }


def run_scenario(name, config, blocks):
    print(f"\n{'=' * 60}")
    print(f"SCENARIO: {name}")
    print(f"Description: {config['description']}")
    print(f"{'=' * 60}\n")

    with open(CONFIG_FILE, "w") as f:
        json.dump(config["config"], f, indent=2)

    output_file = RESULTS_DIR / f"result_{name}.json"
    result = subprocess.run(
        [sys.executable, str(BENCHMARK_SCRIPT),
         f"--blocks={blocks}", f"--output={output_file}"],
        capture_output=True, text=True, timeout=900,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if output_file.exists():
        with open(output_file) as f:
            return json.load(f)
    return None


def _fmt_row(name, r):
    if "error" in r:
        return f"{name:<25} {'ERROR':>10}"
    status = "✓" if r["pass"] else "✗"
    return (
        f"{name:<25} {r['overhead_pct']:>+9.2f}% "
        f"{r['baseline_blocks_per_s']:>10.2f}b/s "
        f"{r['shadow_blocks_per_s']:>10.2f}b/s "
        f"{status:>6}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=DEFAULT_BLOCKS)
    ap.add_argument("--only", nargs="+", default=None,
                    help="Run only the named scenarios.")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    scenarios = build_scenarios()
    if args.only:
        scenarios = {k: v for k, v in scenarios.items() if k in args.only}

    print("=" * 60)
    print("IPC TRACING BENCHMARK SUITE (FULL PARITY)")
    print(f"Blocks per scenario: {args.blocks}")
    print(f"Scenarios: {len(scenarios)}")
    print("=" * 60)

    results = {}
    for name, config in scenarios.items():
        try:
            result = run_scenario(name, config, args.blocks)
            if result:
                results[name] = {
                    "description": config["description"],
                    "overhead_pct": result["overhead"]["time_pct"],
                    "baseline_blocks_per_s": result["baseline"]["blocks_per_s"],
                    "shadow_blocks_per_s": result["shadow"]["blocks_per_s"],
                    "pass": result["pass"],
                }
        except Exception as e:
            print(f"ERROR in scenario {name}: {e}", file=sys.stderr)
            results[name] = {"error": str(e)}

    print("\n" + "=" * 60)
    print("SUMMARY: IPC Tracing Overhead by Scenario (full parity)")
    print("=" * 60)
    print(f"{'Scenario':<25} {'Overhead':>10} {'Baseline':>12} {'IPC':>12} {'Pass':>6}")
    print("-" * 65)
    for name, r in results.items():
        print(_fmt_row(name, r))

    report_file = RESULTS_DIR / "full_parity_suite_report.json"
    with open(report_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull parity report saved to: {report_file}")


if __name__ == "__main__":
    main()
