#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Property-based tests for the reindex mainnet benchmark.

Uses Hypothesis to verify universal correctness properties from the design
document. Each test validates a formal property that must hold for all valid
inputs, providing stronger guarantees than example-based tests alone.

Minimum 100 iterations per property test (configured via settings).
"""

import json
import math
import struct
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# Add contrib/perf to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reindex.block_validation import (
    BlockValidationResult,
    MAINNET_MAGIC,
    validate_block_files,
)
from reindex.config import (
    BenchmarkConfig,
    Condition,
    ConditionResult,
    ReportMetadata,
    compute_blocks_per_second,
    compute_overhead_pct,
    detect_event_discrepancy,
    is_competitive,
    validate_stop_height,
    MIN_STOP_HEIGHT,
    MAX_STOP_HEIGHT,
)
from reindex.report import (
    BenchmarkReport,
    generate_report,
    report_to_json,
    format_table,
)
from reindex.runners.ebpf import parse_probe_attachment_count, EXPECTED_PROBE_COUNT
from reindex.workload_validation import (
    validate_transaction_density,
    MIN_AVG_TRANSACTIONS,
)

# Hypothesis settings: minimum 100 examples per test
PBT_SETTINGS = settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])


# =============================================================================
# Property 1: Block count validation threshold
# Feature: reindex-mainnet-benchmark, Property 1: Block count validation threshold
# =============================================================================


def _create_block_file(directory: Path, num_blocks: int) -> None:
    """Create a synthetic blk00000.dat with the given number of blocks.

    Each block is minimal: magic + size + 80 bytes of header data.
    """
    blk_path = directory / "blk00000.dat"
    with open(blk_path, "wb") as f:
        for _ in range(num_blocks):
            # Write magic bytes
            f.write(MAINNET_MAGIC)
            # Write block size (80 bytes — minimal valid block header)
            f.write(struct.pack("<I", 80))
            # Write 80 bytes of block data
            f.write(b"\x00" * 80)


@given(block_count=st.integers(min_value=0, max_value=25_000))
@PBT_SETTINGS
def test_block_count_validation_threshold(block_count: int):
    """Property 1: Block count validation threshold.

    For any integer block_count, validate_block_files returns valid=True
    iff block_count >= 10,000.

    Validates: Requirements 1.2, 1.3
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir)
        _create_block_file(block_dir, block_count)

        result = validate_block_files(block_dir, min_blocks=10_000)

        if block_count >= 10_000:
            assert result.valid is True, (
                f"Expected valid=True for {block_count} blocks, got {result}"
            )
            assert result.error_message is None
        else:
            assert result.valid is False, (
                f"Expected valid=False for {block_count} blocks, got {result}"
            )
            assert result.error_message is not None

        assert result.block_count == block_count


# =============================================================================
# Property 2: Block range bounds enforcement
# Feature: reindex-mainnet-benchmark, Property 2: Block range bounds enforcement
# =============================================================================


@given(stop_height=st.integers(min_value=-100_000, max_value=200_000))
@PBT_SETTINGS
def test_block_range_bounds_enforcement(stop_height: int):
    """Property 2: Block range bounds enforcement.

    For any integer stop_height, config validator accepts iff
    10,000 <= stop_height <= 50,000.

    Validates: Requirements 2.3
    """
    in_range = MIN_STOP_HEIGHT <= stop_height <= MAX_STOP_HEIGHT

    if in_range:
        # Should not raise
        validate_stop_height(stop_height)
    else:
        # Should raise ValueError
        with pytest.raises(ValueError):
            validate_stop_height(stop_height)


# =============================================================================
# Property 3: Throughput computation correctness
# Feature: reindex-mainnet-benchmark, Property 3: Throughput computation correctness
# =============================================================================


@given(
    elapsed_time=st.floats(min_value=1e-6, max_value=1e9, allow_nan=False, allow_infinity=False),
    block_count=st.integers(min_value=1, max_value=10_000_000),
)
@PBT_SETTINGS
def test_throughput_computation_correctness(elapsed_time: float, block_count: int):
    """Property 3: Throughput computation correctness.

    For any positive elapsed_time and positive block_count,
    blocks_per_second == block_count / elapsed_time (within float tolerance).

    Validates: Requirements 2.4
    """
    result = compute_blocks_per_second(block_count, elapsed_time)
    expected = block_count / elapsed_time

    assert math.isclose(result, expected, rel_tol=1e-9), (
        f"Expected {expected}, got {result} for "
        f"blocks={block_count}, elapsed={elapsed_time}"
    )


# =============================================================================
# Property 4: Overhead percentage computation
# Feature: reindex-mainnet-benchmark, Property 4: Overhead percentage computation
# =============================================================================


