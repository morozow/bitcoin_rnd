#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
End-to-end integration tests for the reindex mainnet benchmark.

Tests the orchestrator with mocked bitcoind for fast CI execution.
Validates:
- Orchestrator runs with synthetic block files
- Baseline condition produces valid ConditionResult
- Report JSON is valid and parseable
- Table formatting aligns columns
- Graceful degradation when a condition fails (e.g., bpftrace not available)

Requirements: 8.1, 8.2, 8.5
"""

import json
import struct
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # contrib/perf

from reindex.block_validation import MAINNET_MAGIC, validate_block_files
from reindex.config import (
    BenchmarkConfig,
    Condition,
    ConditionResult,
    ReportMetadata,
    compute_blocks_per_second,
)
from reindex.report import (
    BenchmarkReport,
    format_table,
    generate_report,
    report_to_json,
)
from reindex.workload_validation import validate_workload


# ============================================================
# Helpers
# ============================================================


def _create_synthetic_blk_file(path: Path, num_blocks: int) -> None:
    """Create a synthetic blk*.dat file with the given number of blocks.

    Uses the real Bitcoin mainnet magic bytes and a minimal 80-byte
    block header as payload.
    """
    with open(path, "wb") as f:
        for _ in range(num_blocks):
            f.write(MAINNET_MAGIC)
            block_data = b"\x01" * 80  # minimal block header
            f.write(struct.pack("<I", len(block_data)))
            f.write(block_data)


def _make_baseline_result(elapsed_s: float = 100.0, blocks: int = 20000):
    """Create a realistic baseline ConditionResult."""
    return ConditionResult(
        name="baseline",
        elapsed_s=elapsed_s,
        blocks_processed=blocks,
        blocks_per_second=compute_blocks_per_second(blocks, elapsed_s),
        overhead_pct=None,
        event_counts={},
    )


def _make_ebpf_result(
    elapsed_s: float = 105.0,
    blocks: int = 20000,
    baseline_elapsed: float = 100.0,
):
    """Create a realistic eBPF ConditionResult."""
    overhead = ((elapsed_s - baseline_elapsed) / baseline_elapsed) * 100
    return ConditionResult(
        name="ebpf",
        elapsed_s=elapsed_s,
        blocks_processed=blocks,
        blocks_per_second=compute_blocks_per_second(blocks, elapsed_s),
        overhead_pct=overhead,
        event_counts={
            "validation_block_connected": blocks,
            "utxocache_add": blocks * 50,
            "utxocache_spent": blocks * 40,
            "utxocache_flush": 10,
            "mempool_added": 0,
        },
    )


def _make_ipc_result(
    elapsed_s: float = 108.0,
    blocks: int = 20000,
    baseline_elapsed: float = 100.0,
):
    """Create a realistic IPC ConditionResult."""
    overhead = ((elapsed_s - baseline_elapsed) / baseline_elapsed) * 100
    return ConditionResult(
        name="ipc",
        elapsed_s=elapsed_s,
        blocks_processed=blocks,
        blocks_per_second=compute_blocks_per_second(blocks, elapsed_s),
        overhead_pct=overhead,
        event_counts={
            "validation_block_connected": blocks,
            "utxocache_add": blocks * 50,
            "utxocache_spent": blocks * 40,
            "utxocache_flush": 10,
            "mempool_added": 0,
        },
    )


def _make_capnproto_result(
    elapsed_s: float = 112.0,
    blocks: int = 20000,
    baseline_elapsed: float = 100.0,
):
    """Create a realistic Cap'n Proto ConditionResult."""
    overhead = ((elapsed_s - baseline_elapsed) / baseline_elapsed) * 100
    return ConditionResult(
        name="capnproto",
        elapsed_s=elapsed_s,
        blocks_processed=blocks,
        blocks_per_second=compute_blocks_per_second(blocks, elapsed_s),
        overhead_pct=overhead,
        event_counts={
            "validation_block_connected": blocks,
            "utxocache_add": blocks * 50,
            "utxocache_spent": blocks * 40,
            "utxocache_flush": 10,
            "mempool_added": 0,
        },
    )


