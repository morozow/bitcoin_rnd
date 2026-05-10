#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Report generation for the reindex mainnet benchmark.

Produces JSON and human-readable table reports comparing tracing overhead
across benchmark conditions (baseline, eBPF, IPC, Cap'n Proto).
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .config import (
    BenchmarkConfig,
    ConditionResult,
    ReportMetadata,
    is_competitive,
    detect_event_discrepancy,
)

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkReport:
    """Complete benchmark report with all condition results.

    Attributes:
        metadata: Report metadata (block range, timestamp, etc.).
        conditions: Mapping of condition name to its result.
        competitive: Whether IPC overhead is competitive with eBPF.
        event_parity: Whether IPC and eBPF event counts match within 1%.
    """

    metadata: ReportMetadata
    conditions: dict[str, ConditionResult]
    competitive: bool
    event_parity: bool


def generate_report(
    config: BenchmarkConfig,
    results: dict[str, ConditionResult],
    metadata: ReportMetadata | None = None,
) -> BenchmarkReport:
    """Generate a benchmark report from condition results.

    Computes competitive status and event parity from the results.
    Handles partial results (some conditions may have failed).

    Args:
        config: The benchmark configuration used.
        results: Mapping of condition name to its result.
        metadata: Optional pre-built metadata. If None, generates default.

    Returns:
        BenchmarkReport with all metrics and status flags.
    """
    if metadata is None:
        metadata = ReportMetadata(
            block_range=(0, config.stop_height),
            total_transactions=0,
            docker_image_hash="unknown",
            timestamp=datetime.now(timezone.utc).isoformat(),
            host_info="",
        )

    # Determine competitive status
    competitive = _compute_competitive_status(results)

    # Determine event parity
    event_parity = _compute_event_parity(results)

    return BenchmarkReport(
        metadata=metadata,
        conditions=results,
        competitive=competitive,
        event_parity=event_parity,
    )


def _compute_competitive_status(results: dict[str, ConditionResult]) -> bool:
    """Determine if IPC overhead is competitive with eBPF.

    Competitive means IPC overhead <= 2x eBPF overhead.
    Returns False if either condition is missing or errored.
    """
    ipc_result = results.get("ipc")
    ebpf_result = results.get("ebpf")

    if ipc_result is None or ebpf_result is None:
        return False
    if ipc_result.error is not None or ebpf_result.error is not None:
        return False
    if ipc_result.overhead_pct is None or ebpf_result.overhead_pct is None:
        return False

    return is_competitive(ipc_result.overhead_pct, ebpf_result.overhead_pct)


def _compute_event_parity(results: dict[str, ConditionResult]) -> bool:
    """Determine if IPC and eBPF event counts match within 1%.

    Returns True if counts are within tolerance or if either condition
    is missing/errored (no discrepancy to report).
    """
    ipc_result = results.get("ipc")
    ebpf_result = results.get("ebpf")

    if ipc_result is None or ebpf_result is None:
        return True
    if ipc_result.error is not None or ebpf_result.error is not None:
        return True

    ipc_total = sum(ipc_result.event_counts.values())
    ebpf_total = sum(ebpf_result.event_counts.values())

    if ebpf_total == 0:
        return True

    return not detect_event_discrepancy(ipc_total, ebpf_total)


def report_to_json(report: BenchmarkReport) -> str:
    """Serialize a BenchmarkReport to a JSON string.

    Handles dataclass serialization and formats the output for readability.

    Args:
        report: The benchmark report to serialize.

    Returns:
        Pretty-printed JSON string.
    """
    data = {
        "metadata": _metadata_to_dict(report.metadata),
        "conditions": {
            name: _condition_result_to_dict(result)
            for name, result in report.conditions.items()
        },
        "competitive": report.competitive,
        "event_parity": report.event_parity,
    }
    return json.dumps(data, indent=2)


def _metadata_to_dict(metadata: ReportMetadata) -> dict:
    """Convert ReportMetadata to a JSON-serializable dict."""
    return {
        "block_range": list(metadata.block_range),
        "total_transactions": metadata.total_transactions,
        "docker_image_hash": metadata.docker_image_hash,
        "timestamp": metadata.timestamp,
        "host_info": metadata.host_info,
    }


def _condition_result_to_dict(result: ConditionResult) -> dict:
    """Convert ConditionResult to a JSON-serializable dict."""
    d = {
        "name": result.name,
        "elapsed_s": result.elapsed_s,
        "blocks_processed": result.blocks_processed,
        "blocks_per_second": result.blocks_per_second,
        "overhead_pct": result.overhead_pct,
        "event_counts": result.event_counts,
    }
    if result.error is not None:
        d["error"] = result.error
    return d


def format_table(report: BenchmarkReport) -> str:
    """Format benchmark results as a human-readable comparison table.

    Produces a markdown-compatible table suitable for posting in
    Bitcoin Core issue #35142.

    Columns: Condition, Time(s), Blocks/s, Overhead%, Events, Status

    Args:
        report: The benchmark report to format.

    Returns:
        Formatted table string.
    """
    # Define column headers and widths
    headers = ["Condition", "Time(s)", "Blocks/s", "Overhead%", "Events", "Status"]

    # Build rows
    rows: list[list[str]] = []
    # Order: baseline first, then ebpf, ebpf_full, ipc, raw_ipc, capnproto
    condition_order = ["baseline", "ebpf", "ebpf_full", "ipc", "raw_ipc", "capnproto"]

    for cond_name in condition_order:
        result = report.conditions.get(cond_name)
        if result is None:
            continue
        rows.append(_format_row(result))

    # Include any conditions not in the standard order
    for cond_name, result in report.conditions.items():
        if cond_name not in condition_order:
            rows.append(_format_row(result))

    if not rows:
        return "No results to display."

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    # Build the table
    lines: list[str] = []

    # Header line
    header_line = "| " + " | ".join(
        h.ljust(col_widths[i]) for i, h in enumerate(headers)
    ) + " |"
    lines.append(header_line)

    # Separator line
    sep_line = "|-" + "-|-".join("-" * w for w in col_widths) + "-|"
    lines.append(sep_line)

    # Data rows
    for row in rows:
        data_line = "| " + " | ".join(
            cell.ljust(col_widths[i]) for i, cell in enumerate(row)
        ) + " |"
        lines.append(data_line)

    # Footer with summary
    lines.append("")
    lines.append(f"Block range: {report.metadata.block_range[0]}-{report.metadata.block_range[1]}")
    lines.append(f"Timestamp: {report.metadata.timestamp}")

    if report.competitive:
        lines.append("Result: IPC overhead is COMPETITIVE with eBPF (≤2x)")
    else:
        ebpf = report.conditions.get("ebpf")
        ipc = report.conditions.get("ipc")
        if ebpf and ipc and ebpf.error is None and ipc.error is None:
            lines.append("Result: IPC overhead is NOT competitive with eBPF (>2x)")

    if not report.event_parity:
        lines.append("WARNING: Event count discrepancy >1% between IPC and eBPF")

    return "\n".join(lines)


def _format_row(result: ConditionResult) -> list[str]:
    """Format a single condition result as a table row."""
    if result.error is not None:
        return [
            result.name,
            "-",
            "-",
            "-",
            "-",
            f"FAILED: {result.error[:40]}",
        ]

    total_events = sum(result.event_counts.values())

    overhead_str = (
        f"{result.overhead_pct:.2f}%"
        if result.overhead_pct is not None
        else "—"
    )

    return [
        result.name,
        f"{result.elapsed_s:.2f}",
        f"{result.blocks_per_second:.1f}",
        overhead_str,
        str(total_events),
        "OK",
    ]
