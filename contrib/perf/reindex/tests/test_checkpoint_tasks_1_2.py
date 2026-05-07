#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Checkpoint tests for Tasks 1 and 2 of the reindex mainnet benchmark.

Validates:
- Task 1: Core infrastructure (block validation, config, datadir setup)
- Task 2: Condition runners (baseline, ebpf, ipc, capnproto_sim)

These tests verify the pure logic and data structures without requiring
bitcoind, bpftrace, or Docker.
"""

import json
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # contrib/perf

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
from reindex.datadir_setup import setup_condition_datadir
from reindex.runners import (
    BaselineRunner,
    CapnProtoSimRunner,
    ConditionRunner,
    EbpfRunner,
    IpcRunner,
    ReindexResult,
    TracingMetrics,
)
from reindex.runners.ebpf import (
    BPFTRACE_SCRIPT_TEMPLATE,
    EXPECTED_PROBE_COUNT,
    parse_probe_attachment_count,
    parse_probe_hit_counts,
)


# ============================================================
# Task 1.1: Block Validation Tests
# ============================================================


def _create_fake_blk_file(path: Path, num_blocks: int) -> None:
    """Create a fake blk*.dat file with the given number of blocks."""
    with open(path, "wb") as f:
        for _ in range(num_blocks):
            # Magic bytes
            f.write(MAINNET_MAGIC)
            # Block size (80 bytes = minimal block header)
            block_data = b"\x00" * 80
            f.write(struct.pack("<I", len(block_data)))
            # Block data
            f.write(block_data)


def test_validate_block_files_nonexistent_dir():
    """Block validation returns invalid for nonexistent directory."""
    result = validate_block_files(Path("/nonexistent/path"))
    assert not result.valid
    assert result.block_count == 0
    assert result.file_count == 0
    assert "does not exist" in result.error_message


def test_validate_block_files_empty_dir():
    """Block validation returns invalid for directory with no blk*.dat."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = validate_block_files(Path(tmpdir))
        assert not result.valid
        assert result.block_count == 0
        assert result.file_count == 0
        assert "No blk*.dat" in result.error_message


def test_validate_block_files_insufficient_blocks():
    """Block validation returns invalid when fewer than min_blocks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        blk_path = Path(tmpdir) / "blk00000.dat"
        _create_fake_blk_file(blk_path, 100)
        result = validate_block_files(Path(tmpdir), min_blocks=10_000)
        assert not result.valid
        assert result.block_count == 100
        assert result.file_count == 1
        assert "Insufficient" in result.error_message


def test_validate_block_files_sufficient_blocks():
    """Block validation returns valid when enough blocks present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        blk_path = Path(tmpdir) / "blk00000.dat"
        _create_fake_blk_file(blk_path, 500)
        result = validate_block_files(Path(tmpdir), min_blocks=500)
        assert result.valid
        assert result.block_count == 500
        assert result.file_count == 1
        assert result.error_message is None


def test_validate_block_files_multiple_files():
    """Block validation counts blocks across multiple blk*.dat files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_fake_blk_file(Path(tmpdir) / "blk00000.dat", 300)
        _create_fake_blk_file(Path(tmpdir) / "blk00001.dat", 300)
        result = validate_block_files(Path(tmpdir), min_blocks=500)
        assert result.valid
        assert result.block_count == 600
        assert result.file_count == 2


# ============================================================
# Task 1.2: Configuration Tests
# ============================================================


def test_validate_stop_height_valid():
    """Valid stop_height values are accepted."""
    validate_stop_height(10_000)
    validate_stop_height(25_000)
    validate_stop_height(50_000)


def test_validate_stop_height_too_low():
    """stop_height below minimum raises ValueError."""
    try:
        validate_stop_height(9_999)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "10000" in str(e) or "10_000" in str(e) or "10000" in str(e)


def test_validate_stop_height_too_high():
    """stop_height above maximum raises ValueError."""
    try:
        validate_stop_height(50_001)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "50000" in str(e) or "50_000" in str(e) or "50000" in str(e)


def test_benchmark_config_creation():
    """BenchmarkConfig validates stop_height on creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BenchmarkConfig(
            block_dir=Path(tmpdir),
            stop_height=20_000,
            datadir_base=Path(tmpdir) / "data",
        )
        assert config.stop_height == 20_000
        assert config.flush_caches is True
        assert len(config.conditions) == 4  # All conditions by default