def _make_failed_result(name: str, error: str):
    """Create a failed ConditionResult."""
    return ConditionResult(
        name=name,
        elapsed_s=0,
        blocks_processed=0,
        blocks_per_second=0,
        error=error,
    )


# ============================================================
# Test: Orchestrator runs with synthetic block files
# ============================================================


def test_orchestrator_validates_synthetic_blocks():
    """Orchestrator validates synthetic block files correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        # Create a small synthetic block file (500 blocks)
        _create_synthetic_blk_file(block_dir / "blk00000.dat", 500)

        # Validate with low threshold (for testing)
        result = validate_block_files(block_dir, min_blocks=100)
        assert result.valid
        assert result.block_count == 500
        assert result.file_count == 1

        # Validate with high threshold (should fail)
        result = validate_block_files(block_dir, min_blocks=10_000)
        assert not result.valid
        assert "Insufficient" in result.error_message


# ============================================================
# Test: Baseline condition produces valid ConditionResult
# ============================================================


def test_baseline_produces_valid_condition_result():
    """Baseline condition produces a ConditionResult with correct fields."""
    result = _make_baseline_result(elapsed_s=95.5, blocks=20000)

    assert result.name == "baseline"
    assert result.elapsed_s == 95.5
    assert result.blocks_processed == 20000
    assert abs(result.blocks_per_second - (20000 / 95.5)) < 0.01
    assert result.overhead_pct is None  # Baseline has no overhead
    assert result.error is None
    assert isinstance(result.event_counts, dict)


def test_baseline_runner_with_mocked_bitcoind():
    """Baseline runner produces valid result when bitcoind is mocked.

    Mocks subprocess.Popen to simulate a successful bitcoind -reindex
    that completes in a short time.
    """
    from reindex.runners.baseline import BaselineRunner
    from reindex.runners.base import ReindexResult

    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)

        runner = BaselineRunner(bitcoind_path=Path("/fake/bitcoind"))
        base = Path(tmpdir) / "datadirs"
        base.mkdir()
        datadir = base / "baseline"

        runner.setup(datadir, block_dir)

        # Mock run_reindex to return a successful result
        mock_result = ReindexResult(
            elapsed_s=50.0,
            blocks_processed=20000,
            returncode=0,
        )

        with patch(
            "reindex.runners.baseline.run_reindex", return_value=mock_result
        ):
            result = runner.run(stop_height=20000)

        assert result.name == "baseline"
        assert result.elapsed_s == 50.0
        assert result.blocks_processed == 20000
        assert abs(result.blocks_per_second - 400.0) < 0.01
        assert result.overhead_pct is None
        assert result.error is None


# ============================================================
# Test: Report JSON is valid and parseable
# ============================================================


def test_report_json_valid_and_parseable():
    """Generated JSON report is valid JSON with all required fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BenchmarkConfig(
            block_dir=Path(tmpdir),
            stop_height=20000,
            datadir_base=Path(tmpdir) / "data",
            conditions=[Condition.BASELINE, Condition.EBPF, Condition.IPC],
        )

        results = {
            "baseline": _make_baseline_result(),
            "ebpf": _make_ebpf_result(),
            "ipc": _make_ipc_result(),
        }

        metadata = ReportMetadata(
            block_range=(0, 20000),
            total_transactions=5_000_000,
            docker_image_hash="sha256:abc123def456",
            timestamp="2026-05-07T12:00:00Z",
            host_info="Linux x86_64 6.1.0",
        )

        report = generate_report(config, results, metadata)
        json_str = report_to_json(report)

        # Must be valid JSON
        parsed = json.loads(json_str)

        # Check metadata fields
        assert "metadata" in parsed
        assert parsed["metadata"]["block_range"] == [0, 20000]
        assert parsed["metadata"]["total_transactions"] == 5_000_000
        assert parsed["metadata"]["docker_image_hash"] == "sha256:abc123def456"
        assert parsed["metadata"]["timestamp"] == "2026-05-07T12:00:00Z"
        assert parsed["metadata"]["host_info"] == "Linux x86_64 6.1.0"

        # Check conditions
        assert "conditions" in parsed
        assert "baseline" in parsed["conditions"]
        assert "ebpf" in parsed["conditions"]
        assert "ipc" in parsed["conditions"]

        # Each condition has required fields
        for cond_name, cond_data in parsed["conditions"].items():
            assert "name" in cond_data
            assert "elapsed_s" in cond_data
            assert "blocks_processed" in cond_data
            assert "blocks_per_second" in cond_data
            assert "overhead_pct" in cond_data
            assert "event_counts" in cond_data

        # Baseline has no overhead
        assert parsed["conditions"]["baseline"]["overhead_pct"] is None

        # eBPF and IPC have overhead
        assert parsed["conditions"]["ebpf"]["overhead_pct"] is not None
        assert parsed["conditions"]["ipc"]["overhead_pct"] is not None

        # Check top-level flags
        assert "competitive" in parsed
        assert "event_parity" in parsed
        assert isinstance(parsed["competitive"], bool)
        assert isinstance(parsed["event_parity"], bool)


