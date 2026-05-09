#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Isolated Benchmark Runner (host-side orchestrator).

Runs each benchmark condition as a separate Docker container with
filesystem cache flush between runs. This eliminates page cache
contamination that occurs when conditions run sequentially in a
single container.

Features:
  - Each condition = separate docker run (clean process state)
  - drop_caches between conditions (clean page cache)
  - Parses output from each run
  - Computes overhead% relative to baseline
  - Prints formatted table to terminal
  - Saves results to timestamped directory as JSON

Usage:
    python3 contrib/perf/run_benchmark_isolated.py \\
        --image bitcoin-reindex-benchmark \\
        --block-dir /tmp/btc_blocks/mainnet/blocks \\
        --stop-height 200000 \\
        --conditions baseline,ebpf,ebpf_full,ipc,raw_ipc

Output:
    contrib/perf/results/<timestamp>/
        ├── baseline.json
        ├── ebpf.json
        ├── ebpf_full.json
        ├── ipc.json
        ├── raw_ipc.json
        └── report.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Default values
DEFAULT_IMAGE = "bitcoin-reindex-benchmark"
DEFAULT_BLOCK_DIR = "/tmp/btc_blocks/mainnet/blocks"
DEFAULT_STOP_HEIGHT = 200000
DEFAULT_CONDITIONS = "baseline,ebpf,ebpf_full,ipc,raw_ipc"
DEFAULT_RESULTS_BASE = Path(__file__).resolve().parent / "results"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run benchmark conditions in isolated containers with cache flush.",
    )
    parser.add_argument(
        "--image", default=DEFAULT_IMAGE,
        help=f"Docker image name (default: {DEFAULT_IMAGE})",
    )
    parser.add_argument(
        "--block-dir", default=DEFAULT_BLOCK_DIR,
        help=f"Host path to mainnet blocks (default: {DEFAULT_BLOCK_DIR})",
    )
    parser.add_argument(
        "--stop-height", type=int, default=DEFAULT_STOP_HEIGHT,
        help=f"Block height to stop at (default: {DEFAULT_STOP_HEIGHT})",
    )
    parser.add_argument(
        "--conditions", default=DEFAULT_CONDITIONS,
        help=f"Comma-separated conditions (default: {DEFAULT_CONDITIONS})",
    )
    parser.add_argument(
        "--results-dir", type=Path, default=None,
        help="Override results directory (default: results/<timestamp>)",
    )
    parser.add_argument(
        "--no-cache-flush", action="store_true",
        help="Skip cache flush between conditions (for debugging)",
    )
    return parser.parse_args(argv)


