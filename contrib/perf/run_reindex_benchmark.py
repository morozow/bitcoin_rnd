#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Reindex Mainnet Benchmark — Main Entry Point

Measures tracing overhead on Bitcoin Core using real mainnet blocks via
`bitcoind -reindex`. Compares four conditions:
  1. Baseline (no tracing)
  2. eBPF (bpftrace attached to all 20 USDT probes)
  3. IPC (stdio_bus shadow mode with all 6 workers)
  4. Cap'n Proto simulation (calibrated overhead worker)

Results are intended as evidence for Bitcoin Core issue #35142 demonstrating
that IPC-based tracing overhead is competitive with eBPF on realistic workloads.

Usage:
    python3 contrib/perf/run_reindex_benchmark.py \\
        --block-dir /blocks \\
        --stop-height 20000 \\
        --output results.json

Docker usage:
    docker run --privileged --rm \\
        -v /path/to/blocks:/blocks:ro \\
        bitcoin-reindex-benchmark --stop-height=20000
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure the reindex package is importable regardless of CWD
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from reindex import (
    BenchmarkConfig,
    Condition,
    flush_caches,
    format_table,
    generate_report,
    report_to_json,
    validate_block_files,
    validate_workload,
)
from reindex.config import (
    ConditionResult,
    ReportMetadata,
)
from reindex.report import BenchmarkReport
from reindex.runners import (
    BaselineRunner,
    CapnProtoSimRunner,
    EbpfRunner,
    IpcRunner,
)
from reindex.workload_validation import (
    WorkloadValidationResult,
    format_workload_validation,
)

logger = logging.getLogger(__name__)