def test_report_json_with_partial_results():
    """Report JSON handles partial results (failed conditions)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BenchmarkConfig(
            block_dir=Path(tmpdir),
            stop_height=20000,
            datadir_base=Path(tmpdir) / "data",
            conditions=[
                Condition.BASELINE,
                Condition.EBPF,
                Condition.IPC,
                Condition.CAPNPROTO,
            ],
        )

        results = {
            "baseline": _make_baseline_result(),
            "ebpf": _make_failed_result("ebpf", "bpftrace not found"),
            "ipc": _make_ipc_result(),
            "capnproto": _make_failed_result(
                "capnproto", "Worker failed to start"
            ),
        }

        report = generate_report(config, results)
        json_str = report_to_json(report)
        parsed = json.loads(json_str)

        # All conditions present in report
        assert len(parsed["conditions"]) == 4

        # Failed conditions have error field
        assert "error" in parsed["conditions"]["ebpf"]
        assert parsed["conditions"]["ebpf"]["error"] == "bpftrace not found"
        assert "error" in parsed["conditions"]["capnproto"]

        # Successful conditions don't have error field
        assert "error" not in parsed["conditions"]["baseline"]
        assert "error" not in parsed["conditions"]["ipc"]

        # competitive is False when eBPF failed
        assert parsed["competitive"] is False


def test_report_json_all_four_conditions():
    """Report JSON includes all four conditions when all succeed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BenchmarkConfig(
            block_dir=Path(tmpdir),
            stop_height=20000,
            datadir_base=Path(tmpdir) / "data",
        )

        results = {
            "baseline": _make_baseline_result(),
            "ebpf": _make_ebpf_result(),
            "ipc": _make_ipc_result(),
            "capnproto": _make_capnproto_result(),
        }

        report = generate_report(config, results)
        json_str = report_to_json(report)
        parsed = json.loads(json_str)

        assert len(parsed["conditions"]) == 4
        assert set(parsed["conditions"].keys()) == {
            "baseline",
            "ebpf",
            "ipc",
            "capnproto",
        }

        # IPC overhead (8%) <= 2 * eBPF overhead (5%) = 10% → competitive
        assert parsed["competitive"] is True
        # Event counts match → parity
        assert parsed["event_parity"] is True


# ============================================================
# Test: Table formatting aligns columns
# ============================================================


