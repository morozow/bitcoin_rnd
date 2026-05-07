#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Tests for report generation and workload validation modules.
"""

import json
import sys
from pathlib import Path

# Add the contrib/perf directory to path so 'reindex' package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reindex.config import (
    BenchmarkConfig,
    ConditionResult,
    ReportMetadata,
)
from reindex.report import (
    BenchmarkReport,
    format_table,
    generate_report,
    report_to_json,
)
from reindex.workload_validation import (
    validate_transaction_density,
    validate_workload,
    format_workload_validation,
)


def make_config() -> BenchmarkConfig:
    return BenchmarkConfig(
        block_dir=Path("/blocks"),
        stop_height=20000,
        datadir_base=Path("/benchmark"),
    )


def make_results() -> dict[str, ConditionResult]:
    return {
        "baseline": ConditionResult(
            name="baseline",
            elapsed_s=100.0,
            blocks_processed=20000,
            blocks_per_second=200.0,
            overhead_pct=None,
            event_counts={},
        ),
        "ebpf": ConditionResult(
            name="ebpf",
            elapsed_s=105.0,
            blocks_processed=20000,
            blocks_per_second=190.48,
            overhead_pct=5.0,
            event_counts={
                "validation:block_connected": 20000,
                "utxocache:add": 500000,
                "utxocache:spent": 400000,
                "mempool:added": 0,
            },
        ),
        "ipc": ConditionResult(
            name="ipc",
            elapsed_s=108.0,
            blocks_processed=20000,
            blocks_per_second=185.19,
            overhead_pct=8.0,
            event_counts={
                "validation:block_connected": 20000,
                "utxocache:add": 500000,
                "utxocache:spent": 400000,
                "mempool:added": 0,
            },
        ),
        "capnproto": ConditionResult(
            name="capnproto",
            elapsed_s=112.0,
            blocks_processed=20000,
            blocks_per_second=178.57,
            overhead_pct=12.0,
            event_counts={
                "validation:block_connected": 20000,
                "utxocache:add": 500000,
                "utxocache:spent": 400000,
                "mempool:added": 0,
            },
        ),
    }


def test_generate_report_basic():
    """Test basic report generation with all conditions."""
    config = make_config()
    results = make_results()
    report = generate_report(config, results)

    assert isinstance(report, BenchmarkReport)
    assert report.competitive is True  # 8% <= 2*5% = 10%
    assert report.event_parity is True  # same counts
    assert len(report.conditions) == 4
    print("✓ test_generate_report_basic")


def test_generate_report_not_competitive():
    """Test report when IPC is not competitive."""
    config = make_config()
    results = make_results()
    # Make IPC overhead > 2x eBPF
    results["ipc"].overhead_pct = 15.0  # 15% > 2*5% = 10%
    report = generate_report(config, results)

    assert report.competitive is False
    print("✓ test_generate_report_not_competitive")


def test_generate_report_partial_results():
    """Test report with a failed condition."""
    config = make_config()
    results = make_results()
    results["ebpf"] = ConditionResult(
        name="ebpf",
        elapsed_s=0.0,
        blocks_processed=0,
        blocks_per_second=0.0,
        error="bpftrace failed to attach",
    )
    report = generate_report(config, results)

    # Can't determine competitive without eBPF
    assert report.competitive is False
    assert report.event_parity is True  # no discrepancy if eBPF errored
    print("✓ test_generate_report_partial_results")


def test_report_to_json():
    """Test JSON serialization of report."""
    config = make_config()
    results = make_results()
    report = generate_report(config, results)
    json_str = report_to_json(report)

    data = json.loads(json_str)
    assert "metadata" in data
    assert "conditions" in data
    assert "competitive" in data
    assert "event_parity" in data
    assert data["metadata"]["block_range"] == [0, 20000]
    assert "baseline" in data["conditions"]
    assert data["conditions"]["baseline"]["elapsed_s"] == 100.0
    print("✓ test_report_to_json")


def test_format_table():
    """Test human-readable table formatting."""
    config = make_config()
    results = make_results()
    report = generate_report(config, results)
    table = format_table(report)

    assert "Condition" in table
    assert "Time(s)" in table
    assert "Blocks/s" in table
    assert "Overhead%" in table
    assert "baseline" in table
    assert "ebpf" in table
    assert "ipc" in table
    assert "capnproto" in table
    assert "COMPETITIVE" in table
    # Check alignment (all rows should have same number of pipes)
    lines = [l for l in table.split("\n") if l.startswith("|")]
    pipe_counts = [l.count("|") for l in lines]
    assert len(set(pipe_counts)) == 1, f"Misaligned columns: {pipe_counts}"
    print("✓ test_format_table")


def test_format_table_with_failure():
    """Test table formatting with a failed condition."""
    config = make_config()
    results = make_results()
    results["ebpf"] = ConditionResult(
        name="ebpf",
        elapsed_s=0.0,
        blocks_processed=0,
        blocks_per_second=0.0,
        error="bpftrace not available",
    )
    report = generate_report(config, results)
    table = format_table(report)

    assert "FAILED" in table
    print("✓ test_format_table_with_failure")


def test_validate_transaction_density_valid():
    """Test density validation with sufficient transactions."""
    tx_counts = [150, 200, 300, 120, 180]
    valid, avg = validate_transaction_density(tx_counts)
    assert valid is True
    assert avg == 190.0
    print("✓ test_validate_transaction_density_valid")


def test_validate_transaction_density_invalid():
    """Test density validation with insufficient transactions."""
    tx_counts = [50, 60, 70, 80, 90]
    valid, avg = validate_transaction_density(tx_counts)
    assert valid is False
    assert avg == 70.0
    print("✓ test_validate_transaction_density_invalid")


def test_validate_transaction_density_empty():
    """Test density validation with empty list."""
    valid, avg = validate_transaction_density([])
    assert valid is True
    assert avg == 0.0
    print("✓ test_validate_transaction_density_empty")


def test_validate_workload_full():
    """Test full workload validation."""
    results = make_results()
    tx_counts = [200, 300, 250, 180, 220]

    validation = validate_workload(results, tx_counts)

    assert validation.density_valid is True
    assert validation.avg_transactions == 230.0
    assert validation.event_discrepancy is False
    assert "baseline" in validation.per_condition_events
    assert "ebpf" in validation.per_condition_events
    assert validation.per_condition_events["ebpf"] == 920000
    assert len(validation.warnings) == 0
    print("✓ test_validate_workload_full")


def test_validate_workload_discrepancy():
    """Test workload validation with event count discrepancy."""
    results = make_results()
    # Make IPC have significantly different event count
    results["ipc"].event_counts = {
        "validation:block_connected": 20000,
        "utxocache:add": 600000,  # much higher
        "utxocache:spent": 400000,
        "mempool:added": 0,
    }

    validation = validate_workload(results)

    assert validation.event_discrepancy is True
    assert len(validation.warnings) > 0
    assert "discrepancy" in validation.warnings[0].lower()
    print("✓ test_validate_workload_discrepancy")


def test_format_workload_validation():
    """Test formatting of workload validation results."""
    results = make_results()
    tx_counts = [200, 300, 250, 180, 220]
    validation = validate_workload(results, tx_counts)
    formatted = format_workload_validation(validation)

    assert "Workload Validation" in formatted
    assert "Transaction density" in formatted
    assert "Event parity" in formatted
    assert "Per-tracepoint" in formatted
    print("✓ test_format_workload_validation")


def test_event_parity_with_discrepancy():
    """Test that event_parity flag in report reflects discrepancy."""
    config = make_config()
    results = make_results()
    # Create a >1% discrepancy
    results["ipc"].event_counts = {
        "validation:block_connected": 20000,
        "utxocache:add": 600000,
        "utxocache:spent": 400000,
        "mempool:added": 0,
    }
    report = generate_report(config, results)
    assert report.event_parity is False
    print("✓ test_event_parity_with_discrepancy")


if __name__ == "__main__":
    test_generate_report_basic()
    test_generate_report_not_competitive()
    test_generate_report_partial_results()
    test_report_to_json()
    test_format_table()
    test_format_table_with_failure()
    test_validate_transaction_density_valid()
    test_validate_transaction_density_invalid()
    test_validate_transaction_density_empty()
    test_validate_workload_full()
    test_validate_workload_discrepancy()
    test_format_workload_validation()
    test_event_parity_with_discrepancy()
    print("\nAll tests passed!")
