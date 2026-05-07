#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Benchmark configuration for the reindex mainnet benchmark.

Defines data models for benchmark configuration, condition results,
and report metadata.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Condition(Enum):
    """Tracing conditions to benchmark."""

    BASELINE = "baseline"
    EBPF = "ebpf"
    IPC = "ipc"
    CAPNPROTO = "capnproto"


# Valid stop_height bounds
MIN_STOP_HEIGHT = 10_000
MAX_STOP_HEIGHT = 50_000


@dataclass
class BenchmarkConfig:
    """Configuration for a reindex benchmark run.

    Attributes:
        block_dir: Path to directory containing mainnet blk*.dat files.
        stop_height: Height at which to stop reindex (-stopatheight value).
        datadir_base: Base directory for per-condition data directories.
        flush_caches: Whether to drop page caches between conditions.
        conditions: Which conditions to run.
    """

    block_dir: Path
    stop_height: int
    datadir_base: Path
    flush_caches: bool = True
    conditions: list[Condition] = field(
        default_factory=lambda: list(Condition)
    )

    def __post_init__(self):
        self.block_dir = Path(self.block_dir)
        self.datadir_base = Path(self.datadir_base)
        validate_stop_height(self.stop_height)


def validate_stop_height(stop_height: int) -> None:
    """Validate that stop_height is within acceptable bounds.

    Args:
        stop_height: The -stopatheight value to validate.

    Raises:
        ValueError: If stop_height is outside [10_000, 50_000].
    """
    if not (MIN_STOP_HEIGHT <= stop_height <= MAX_STOP_HEIGHT):
        raise ValueError(
            f"stop_height must be between {MIN_STOP_HEIGHT} and "
            f"{MAX_STOP_HEIGHT}, got {stop_height}"
        )


@dataclass
class ConditionResult:
    """Result metrics from running a single benchmark condition.

    Attributes:
        name: Condition name (e.g. "baseline", "ebpf").
        elapsed_s: Wall-clock elapsed time in seconds.
        blocks_processed: Number of blocks processed during reindex.
        blocks_per_second: Throughput (blocks_processed / elapsed_s).
        overhead_pct: Percentage overhead relative to baseline (None for baseline).
        event_counts: Per-tracepoint event counts.
        error: Error message if condition failed, None otherwise.
    """

    name: str
    elapsed_s: float
    blocks_processed: int
    blocks_per_second: float
    overhead_pct: float | None = None
    event_counts: dict[str, int] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ReportMetadata:
    """Metadata included in the benchmark report.

    Attributes:
        block_range: Tuple of (start_height, stop_height).
        total_transactions: Total transactions in the processed block range.
        docker_image_hash: Hash of the Docker image used.
        timestamp: ISO 8601 timestamp of the benchmark run.
        host_info: Description of the host environment.
    """

    block_range: tuple[int, int]
    total_transactions: int
    docker_image_hash: str
    timestamp: str
    host_info: str = ""


def compute_blocks_per_second(blocks: int, elapsed_s: float) -> float:
    """Compute throughput as blocks per second.

    Args:
        blocks: Number of blocks processed.
        elapsed_s: Elapsed time in seconds (must be positive).

    Returns:
        Blocks per second.

    Raises:
        ValueError: If elapsed_s <= 0 or blocks < 0.
    """
    if elapsed_s <= 0:
        raise ValueError(f"elapsed_s must be positive, got {elapsed_s}")
    if blocks < 0:
        raise ValueError(f"blocks must be non-negative, got {blocks}")
    return blocks / elapsed_s


def compute_overhead_pct(baseline_time: float, condition_time: float) -> float:
    """Compute overhead percentage relative to baseline.

    overhead_pct = ((condition_time - baseline_time) / baseline_time) * 100

    Args:
        baseline_time: Baseline elapsed time (must be positive).
        condition_time: Condition elapsed time (must be positive).

    Returns:
        Overhead percentage (positive means slower than baseline).

    Raises:
        ValueError: If either time is not positive.
    """
    if baseline_time <= 0:
        raise ValueError(
            f"baseline_time must be positive, got {baseline_time}"
        )
    if condition_time <= 0:
        raise ValueError(
            f"condition_time must be positive, got {condition_time}"
        )
    return ((condition_time - baseline_time) / baseline_time) * 100


def is_competitive(ipc_overhead: float, ebpf_overhead: float) -> bool:
    """Determine if IPC overhead is competitive with eBPF.

    Competitive means IPC overhead <= 2x eBPF overhead.

    Args:
        ipc_overhead: IPC overhead percentage.
        ebpf_overhead: eBPF overhead percentage (must be > 0).

    Returns:
        True if IPC is competitive, False otherwise.
    """
    if ebpf_overhead <= 0:
        # If eBPF has no overhead, IPC can't be "competitive" by ratio
        return ipc_overhead <= 0
    return ipc_overhead <= 2 * ebpf_overhead


def detect_event_discrepancy(ipc_count: int, ebpf_count: int) -> bool:
    """Detect if IPC and eBPF event counts differ by more than 1%.

    Args:
        ipc_count: Total events from IPC condition.
        ebpf_count: Total events from eBPF condition (must be > 0).

    Returns:
        True if discrepancy exceeds 1%, False otherwise.
    """
    if ebpf_count <= 0:
        return False
    return abs(ipc_count - ebpf_count) / ebpf_count > 0.01