def flush_caches():
    """Flush page cache in Docker VM via privileged alpine container."""
    print("  Flushing page cache...", end=" ", flush=True)
    result = subprocess.run(
        [
            "docker", "run", "--rm", "--privileged", "alpine",
            "sh", "-c", "sync && echo 3 > /proc/sys/vm/drop_caches",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        print("done")
    else:
        print(f"FAILED ({result.stderr.strip()})")
    return result.returncode == 0


def run_condition(image, block_dir, stop_height, condition):
    """Run a single condition in a Docker container.

    Returns:
        Tuple of (stdout_text, stderr_text, returncode, elapsed_s)
    """
    cmd = [
        "docker", "run", "--privileged", "--rm",
        "-v", f"{block_dir}:/blocks",
        "-v", "/sys/kernel/debug:/sys/kernel/debug",
        image,
        "--block-dir", "/blocks",
        "--stop-height", str(stop_height),
        "--conditions", condition,
    ]

    start = time.monotonic()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=14400,  # 4 hours max
    )
    elapsed = time.monotonic() - start

    return result.stdout, result.stderr, result.returncode, elapsed


def parse_condition_output(stdout_text, condition_name):
    """Parse benchmark output to extract metrics for a condition.

    Looks for the table row matching the condition name.
    Format: | condition | time | blocks/s | overhead% | events | status |
    """
    result = {
        "name": condition_name,
        "elapsed_s": None,
        "blocks_per_second": None,
        "overhead_pct": None,
        "events": 0,
        "status": "UNKNOWN",
        "error": None,
    }

    for line in stdout_text.split("\n"):
        # Match table row: | name | time | bps | overhead | events | status |
        if f"| {condition_name}" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 6:
                try:
                    result["elapsed_s"] = float(parts[1])
                    result["blocks_per_second"] = float(parts[2])
                    overhead_str = parts[3].replace("%", "").strip()
                    if overhead_str != "—":
                        result["overhead_pct"] = float(overhead_str)
                    result["events"] = int(parts[4])
                    result["status"] = parts[5]
                except (ValueError, IndexError):
                    pass
            break

    # If parsing failed, try to find error
    if result["elapsed_s"] is None:
        if "FAILED" in stdout_text:
            result["status"] = "FAILED"
            # Try to extract error message
            for line in stdout_text.split("\n"):
                if "FAILED" in line and condition_name in line:
                    result["error"] = line.strip()
                    break

    return result


def compute_overhead(baseline_time, condition_time):
    """Compute overhead percentage."""
    if baseline_time is None or baseline_time <= 0:
        return None
    if condition_time is None or condition_time <= 0:
        return None
    return ((condition_time - baseline_time) / baseline_time) * 100


def format_table(results, stop_height):
    """Format results as a terminal table."""
    lines = []
    lines.append("")
    lines.append("=" * 78)
    lines.append("BENCHMARK RESULTS (isolated runs, cache flushed between conditions)")
    lines.append("=" * 78)
    lines.append("")

    # Header
    header = f"| {'Condition':<12} | {'Time(s)':>8} | {'Blocks/s':>8} | {'Overhead%':>10} | {'Events':>10} | {'Status':<8} |"
    sep = f"|{'-'*14}|{'-'*10}|{'-'*10}|{'-'*12}|{'-'*12}|{'-'*10}|"
    lines.append(header)
    lines.append(sep)

    for r in results:
        if r["elapsed_s"] is not None:
            time_str = f"{r['elapsed_s']:.2f}"
            bps_str = f"{r['blocks_per_second']:.1f}"
            overhead_str = f"{r['overhead_pct']:.2f}%" if r["overhead_pct"] is not None else "—"
            events_str = str(r["events"])
            status_str = r["status"]
        else:
            time_str = "-"
            bps_str = "-"
            overhead_str = "-"
            events_str = "-"
            status_str = r.get("status", "FAILED")

        row = f"| {r['name']:<12} | {time_str:>8} | {bps_str:>8} | {overhead_str:>10} | {events_str:>10} | {status_str:<8} |"
        lines.append(row)

    lines.append("")
    lines.append(f"Block range: 0-{stop_height}")
    lines.append(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 78)

    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv)

    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    if not conditions:
        print("ERROR: No conditions specified", file=sys.stderr)
        return 1

    # Ensure baseline runs first
    if "baseline" in conditions:
        conditions.remove("baseline")
        conditions.insert(0, "baseline")

    # Create timestamped results directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.results_dir:
        results_dir = args.results_dir
    else:
        results_dir = DEFAULT_RESULTS_BASE / timestamp
    results_dir.mkdir(parents=True, exist_ok=True)

    print(f"Isolated Benchmark Runner")
    print(f"  Image:       {args.image}")
    print(f"  Block dir:   {args.block_dir}")
    print(f"  Stop height: {args.stop_height}")
    print(f"  Conditions:  {', '.join(conditions)}")
    print(f"  Results:     {results_dir}")
    print(f"  Cache flush: {'yes' if not args.no_cache_flush else 'no'}")
    print()

    results = []
    baseline_time = None

    for i, condition in enumerate(conditions):
        print(f"[{i+1}/{len(conditions)}] Running: {condition}")
        print(f"  {'─' * 50}")

        # Flush caches before each condition
        if not args.no_cache_flush:
            flush_caches()

        # Run the condition
        print(f"  Starting docker run...", flush=True)
        try:
            stdout, stderr, returncode, wall_time = run_condition(
                args.image, args.block_dir, args.stop_height, condition
            )
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT (4h exceeded)")
            results.append({
                "name": condition,
                "elapsed_s": None,
                "blocks_per_second": None,
                "overhead_pct": None,
                "events": 0,
                "status": "TIMEOUT",
                "error": "Docker run exceeded 4h timeout",
            })
            continue

        # Parse output
        r = parse_condition_output(stdout, condition)

        # Save raw output
        condition_data = {
            "condition": condition,
            "parsed": r,
            "returncode": returncode,
            "wall_time_s": wall_time,
            "stdout": stdout,
            "stderr": stderr[-2000:] if stderr else "",  # Last 2KB of stderr
        }
        condition_file = results_dir / f"{condition}.json"
        condition_file.write_text(json.dumps(condition_data, indent=2))

        # Compute overhead relative to baseline
        if condition == "baseline" and r["elapsed_s"] is not None:
            baseline_time = r["elapsed_s"]
            r["overhead_pct"] = None  # Baseline has no overhead
        elif baseline_time is not None and r["elapsed_s"] is not None:
            r["overhead_pct"] = compute_overhead(baseline_time, r["elapsed_s"])

        results.append(r)

        # Print summary for this condition
        if r["elapsed_s"] is not None:
            overhead_str = f", overhead={r['overhead_pct']:.2f}%" if r["overhead_pct"] is not None else ""
            print(f"  Done: {r['elapsed_s']:.2f}s, {r['blocks_per_second']:.1f} blocks/s{overhead_str}")
        else:
            print(f"  FAILED: {r.get('error', 'unknown error')}")
        print()

    # Print final table
    table = format_table(results, args.stop_height)
    print(table)

    # Save report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "image": args.image,
            "block_dir": args.block_dir,
            "stop_height": args.stop_height,
            "conditions": conditions,
            "cache_flush": not args.no_cache_flush,
        },
        "baseline_time_s": baseline_time,
        "results": results,
    }
    report_file = results_dir / "report.json"
    report_file.write_text(json.dumps(report, indent=2))
    print(f"\nResults saved to: {results_dir}")
    print(f"Report: {report_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