def test_benchmark_config_invalid_height():
    """BenchmarkConfig raises on invalid stop_height."""
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            BenchmarkConfig(
                block_dir=Path(tmpdir),
                stop_height=5_000,
                datadir_base=Path(tmpdir) / "data",
            )
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


def test_condition_enum():
    """Condition enum has all four expected values."""
    assert Condition.BASELINE.value == "baseline"
    assert Condition.EBPF.value == "ebpf"
    assert Condition.IPC.value == "ipc"
    assert Condition.CAPNPROTO.value == "capnproto"
    assert len(Condition) == 4


def test_compute_blocks_per_second():
    """Throughput computation is correct."""
    assert compute_blocks_per_second(1000, 10.0) == 100.0
    assert compute_blocks_per_second(20000, 100.0) == 200.0
    # Edge case: very fast
    assert abs(compute_blocks_per_second(1, 0.001) - 1000.0) < 0.001


def test_compute_blocks_per_second_invalid():
    """Throughput computation rejects invalid inputs."""
    try:
        compute_blocks_per_second(100, 0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    try:
        compute_blocks_per_second(100, -1.0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    try:
        compute_blocks_per_second(-1, 10.0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_compute_overhead_pct():
    """Overhead percentage computation is correct."""
    # 10% overhead
    assert abs(compute_overhead_pct(100.0, 110.0) - 10.0) < 0.001
    # 0% overhead (same time)
    assert abs(compute_overhead_pct(100.0, 100.0) - 0.0) < 0.001
    # Negative overhead (faster than baseline)
    assert abs(compute_overhead_pct(100.0, 90.0) - (-10.0)) < 0.001
    # 100% overhead (2x slower)
    assert abs(compute_overhead_pct(50.0, 100.0) - 100.0) < 0.001


def test_compute_overhead_pct_invalid():
    """Overhead computation rejects non-positive inputs."""
    try:
        compute_overhead_pct(0, 100.0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    try:
        compute_overhead_pct(100.0, 0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_is_competitive():
    """Competitive threshold: IPC overhead <= 2x eBPF overhead."""
    # IPC 3%, eBPF 2% → 3 <= 4 → competitive
    assert is_competitive(3.0, 2.0) is True
    # IPC 4%, eBPF 2% → 4 <= 4 → competitive (boundary)
    assert is_competitive(4.0, 2.0) is True
    # IPC 5%, eBPF 2% → 5 > 4 → not competitive
    assert is_competitive(5.0, 2.0) is False
    # IPC 0%, eBPF 1% → competitive
    assert is_competitive(0.0, 1.0) is True


def test_detect_event_discrepancy():
    """Event discrepancy detection: >1% difference flags."""
    # Exact match → no discrepancy
    assert detect_event_discrepancy(1000, 1000) is False
    # Within 1% → no discrepancy
    assert detect_event_discrepancy(1005, 1000) is False
    # Exactly 1% → no discrepancy (boundary: 10/1000 = 0.01, not > 0.01)
    assert detect_event_discrepancy(1010, 1000) is False
    # Over 1% → discrepancy
    assert detect_event_discrepancy(1011, 1000) is True
    # Under by >1% → discrepancy
    assert detect_event_discrepancy(989, 1000) is True
    # Zero ebpf count → no discrepancy (avoid division by zero)
    assert detect_event_discrepancy(100, 0) is False


# ============================================================
# Task 1.3: Datadir Setup Tests
# ============================================================


def test_setup_condition_datadir():
    """Datadir setup creates directory with symlinked block files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        # Create fake block files
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)
        (block_dir / "blk00001.dat").write_bytes(b"\x00" * 100)
        (block_dir / "rev00000.dat").write_bytes(b"\x00" * 50)

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        datadir = setup_condition_datadir(base, "baseline", block_dir)

        assert datadir.exists()
        assert datadir == base / "baseline"
        assert (datadir / "blocks").exists()
        assert (datadir / "blocks" / "blk00000.dat").is_symlink()
        assert (datadir / "blocks" / "blk00001.dat").is_symlink()
        assert (datadir / "blocks" / "rev00000.dat").is_symlink()


def test_setup_condition_datadir_nonexistent_block_dir():
    """Datadir setup raises FileNotFoundError for missing block_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "datadirs"
        base.mkdir()
        try:
            setup_condition_datadir(base, "test", Path("/nonexistent"))
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass


def test_setup_condition_datadir_no_blk_files():
    """Datadir setup raises ValueError when no blk*.dat files found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        # No blk*.dat files, just some other file
        (block_dir / "other.txt").write_text("hello")

        base = Path(tmpdir) / "datadirs"
        base.mkdir()
        try:
            setup_condition_datadir(base, "test", block_dir)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


def test_setup_condition_datadir_fresh_on_rerun():
    """Datadir setup removes existing directory on re-run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        # First run
        datadir = setup_condition_datadir(base, "test", block_dir)
        # Add a stale file
        (datadir / "stale.txt").write_text("old data")

        # Second run should remove stale file
        datadir = setup_condition_datadir(base, "test", block_dir)
        assert not (datadir / "stale.txt").exists()
        assert (datadir / "blocks" / "blk00000.dat").is_symlink()


# ============================================================
# Task 2.1: Base Runner Protocol Tests
# ============================================================


def test_reindex_result_dataclass():
    """ReindexResult stores expected fields."""
    result = ReindexResult(elapsed_s=45.5, blocks_processed=20000, returncode=0)
    assert result.elapsed_s == 45.5
    assert result.blocks_processed == 20000
    assert result.returncode == 0
    assert result.error is None


def test_reindex_result_with_error():
    """ReindexResult stores error message."""
    result = ReindexResult(
        elapsed_s=1.0, blocks_processed=0, returncode=1, error="crash"
    )
    assert result.error == "crash"
    assert result.returncode == 1


def test_tracing_metrics_dataclass():
    """TracingMetrics stores event counts and probe count."""
    metrics = TracingMetrics(
        event_counts={"block_connected": 100, "utxocache_add": 5000},
        probe_count=20,
    )
    assert metrics.event_counts["block_connected"] == 100
    assert metrics.probe_count == 20


def test_condition_runner_protocol():
    """BaselineRunner satisfies the ConditionRunner protocol."""
    runner = BaselineRunner()
    assert isinstance(runner, ConditionRunner)


# ============================================================
# Task 2.2: Baseline Runner Tests
# ============================================================


def test_baseline_runner_args():
    """Baseline runner returns correct bitcoind args."""
    runner = BaselineRunner()
    args = runner.get_bitcoind_args()
    assert "-stdiobus=off" in args


def test_baseline_runner_tracing_noop():
    """Baseline runner tracing methods are no-ops."""
    runner = BaselineRunner()
    runner.start_tracing(12345)  # Should not raise
    assert runner.verify_tracing_active() is True
    metrics = runner.stop_tracing()
    assert metrics.event_counts == {}
    assert metrics.probe_count == 0


# ============================================================
# Task 2.3: eBPF Runner Tests
# ============================================================


def test_ebpf_runner_args():
    """eBPF runner returns correct bitcoind args."""
    runner = EbpfRunner()
    args = runner.get_bitcoind_args()
    assert "-stdiobus=off" in args


def test_parse_probe_attachment_count():
    """Probe attachment count parsing from bpftrace output."""
    # Standard format
    assert parse_probe_attachment_count("Attaching 20 probes...") == 20
    assert parse_probe_attachment_count("Attaching 1 probe...") == 1
    # Case insensitive
    assert parse_probe_attachment_count("attaching 20 probes") == 20
    # No match
    assert parse_probe_attachment_count("some other output") == 0
    # Embedded in larger output
    output = "Starting bpftrace\nAttaching 20 probes...\nRunning"
    assert parse_probe_attachment_count(output) == 20


def test_parse_probe_hit_counts():
    """Probe hit count parsing from bpftrace output."""
    output = """
@validation_block_connected: 20000
@utxocache_add: 1500000
@utxocache_spent: 1200000
@utxocache_flush: 50
@mempool_added: 0
"""
    counts = parse_probe_hit_counts(output)
    assert counts["validation_block_connected"] == 20000
    assert counts["utxocache_add"] == 1500000
    assert counts["utxocache_spent"] == 1200000
    assert counts["utxocache_flush"] == 50
    assert counts["mempool_added"] == 0


def test_parse_probe_hit_counts_empty():
    """Probe hit count parsing returns empty dict for no matches."""
    assert parse_probe_hit_counts("") == {}
    assert parse_probe_hit_counts("no counters here") == {}


def test_bpftrace_script_template():
    """bpftrace script template covers all 20 probes."""
    script = BPFTRACE_SCRIPT_TEMPLATE.format(binary="/usr/bin/bitcoind")
    # Count usdt: lines (each is a probe)
    probe_lines = [l for l in script.split("\n") if l.strip().startswith("usdt:")]
    assert len(probe_lines) == EXPECTED_PROBE_COUNT


def test_ebpf_runner_verify_not_started():
    """eBPF runner verify returns False when not started."""
    runner = EbpfRunner()
    assert runner.verify_tracing_active() is False


# ============================================================
# Task 2.4: IPC Runner Tests
# ============================================================


def test_ipc_runner_args():
    """IPC runner returns correct bitcoind args."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)

        runner = IpcRunner(ipc_dir=Path("/bitcoin/contrib/tracing/ipc"))
        base = Path(tmpdir) / "datadirs"
        base.mkdir()
        datadir = base / "ipc"
        runner.setup(datadir, block_dir)

        args = runner.get_bitcoind_args()
        assert "-stdiobus=shadow" in args
        assert any("-stdiobusconfig=" in a for a in args)


def test_ipc_runner_config_has_6_workers():
    """IPC runner config contains all 6 workers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)

        runner = IpcRunner(ipc_dir=Path("/bitcoin/contrib/tracing/ipc"))
        base = Path(tmpdir) / "datadirs"
        base.mkdir()
        datadir = base / "ipc"
        runner.setup(datadir, block_dir)

        # Read the generated config
        config_path = base / "ipc" / "stdiobus_trace.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert len(config["pools"]) == 6

        # Verify worker IDs
        worker_ids = {p["id"] for p in config["pools"]}
        expected_ids = {
            "connectblock-benchmark",
            "mempool-monitor",
            "p2p-traffic",
            "p2p-connections",
            "utxocache-utxos",
            "utxocache-flush",
        }
        assert worker_ids == expected_ids


# ============================================================
# Task 2.5: Cap'n Proto Sim Worker Tests
# ============================================================


def test_capnproto_sim_worker_imports():
    """capnproto_sim_worker.py imports without error."""
    import importlib.util

    # Resolve path relative to project root (4 levels up from this test file)
    project_root = Path(__file__).resolve().parents[4]
    worker_path = project_root / "contrib" / "tracing" / "ipc" / "capnproto_sim_worker.py"

    spec = importlib.util.spec_from_file_location(
        "capnproto_sim_worker",
        str(worker_path),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Verify OVERHEAD_US has entries for all expected event types
    assert "block_connected" in module.OVERHEAD_US
    assert module.OVERHEAD_US["block_connected"] == 30
    assert "utxocache_add" in module.OVERHEAD_US
    assert module.OVERHEAD_US["utxocache_add"] == 10
    assert "mempool_added" in module.OVERHEAD_US
    assert module.OVERHEAD_US["mempool_added"] == 6
    assert len(module.OVERHEAD_US) == 20  # All 20 event types


def test_capnproto_sim_worker_busy_wait():
    """busy_wait_us burns approximately the right amount of time."""
    import importlib.util
    import time

    # Resolve path relative to project root (4 levels up from this test file)
    project_root = Path(__file__).resolve().parents[4]
    worker_path = project_root / "contrib" / "tracing" / "ipc" / "capnproto_sim_worker.py"

    spec = importlib.util.spec_from_file_location(
        "capnproto_sim_worker",
        str(worker_path),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Test that busy_wait_us(1000) takes approximately 1ms
    start = time.perf_counter_ns()
    module.busy_wait_us(1000)
    elapsed_us = (time.perf_counter_ns() - start) / 1000

    # Allow generous tolerance (500μs to 5000μs for 1000μs target)
    # CI environments can be slow
    assert elapsed_us >= 500, f"Too fast: {elapsed_us}μs"
    assert elapsed_us < 5000, f"Too slow: {elapsed_us}μs"


# ============================================================
# Task 2.6: Cap'n Proto Sim Runner Tests
# ============================================================


def test_capnproto_sim_runner_args():
    """Cap'n Proto sim runner returns correct bitcoind args."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)

        runner = CapnProtoSimRunner()
        base = Path(tmpdir) / "datadirs"
        base.mkdir()
        datadir = base / "capnproto"
        runner.setup(datadir, block_dir)

        args = runner.get_bitcoind_args()
        assert "-stdiobus=shadow" in args
        assert any("-stdiobusconfig=" in a for a in args)


def test_capnproto_sim_runner_config():
    """Cap'n Proto sim runner config has single worker."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)

        runner = CapnProtoSimRunner()
        base = Path(tmpdir) / "datadirs"
        base.mkdir()
        datadir = base / "capnproto"
        runner.setup(datadir, block_dir)

        config_path = base / "capnproto" / "stdiobus_trace.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert len(config["pools"]) == 1
        assert config["pools"][0]["id"] == "capnproto-sim"
        assert "capnproto_sim_worker.py" in config["pools"][0]["args"][0]


# ============================================================
# Task 2.7: Runners Package Tests
# ============================================================


def test_runners_package_exports():
    """Runners package exports all expected classes."""
    from reindex.runners import (
        BaselineRunner,
        CapnProtoSimRunner,
        ConditionRunner,
        EbpfRunner,
        IpcRunner,
        ReindexResult,
        TracingMetrics,
        run_reindex,
    )
    # All should be importable (already verified by import above)
    assert BaselineRunner is not None
    assert CapnProtoSimRunner is not None
    assert EbpfRunner is not None
    assert IpcRunner is not None


# ============================================================
# ConditionResult and ReportMetadata Tests
# ============================================================


def test_condition_result_dataclass():
    """ConditionResult stores all expected fields."""
    result = ConditionResult(
        name="ebpf",
        elapsed_s=120.5,
        blocks_processed=20000,
        blocks_per_second=166.0,
        overhead_pct=5.2,
        event_counts={"block_connected": 20000},
    )
    assert result.name == "ebpf"
    assert result.overhead_pct == 5.2
    assert result.error is None


def test_report_metadata_dataclass():
    """ReportMetadata stores all expected fields."""
    meta = ReportMetadata(
        block_range=(0, 20000),
        total_transactions=5000000,
        docker_image_hash="sha256:abc123",
        timestamp="2026-05-07T12:00:00Z",
    )
    assert meta.block_range == (0, 20000)
    assert meta.total_transactions == 5000000


# ============================================================
# Run all tests
# ============================================================


def run_all_tests():
    """Run all checkpoint tests and report results."""
    import traceback

    tests = [
        # Task 1.1: Block validation
        test_validate_block_files_nonexistent_dir,
        test_validate_block_files_empty_dir,
        test_validate_block_files_insufficient_blocks,
        test_validate_block_files_sufficient_blocks,
        test_validate_block_files_multiple_files,
        # Task 1.2: Configuration
        test_validate_stop_height_valid,
        test_validate_stop_height_too_low,
        test_validate_stop_height_too_high,
        test_benchmark_config_creation,
        test_benchmark_config_invalid_height,
        test_condition_enum,
        test_compute_blocks_per_second,
        test_compute_blocks_per_second_invalid,
        test_compute_overhead_pct,
        test_compute_overhead_pct_invalid,
        test_is_competitive,
        test_detect_event_discrepancy,
        # Task 1.3: Datadir setup
        test_setup_condition_datadir,
        test_setup_condition_datadir_nonexistent_block_dir,
        test_setup_condition_datadir_no_blk_files,
        test_setup_condition_datadir_fresh_on_rerun,
        # Task 2.1: Base runner
        test_reindex_result_dataclass,
        test_reindex_result_with_error,
        test_tracing_metrics_dataclass,
        test_condition_runner_protocol,
        # Task 2.2: Baseline runner
        test_baseline_runner_args,
        test_baseline_runner_tracing_noop,
        # Task 2.3: eBPF runner
        test_ebpf_runner_args,
        test_parse_probe_attachment_count,
        test_parse_probe_hit_counts,
        test_parse_probe_hit_counts_empty,
        test_bpftrace_script_template,
        test_ebpf_runner_verify_not_started,
        # Task 2.4: IPC runner
        test_ipc_runner_args,
        test_ipc_runner_config_has_6_workers,
        # Task 2.5: Cap'n Proto sim worker
        test_capnproto_sim_worker_imports,
        test_capnproto_sim_worker_busy_wait,
        # Task 2.6: Cap'n Proto sim runner
        test_capnproto_sim_runner_args,
        test_capnproto_sim_runner_config,
        # Task 2.7: Runners package
        test_runners_package_exports,
        # Data classes
        test_condition_result_dataclass,
        test_report_metadata_dataclass,
    ]

    passed = 0
    failed = 0
    errors = []

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
        print("\n✓ All checkpoint tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