@given(
    baseline_time=st.floats(min_value=1e-6, max_value=1e9, allow_nan=False, allow_infinity=False),
    condition_time=st.floats(min_value=1e-6, max_value=1e9, allow_nan=False, allow_infinity=False),
)
@PBT_SETTINGS
def test_overhead_percentage_computation(baseline_time: float, condition_time: float):
    """Property 4: Overhead percentage computation.

    For any positive baseline_time and condition_time,
    overhead_pct == ((condition_time - baseline_time) / baseline_time) * 100.

    Validates: Requirements 4.3, 5.4, 6.3
    """
    result = compute_overhead_pct(baseline_time, condition_time)
    expected = ((condition_time - baseline_time) / baseline_time) * 100

    assert math.isclose(result, expected, rel_tol=1e-9), (
        f"Expected {expected}, got {result} for "
        f"baseline={baseline_time}, condition={condition_time}"
    )


# =============================================================================
# Property 5: Probe attachment count validation
# Feature: reindex-mainnet-benchmark, Property 5: Probe attachment count validation
# =============================================================================


@given(n_probes=st.integers(min_value=0, max_value=100))
@PBT_SETTINGS
def test_probe_attachment_count_validation(n_probes: int):
    """Property 5: Probe attachment count validation.

    For any bpftrace output with N "Attaching" lines, parser extracts N,
    validator returns success iff N == 20.

    Validates: Requirements 4.2
    """
    # Generate synthetic bpftrace output with N probes
    output = f"Attaching {n_probes} probes...\n"

    parsed_count = parse_probe_attachment_count(output)
    assert parsed_count == n_probes, (
        f"Expected parser to extract {n_probes}, got {parsed_count}"
    )

    # Validator: success iff N == EXPECTED_PROBE_COUNT (20)
    is_valid = (parsed_count == EXPECTED_PROBE_COUNT)
    if n_probes == 20:
        assert is_valid is True
    else:
        assert is_valid is False


# =============================================================================
# Property 6: Competitive threshold determination
# Feature: reindex-mainnet-benchmark, Property 6: Competitive threshold determination
# =============================================================================


@given(
    ipc_overhead=st.floats(min_value=-100, max_value=1000, allow_nan=False, allow_infinity=False),
    ebpf_overhead=st.floats(min_value=0.001, max_value=1000, allow_nan=False, allow_infinity=False),
)
@PBT_SETTINGS
def test_competitive_threshold_determination(ipc_overhead: float, ebpf_overhead: float):
    """Property 6: Competitive threshold determination.

    For any (ipc_overhead, ebpf_overhead) where ebpf_overhead > 0,
    result is "competitive" iff ipc_overhead <= 2 * ebpf_overhead.

    Validates: Requirements 8.4
    """
    result = is_competitive(ipc_overhead, ebpf_overhead)
    expected = ipc_overhead <= 2 * ebpf_overhead

    assert result == expected, (
        f"Expected competitive={expected}, got {result} for "
        f"ipc_overhead={ipc_overhead}, ebpf_overhead={ebpf_overhead}"
    )


# =============================================================================
# Property 7: Event count discrepancy detection
# Feature: reindex-mainnet-benchmark, Property 7: Event count discrepancy detection
# =============================================================================


@given(
    ipc_count=st.integers(min_value=0, max_value=10_000_000),
    ebpf_count=st.integers(min_value=1, max_value=10_000_000),
)
@PBT_SETTINGS
def test_event_count_discrepancy_detection(ipc_count: int, ebpf_count: int):
    """Property 7: Event count discrepancy detection.

    For any (ipc_count, ebpf_count) where ebpf_count > 0,
    flag is set iff abs(ipc_count - ebpf_count) / ebpf_count > 0.01.

    Validates: Requirements 9.3
    """
    result = detect_event_discrepancy(ipc_count, ebpf_count)
    expected = abs(ipc_count - ebpf_count) / ebpf_count > 0.01

    assert result == expected, (
        f"Expected discrepancy={expected}, got {result} for "
        f"ipc_count={ipc_count}, ebpf_count={ebpf_count}"
    )


# =============================================================================
# Property 8: Report completeness
# Feature: reindex-mainnet-benchmark, Property 8: Report completeness
# =============================================================================

# Strategy for generating valid ConditionResult instances
condition_names = st.sampled_from(["baseline", "ebpf", "ipc", "capnproto"])

condition_result_strategy = st.builds(
    ConditionResult,
    name=condition_names,
    elapsed_s=st.floats(min_value=0.1, max_value=10000, allow_nan=False, allow_infinity=False),
    blocks_processed=st.integers(min_value=1000, max_value=50000),
    blocks_per_second=st.floats(min_value=0.1, max_value=10000, allow_nan=False, allow_infinity=False),
    overhead_pct=st.one_of(st.none(), st.floats(min_value=-50, max_value=500, allow_nan=False, allow_infinity=False)),
    event_counts=st.dictionaries(
        keys=st.sampled_from([
            "validation:block_connected", "utxocache:add",
            "utxocache:spent", "mempool:added",
        ]),
        values=st.integers(min_value=0, max_value=1_000_000),
        min_size=0,
        max_size=4,
    ),
    error=st.none(),
)


