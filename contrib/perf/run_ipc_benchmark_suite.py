#!/usr/bin/env python3
"""
Full IPC tracing benchmark suite.

Runs the stdio_bus_benchmark.py for each IPC worker configuration
and produces a combined report comparing all scenarios.

Scenarios:
1. Baseline (no tracing)
2. Block benchmark only (connectblock_benchmark.py)
3. Mempool monitor only (mempool_monitor.py)
4. P2P traffic only (p2p_traffic.py)
5. All workers combined

Each scenario generates blocks on regtest and measures overhead.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
IPC_DIR = REPO_ROOT / "contrib" / "tracing" / "ipc"
CONFIG_FILE = REPO_ROOT / "contrib" / "perf" / "stdiobus_trace.json"
BENCHMARK_SCRIPT = REPO_ROOT / "contrib" / "perf" / "stdio_bus_benchmark.py"
RESULTS_DIR = REPO_ROOT / "contrib" / "perf" / "results"

BLOCKS = 500

SCENARIOS = {
    "block_benchmark": {
        "description": "Block validation timing (equiv: connectblock_benchmark.bt)",
        "config": {
            "pools": [{
                "id": "block-bench",
                "command": "/usr/bin/python3",
                "args": [str(IPC_DIR / "connectblock_benchmark.py")],
                "instances": 1
            }]
        }
    },
    "mempool_monitor": {
        "description": "Mempool event monitoring (equiv: mempool_monitor.py)",
        "config": {
            "pools": [{
                "id": "mempool-mon",
                "command": "/usr/bin/python3",
                "args": [str(IPC_DIR / "mempool_monitor.py")],
                "instances": 1
            }]
        }
    },
    "p2p_traffic": {
        "description": "P2P traffic monitoring (equiv: log_p2p_traffic.bt + p2p_monitor.py)",
        "config": {
            "pools": [{
                "id": "p2p-traffic",
                "command": "/usr/bin/python3",
                "args": [str(IPC_DIR / "p2p_traffic.py")],
                "instances": 1
            }]
        }
    },
    "all_combined": {
        "description": "All tracing workers running simultaneously",
        "config": {
            "pools": [
                {
                    "id": "block-bench",
                    "command": "/usr/bin/python3",
                    "args": [str(IPC_DIR / "connectblock_benchmark.py")],
                    "instances": 1
                },
                {
                    "id": "mempool-mon",
                    "command": "/usr/bin/python3",
                    "args": [str(IPC_DIR / "mempool_monitor.py")],
                    "instances": 1
                },
                {
                    "id": "p2p-traffic",
                    "command": "/usr/bin/python3",
                    "args": [str(IPC_DIR / "p2p_traffic.py")],
                    "instances": 1
                }
            ]
        }
    },
}


def run_scenario(name, config):
    """Run a single benchmark scenario."""
    print(f"\n{'='*60}")
    print(f"SCENARIO: {name}")
    print(f"Description: {config['description']}")
    print(f"{'='*60}\n")

    # Write config
    with open(CONFIG_FILE, "w") as f:
        json.dump(config["config"], f, indent=2)

    # Run benchmark
    output_file = RESULTS_DIR / f"result_{name}.json"
    result = subprocess.run(
        [sys.executable, str(BENCHMARK_SCRIPT),
         f"--blocks={BLOCKS}",
         f"--output={output_file}"],
        capture_output=True, text=True, timeout=600
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # Read results
    if output_file.exists():
        with open(output_file) as f:
            return json.load(f)
    return None


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("IPC TRACING BENCHMARK SUITE")
    print(f"Blocks per scenario: {BLOCKS}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print("=" * 60)

    results = {}
    for name, config in SCENARIOS.items():
        try:
            result = run_scenario(name, config)
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

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY: IPC Tracing Overhead by Scenario")
    print("=" * 60)
    print(f"{'Scenario':<25} {'Overhead':>10} {'Baseline':>12} {'IPC':>12} {'Pass':>6}")
    print("-" * 65)
    for name, r in results.items():
        if "error" in r:
            print(f"{name:<25} {'ERROR':>10}")
        else:
            status = "✓" if r["pass"] else "✗"
            print(f"{name:<25} {r['overhead_pct']:>+9.2f}% "
                  f"{r['baseline_blocks_per_s']:>10.2f}b/s "
                  f"{r['shadow_blocks_per_s']:>10.2f}b/s "
                  f"{status:>6}")

    # Save combined report
    report_file = RESULTS_DIR / "full_suite_report.json"
    with open(report_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull report saved to: {report_file}")


if __name__ == "__main__":
    main()