def test_table_formatting_aligns_columns():
    """Table output has aligned columns with consistent widths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BenchmarkConfig(
            block_dir=Path(tmpdir),
            stop_height=20000,
            datadir_base=Path(tmpdir) / "data",
        )

        results = {
            "baseline": _make_baseline_result(),
            "ebpf": _make_ebpf_result(),
            "ipc": _make_ipc_result(),
            "capnproto": _make_capnproto_result(),
        }

        metadata = ReportMetadata(
            block_range=(0, 20000),
            total_transactions=5_000_000,
            docker_image_hash="sha256:abc123",
            timestamp="2026-05-07T12:00:00Z",
        )

        report = generate_report(config, results, metadata)
        table = format_table(report)

        # Table should not be empty
        assert len(table) > 0

        # Split into lines
        lines = table.split("\n")

        # First line is header, second is separator
        assert lines[0].startswith("|")
        assert lines[1].startswith("|")

        # Header contains expected column names
        header = lines[0]
        assert "Condition" in header
        assert "Time(s)" in header
        assert "Blocks/s" in header
        assert "Overhead%" in header
        assert "Events" in header
        assert "Status" in header

        # Separator line uses dashes
        assert "-" in lines[1]

        # Data rows (lines 2-5) should all start with |
        data_lines = [l for l in lines[2:] if l.startswith("|")]
        assert len(data_lines) == 4  # 4 conditions

        # All pipe-delimited lines should have the same number of pipes
        pipe_counts = [l.count("|") for l in [lines[0]] + data_lines]
        assert len(set(pipe_counts)) == 1, (
            f"Inconsistent pipe counts: {pipe_counts}"
        )

        # All conditions appear in the table
        table_text = "\n".join(data_lines)
        assert "baseline" in table_text
        assert "ebpf" in table_text
        assert "ipc" in table_text
        assert "capnproto" in table_text

        # Footer contains block range and timestamp
        assert "Block range: 0-20000" in table
        assert "2026-05-07T12:00:00Z" in table

        # Competitive status appears
        assert "COMPETITIVE" in table


def test_table_formatting_with_failed_condition():
    """Table shows FAILED status for conditions that errored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BenchmarkConfig(
            block_dir=Path(tmpdir),
            stop_height=20000,
            datadir_base=Path(tmpdir) / "data",
        )

        results = {
            "baseline": _make_baseline_result(),
            "ebpf": _make_failed_result("ebpf", "bpftrace not available"),
            "ipc": _make_ipc_result(),
        }

        report = generate_report(config, results)
        table = format_table(report)

        # Failed condition shows FAILED
        assert "FAILED" in table
        assert "bpftrace not available" in table

        # Successful conditions show OK
        assert "OK" in table


def test_table_formatting_empty_results():
    """Table handles empty results gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BenchmarkConfig(
            block_dir=Path(tmpdir),
            stop_height=20000,
            datadir_base=Path(tmpdir) / "data",
        )

        report = generate_report(config, {})
        table = format_table(report)

        assert "No results to display" in table


# ============================================================
# Test: Graceful degradation when a condition fails
# ============================================================


def test_graceful_degradation_bpftrace_unavailable():
    """Benchmark continues when eBPF condition fails (bpftrace not found).

    Simulates the scenario where bpftrace is not installed or not
    accessible, which is common in CI environments.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BenchmarkConfig(
            block_dir=Path(tmpdir),
            stop_height=20000,
            datadir_base=Path(tmpdir) / "data",
            conditions=[Condition.BASELINE, Condition.EBPF, Condition.IPC],
        )

        # Simulate: baseline succeeds, ebpf fails, ipc succeeds
        results = {
            "baseline": _make_baseline_result(),
            "ebpf": _make_failed_result(
                "ebpf", "bpftrace attachment failed: command not found"
            ),
            "ipc": _make_ipc_result(),
        }

        report = generate_report(config, results)

        # Report includes all conditions
        assert "baseline" in report.conditions
        assert "ebpf" in report.conditions
        assert "ipc" in report.conditions

        # Failed condition has error
        assert report.conditions["ebpf"].error is not None
        assert "bpftrace" in report.conditions["ebpf"].error

        # Successful conditions have valid data
        assert report.conditions["baseline"].error is None
        assert report.conditions["baseline"].blocks_per_second > 0
        assert report.conditions["ipc"].error is None
        assert report.conditions["ipc"].blocks_per_second > 0

        # competitive is False (eBPF failed, can't compare)
        assert report.competitive is False

        # JSON report is still valid
        json_str = report_to_json(report)
        parsed = json.loads(json_str)
        assert len(parsed["conditions"]) == 3