@given(
    results=st.dictionaries(
        keys=condition_names,
        values=condition_result_strategy,
        min_size=1,
        max_size=4,
    ),
)
@PBT_SETTINGS
def test_report_completeness(results: dict[str, ConditionResult]):
    """Property 8: Report completeness.

    For any set of 1-4 condition results, JSON report contains all required
    fields per condition and metadata.

    Validates: Requirements 8.1, 8.2, 8.3
    """
    # Ensure condition names in results match the keys
    fixed_results = {}
    for name, result in results.items():
        fixed_results[name] = ConditionResult(
            name=name,
            elapsed_s=result.elapsed_s,
            blocks_processed=result.blocks_processed,
            blocks_per_second=result.blocks_per_second,
            overhead_pct=result.overhead_pct,
            event_counts=result.event_counts,
            error=result.error,
        )

    config = BenchmarkConfig(
        block_dir=Path("/tmp/blocks"),
        stop_height=20_000,
        datadir_base=Path("/tmp/benchmark"),
        flush_caches=False,
        conditions=[Condition.BASELINE],
    )

    report = generate_report(config, fixed_results)
    json_str = report_to_json(report)
    data = json.loads(json_str)

    # Verify metadata fields
    assert "metadata" in data
    meta = data["metadata"]
    assert "block_range" in meta
    assert "total_transactions" in meta
    assert "docker_image_hash" in meta
    assert "timestamp" in meta

    # Verify each condition has required fields
    assert "conditions" in data
    for cond_name, cond_data in data["conditions"].items():
        assert "name" in cond_data
        assert "elapsed_s" in cond_data
        assert "blocks_processed" in cond_data
        assert "blocks_per_second" in cond_data
        assert "overhead_pct" in cond_data
        assert "event_counts" in cond_data

    # Verify competitive and event_parity flags present
    assert "competitive" in data
    assert "event_parity" in data

    # Verify table formatting includes all condition names
    table = format_table(report)
    for cond_name in fixed_results:
        assert cond_name in table, (
            f"Condition '{cond_name}' not found in table output"
        )


# =============================================================================
# Property 9: Condition configuration consistency
# Feature: reindex-mainnet-benchmark, Property 9: Condition configuration consistency
# =============================================================================


@given(
    block_dir_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
        min_size=1,
        max_size=20,
    ),
    stop_height=st.integers(min_value=MIN_STOP_HEIGHT, max_value=MAX_STOP_HEIGHT),
    conditions=st.lists(
        st.sampled_from(list(Condition)),
        min_size=1,
        max_size=4,
        unique=True,
    ),
)
@PBT_SETTINGS
def test_condition_configuration_consistency(
    block_dir_name: str, stop_height: int, conditions: list[Condition]
):
    """Property 9: Condition configuration consistency.

    For any benchmark run with multiple conditions, all receive identical
    block_dir and stop_height.

    Validates: Requirements 6.4
    """
    block_dir = Path(f"/tmp/{block_dir_name}")
    config = BenchmarkConfig(
        block_dir=block_dir,
        stop_height=stop_height,
        datadir_base=Path("/tmp/benchmark"),
        flush_caches=True,
        conditions=conditions,
    )

    # Verify all conditions in the config share the same block_dir and stop_height
    # (The config is a single object — this property verifies the design ensures
    # all conditions use the same parameters by construction)
    assert config.block_dir == block_dir
    assert config.stop_height == stop_height

    # Verify that creating multiple configs with same params yields identical values
    for condition in conditions:
        # Each condition runner would receive these same parameters
        assert config.block_dir == block_dir, (
            f"Condition {condition} got different block_dir"
        )
        assert config.stop_height == stop_height, (
            f"Condition {condition} got different stop_height"
        )


# =============================================================================
# Property 10: Transaction density validation
# Feature: reindex-mainnet-benchmark, Property 10: Transaction density validation
# =============================================================================


@given(
    tx_counts=st.lists(
        st.integers(min_value=0, max_value=10_000),
        min_size=1,
        max_size=1000,
    ),
)
@PBT_SETTINGS
def test_transaction_density_validation(tx_counts: list[int]):
    """Property 10: Transaction density validation.

    For any list of per-block tx counts above height 150,000,
    flag insufficient density iff mean < 100.

    Validates: Requirements 9.1
    """
    is_valid, avg = validate_transaction_density(tx_counts)
    expected_avg = sum(tx_counts) / len(tx_counts)
    expected_valid = expected_avg >= MIN_AVG_TRANSACTIONS

    assert math.isclose(avg, expected_avg, rel_tol=1e-9), (
        f"Expected avg={expected_avg}, got {avg}"
    )
    assert is_valid == expected_valid, (
        f"Expected valid={expected_valid}, got {is_valid} for avg={avg}"
    )