# Default paths inside Docker container
DEFAULT_BLOCK_DIR = Path("/blocks")
DEFAULT_DATADIR_BASE = Path("/benchmark")
DEFAULT_OUTPUT = Path("benchmark_report.json")
DEFAULT_STOP_HEIGHT = 20_000


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Reindex Mainnet Benchmark: measures tracing overhead on "
            "Bitcoin Core using real mainnet blocks."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--block-dir",
        type=Path,
        default=DEFAULT_BLOCK_DIR,
        help=(
            "Directory containing mainnet blk*.dat files "
            f"(default: {DEFAULT_BLOCK_DIR})"
        ),
    )
    parser.add_argument(
        "--stop-height",
        type=int,
        default=DEFAULT_STOP_HEIGHT,
        help=(
            "Block height at which to stop reindex, range [10000, 50000] "
            f"(default: {DEFAULT_STOP_HEIGHT})"
        ),
    )
    parser.add_argument(
        "--datadir",
        type=Path,
        default=DEFAULT_DATADIR_BASE,
        help=(
            "Base directory for per-condition data directories "
            f"(default: {DEFAULT_DATADIR_BASE})"
        ),
    )
    parser.add_argument(
        "--conditions",
        type=str,
        default="baseline,ebpf,ipc,capnproto",
        help=(
            "Comma-separated list of conditions to run. "
            "Options: baseline,ebpf,ipc,capnproto "
            "(default: baseline,ebpf,ipc,capnproto)"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path for JSON report output (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--bitcoind",
        type=Path,
        default=None,
        help="Path to bitcoind binary (default: /bitcoin/build/bin/bitcoind)",
    )
    parser.add_argument(
        "--no-flush-caches",
        action="store_true",
        help="Skip filesystem cache flushing between conditions",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    return parser.parse_args(argv)


def parse_conditions(conditions_str: str) -> list[Condition]:
    """Parse comma-separated condition names into Condition enum values.

    Args:
        conditions_str: Comma-separated condition names.

    Returns:
        List of Condition enum values.

    Raises:
        ValueError: If an invalid condition name is provided.
    """
    valid_names = {c.value for c in Condition}
    conditions = []

    for name in conditions_str.split(","):
        name = name.strip().lower()
        if not name:
            continue
        if name not in valid_names:
            raise ValueError(
                f"Invalid condition '{name}'. "
                f"Valid options: {', '.join(sorted(valid_names))}"
            )
        conditions.append(Condition(name))

    if not conditions:
        raise ValueError("At least one condition must be specified")

    return conditions


def run_benchmark(
    config: BenchmarkConfig,
) -> tuple[BenchmarkReport, WorkloadValidationResult]:
    """Execute the full benchmark: validate, run conditions, generate report.

    Runs conditions sequentially with cache flushing between each.
    Continues with remaining conditions if one fails.

    Args:
        config: Benchmark configuration.

    Returns:
        Tuple of (BenchmarkReport, WorkloadValidationResult).
    """
    # Step 1: Validate block data
    logger.info("Validating block data in %s...", config.block_dir)
    validation = validate_block_files(config.block_dir)
    if not validation.valid:
        logger.error("Block validation failed: %s", validation.error_message)
        print(f"ERROR: {validation.error_message}", file=sys.stderr)
        sys.exit(1)

    logger.info(
        "Block validation passed: %d blocks in %d files",
        validation.block_count,
        validation.file_count,
    )

    # Step 2: Ensure baseline runs first if included
    conditions = list(config.conditions)
    if Condition.BASELINE in conditions:
        conditions.remove(Condition.BASELINE)
        conditions.insert(0, Condition.BASELINE)

    # Step 3: Execute conditions sequentially
    results: dict[str, ConditionResult] = {}
    baseline_elapsed: float | None = None

    for i, condition in enumerate(conditions):
        logger.info(
            "=== Running condition %d/%d: %s ===",
            i + 1,
            len(conditions),
            condition.value,
        )

        # Flush caches between conditions (skip before first)
        if i > 0 and config.flush_caches:
            logger.info("Flushing filesystem caches...")
            flushed = flush_caches()
            if not flushed:
                logger.warning(
                    "Cache flush failed — results may be affected by "
                    "page cache from previous condition"
                )

        # Run the condition
        try:
            result = _run_single_condition(
                condition=condition,
                config=config,
                baseline_elapsed=baseline_elapsed,
            )
        except Exception as e:
            logger.error(
                "Condition '%s' failed with exception: %s",
                condition.value,
                e,
            )
            result = ConditionResult(
                name=condition.value,
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error=str(e),
            )

        results[condition.value] = result

        # Track baseline elapsed for overhead calculations
        if condition == Condition.BASELINE and result.error is None:
            baseline_elapsed = result.elapsed_s

        # Log result summary
        if result.error:
            logger.error(
                "Condition '%s' FAILED: %s", condition.value, result.error
            )
        else:
            overhead_str = (
                f", overhead={result.overhead_pct:.2f}%"
                if result.overhead_pct is not None
                else ""
            )
            logger.info(
                "Condition '%s' completed: %.2fs, %.1f blocks/s%s",
                condition.value,
                result.elapsed_s,
                result.blocks_per_second,
                overhead_str,
            )

    # Step 4: Generate report
    metadata = ReportMetadata(
        block_range=(0, config.stop_height),
        total_transactions=0,  # Would need block parsing to compute
        docker_image_hash=_get_docker_image_hash(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        host_info=_get_host_info(),
    )

    report = generate_report(config, results, metadata)

    # Step 5: Workload validation
    workload_result = validate_workload(results)

    return report, workload_result


def _run_single_condition(
    condition: Condition,
    config: BenchmarkConfig,
    baseline_elapsed: float | None,
) -> ConditionResult:
    """Run a single benchmark condition.

    Creates the appropriate runner, sets up the datadir, and executes.

    Args:
        condition: Which condition to run.
        config: Benchmark configuration.
        baseline_elapsed: Baseline elapsed time (for overhead calculation).

    Returns:
        ConditionResult with metrics.
    """
    # Create the appropriate runner
    runner = _create_runner(condition, config)

    # Setup datadir with symlinked block files
    datadir = config.datadir_base / condition.value
    runner.setup(datadir, config.block_dir)

    # Execute the condition
    if condition == Condition.BASELINE:
        return runner.run(config.stop_height)
    else:
        return runner.run(config.stop_height, baseline_elapsed=baseline_elapsed)


def _create_runner(condition: Condition, config: BenchmarkConfig):
    """Create the appropriate condition runner.

    Args:
        condition: Which condition to create a runner for.
        config: Benchmark configuration (for bitcoind path).

    Returns:
        Runner instance implementing the condition.

    Raises:
        ValueError: If condition is unknown.
    """
    bitcoind_path = getattr(config, "bitcoind_path", None)

    if condition == Condition.BASELINE:
        return BaselineRunner(bitcoind_path=bitcoind_path)
    elif condition == Condition.EBPF:
        return EbpfRunner(bitcoind_path=bitcoind_path)
    elif condition == Condition.IPC:
        return IpcRunner(bitcoind_path=bitcoind_path)
    elif condition == Condition.CAPNPROTO:
        return CapnProtoSimRunner(bitcoind_path=bitcoind_path)
    else:
        raise ValueError(f"Unknown condition: {condition}")


def _get_docker_image_hash() -> str:
    """Get the Docker image hash if running inside a container.

    Returns:
        Docker image hash string, or "unknown" if not in Docker.
    """
    try:
        cgroup_path = Path("/proc/self/cgroup")
        if cgroup_path.exists():
            content = cgroup_path.read_text()
            # Docker container IDs appear in cgroup paths
            for line in content.split("\n"):
                if "docker" in line or "containerd" in line:
                    parts = line.strip().split("/")
                    if parts:
                        container_id = parts[-1]
                        if len(container_id) >= 12:
                            return container_id[:12]
    except OSError:
        pass
    return "unknown"


def _get_host_info() -> str:
    """Get basic host information for the report.

    Returns:
        String describing the host environment.
    """
    import platform

    parts = [
        platform.system(),
        platform.machine(),
        platform.release(),
    ]
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the reindex benchmark.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    args = parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Parse conditions
    try:
        conditions = parse_conditions(args.conditions)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Build configuration
    try:
        config = BenchmarkConfig(
            block_dir=args.block_dir,
            stop_height=args.stop_height,
            datadir_base=args.datadir,
            flush_caches=not args.no_flush_caches,
            conditions=conditions,
        )
    except ValueError as e:
        print(f"ERROR: Configuration invalid: {e}", file=sys.stderr)
        return 1

    # Store optional bitcoind path on config for runner creation
    if args.bitcoind:
        config.bitcoind_path = args.bitcoind

    # Run the benchmark
    print(f"Reindex Mainnet Benchmark")
    print(f"  Block dir:    {config.block_dir}")
    print(f"  Stop height:  {config.stop_height}")
    print(f"  Conditions:   {', '.join(c.value for c in config.conditions)}")
    print(f"  Cache flush:  {'yes' if config.flush_caches else 'no'}")
    print(f"  Output:       {args.output}")
    print()

    start_time = time.monotonic()
    report, workload_result = run_benchmark(config)
    total_elapsed = time.monotonic() - start_time

    # Print human-readable summary to stdout
    print()
    print("=" * 70)
    print("BENCHMARK RESULTS")
    print("=" * 70)
    print()
    print(format_table(report))
    print()
    print(format_workload_validation(workload_result))
    print()
    print(f"Total benchmark time: {total_elapsed:.1f}s")
    print("=" * 70)

    # Save JSON report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_report = report_to_json(report)
    output_path.write_text(json_report)
    logger.info("JSON report saved to %s", output_path)
    print(f"\nJSON report saved to: {output_path}")

    # Exit with error if all conditions failed
    all_failed = all(
        r.error is not None for r in report.conditions.values()
    )
    if all_failed and report.conditions:
        print("\nERROR: All conditions failed!", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