def test_graceful_degradation_all_tracing_fails():
    """Benchmark produces valid report even when all tracing conditions fail."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BenchmarkConfig(
            block_dir=Path(tmpdir),
            stop_height=20000,
            datadir_base=Path(tmpdir) / "data",
        )

        results = {
            "baseline": _make_baseline_result(),
            "ebpf": _make_failed_result("ebpf", "bpftrace not found"),
            "ipc": _make_failed_result("ipc", "stdio_bus not compiled"),
            "capnproto": _make_failed_result("capnproto", "worker crash"),
        }

        report = generate_report(config, results)

        # Report is still valid
        assert len(report.conditions) == 4
        assert report.conditions["baseline"].error is None
        assert report.competitive is False

        # JSON is valid
        json_str = report_to_json(report)
        parsed = json.loads(json_str)
        assert parsed["conditions"]["baseline"]["elapsed_s"] > 0

        # Table is valid
        table = format_table(report)
        assert "baseline" in table
        assert "FAILED" in table


def test_graceful_degradation_baseline_fails():
    """Report handles baseline failure (all overheads become None)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BenchmarkConfig(
            block_dir=Path(tmpdir),
            stop_height=20000,
            datadir_base=Path(tmpdir) / "data",
        )

        results = {
            "baseline": _make_failed_result("baseline", "bitcoind crash"),
            "ebpf": ConditionResult(
                name="ebpf",
                elapsed_s=105.0,
                blocks_processed=20000,
                blocks_per_second=190.5,
                overhead_pct=None,  # Can't compute without baseline
            ),
        }

        report = generate_report(config, results)
        json_str = report_to_json(report)
        parsed = json.loads(json_str)

        # Baseline has error
        assert "error" in parsed["conditions"]["baseline"]
        # eBPF has no overhead (baseline failed)
        assert parsed["conditions"]["ebpf"]["overhead_pct"] is None


# ============================================================
# Test: Workload validation integration
# ============================================================


def test_workload_validation_with_full_results():
    """Workload validation works with a complete set of results."""
    results = {
        "baseline": _make_baseline_result(),
        "ebpf": _make_ebpf_result(),
        "ipc": _make_ipc_result(),
    }

    validation = validate_workload(results)

    # Per-condition events are logged
    assert "ebpf" in validation.per_condition_events
    assert "ipc" in validation.per_condition_events
    assert validation.per_condition_events["ebpf"] > 0
    assert validation.per_condition_events["ipc"] > 0

    # Event parity (our mock data has matching counts)
    assert validation.event_discrepancy is False

    # Per-tracepoint events are recorded
    assert "ebpf" in validation.per_tracepoint_events
    assert "ipc" in validation.per_tracepoint_events


def test_workload_validation_detects_discrepancy():
    """Workload validation flags event count discrepancy >1%."""
    results = {
        "baseline": _make_baseline_result(),
        "ebpf": ConditionResult(
            name="ebpf",
            elapsed_s=105.0,
            blocks_processed=20000,
            blocks_per_second=190.5,
            overhead_pct=5.0,
            event_counts={"validation_block_connected": 20000},
        ),
        "ipc": ConditionResult(
            name="ipc",
            elapsed_s=108.0,
            blocks_processed=20000,
            blocks_per_second=185.2,
            overhead_pct=8.0,
            # 15% fewer events than eBPF → discrepancy
            event_counts={"validation_block_connected": 17000},
        ),
    }

    validation = validate_workload(results)
    assert validation.event_discrepancy is True
    assert len(validation.warnings) > 0
    assert any("discrepancy" in w.lower() for w in validation.warnings)


# ============================================================
# Test: Full orchestrator flow with mocked subprocess
# ============================================================


def test_orchestrator_full_flow_mocked():
    """Full orchestrator flow with mocked bitcoind subprocess.

    Verifies the complete pipeline: config → validate → run → report.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        # Create enough synthetic blocks to pass validation
        _create_synthetic_blk_file(block_dir / "blk00000.dat", 12000)

        config = BenchmarkConfig(
            block_dir=block_dir,
            stop_height=10000,
            datadir_base=Path(tmpdir) / "data",
            flush_caches=False,
            conditions=[Condition.BASELINE],
        )

        # Validate blocks
        validation = validate_block_files(block_dir, min_blocks=10000)
        assert validation.valid
        assert validation.block_count == 12000

        # Simulate running baseline with mocked result
        results = {"baseline": _make_baseline_result(elapsed_s=50.0, blocks=10000)}

        # Generate report
        metadata = ReportMetadata(
            block_range=(0, 10000),
            total_transactions=1_000_000,
            docker_image_hash="test-image-hash",
            timestamp="2026-05-07T10:00:00Z",
        )
        report = generate_report(config, results, metadata)

        # Verify report
        assert report.metadata.block_range == (0, 10000)
        assert "baseline" in report.conditions
        assert report.conditions["baseline"].blocks_per_second == 200.0

        # Verify JSON output
        json_str = report_to_json(report)
        parsed = json.loads(json_str)
        assert parsed["metadata"]["block_range"] == [0, 10000]
        assert parsed["conditions"]["baseline"]["blocks_per_second"] == 200.0

        # Verify table output
        table = format_table(report)
        assert "baseline" in table
        assert "200.0" in table


def test_orchestrator_parse_conditions():
    """Orchestrator correctly parses condition strings."""
    # Import from the orchestrator module
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # contrib/perf
    from run_reindex_benchmark import parse_conditions

    # Valid conditions
    conditions = parse_conditions("baseline,ebpf,ipc,capnproto")
    assert len(conditions) == 4
    assert Condition.BASELINE in conditions
    assert Condition.EBPF in conditions
    assert Condition.IPC in conditions
    assert Condition.CAPNPROTO in conditions

    # Subset
    conditions = parse_conditions("baseline,ipc")
    assert len(conditions) == 2

    # With whitespace
    conditions = parse_conditions(" baseline , ebpf ")
    assert len(conditions) == 2

    # Invalid condition
    try:
        parse_conditions("baseline,invalid")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid" in str(e).lower()

    # Empty string
    try:
        parse_conditions("")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "at least one" in str(e).lower()


def test_orchestrator_parse_args():
    """Orchestrator correctly parses CLI arguments."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # contrib/perf
    from run_reindex_benchmark import parse_args

    args = parse_args([
        "--block-dir", "/tmp/blocks",
        "--stop-height", "15000",
        "--conditions", "baseline,ebpf",
        "--output", "/tmp/report.json",
        "--no-flush-caches",
    ])

    assert args.block_dir == Path("/tmp/blocks")
    assert args.stop_height == 15000
    assert args.conditions == "baseline,ebpf"
    assert args.output == Path("/tmp/report.json")
    assert args.no_flush_caches is True


# ============================================================
# Run all tests
# ============================================================


def run_all_tests():
    """Run all integration tests and report results."""
    import traceback

    tests = [
        # Orchestrator with synthetic blocks
        test_orchestrator_validates_synthetic_blocks,
        # Baseline condition
        test_baseline_produces_valid_condition_result,
        test_baseline_runner_with_mocked_bitcoind,
        # Report JSON
        test_report_json_valid_and_parseable,
        test_report_json_with_partial_results,
        test_report_json_all_four_conditions,
        # Table formatting
        test_table_formatting_aligns_columns,
        test_table_formatting_with_failed_condition,
        test_table_formatting_empty_results,
        # Graceful degradation
        test_graceful_degradation_bpftrace_unavailable,
        test_graceful_degradation_all_tracing_fails,
        test_graceful_degradation_baseline_fails,
        # Workload validation
        test_workload_validation_with_full_results,
        test_workload_validation_detects_discrepancy,
        # Full orchestrator flow
        test_orchestrator_full_flow_mocked,
        test_orchestrator_parse_conditions,
        test_orchestrator_parse_args,
    ]

    passed = 0
    failed = 0
    errors = []

    print("Running integration tests...")
    print("=" * 60)

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
            print(f"  ✓ {test_fn.__name__}")
        except Exception as e:
            failed += 1
            errors.append((test_fn.__name__, e))
            print(f"  ✗ {test_fn.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'='*60}")

    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")
        return 1
    else:
        print("\n✓ All integration tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
