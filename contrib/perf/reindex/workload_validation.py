#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Workload validation for the reindex mainnet benchmark.

Verifies that the reindex workload fires tracepoints at realistic rates
and that event counts are consistent across tracing conditions.
"""

import logging
from dataclasses import dataclass, field

from .config import ConditionResult, detect_event_discrepancy

logger = logging.getLogger(__name__)

# Minimum average transactions per block for blocks above height 150,000
MIN_AVG_TRANSACTIONS = 100

# Key tracepoints to report individually
KEY_TRACEPOINTS = [
    "validation:block_connected",
    "utxocache:add",
    "utxocache:spent",
    "mempool:added",
]


@dataclass
class WorkloadValidationResult:
    """Result of workload validation checks.

    Attributes:
        density_valid: Whether transaction density meets the threshold.
        avg_transactions: Average transactions per block (if computed).
        event_discrepancy: Whether IPC/eBPF event counts differ by >1%.
        ipc_total_events: Total events from IPC condition.
        ebpf_total_events: Total events from eBPF condition.
        per_condition_events: Per-condition total event counts.
        per_tracepoint_events: Per-tracepoint event counts by condition.
        warnings: List of warning messages.
    """

    density_valid: bool = True
    avg_transactions: float = 0.0
    event_discrepancy: bool = False
    ipc_total_events: int = 0
    ebpf_total_events: int = 0
    per_condition_events: dict[str, int] = field(default_factory=dict)
    per_tracepoint_events: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    warnings: list[str] = field(default_factory=list)


def validate_transaction_density(
    tx_counts: list[int],
) -> tuple[bool, float]:
    """Verify blocks above height 150,000 contain sufficient transactions.

    Checks that the average transaction count per block meets the
    minimum threshold (100 transactions on average).

    Args:
        tx_counts: List of transaction counts per block (for blocks
            above height 150,000).

    Returns:
        Tuple of (is_valid, average_tx_count).
        Returns (True, 0.0) if tx_counts is empty.
    """
    if not tx_counts:
        return True, 0.0

    avg = sum(tx_counts) / len(tx_counts)
    is_valid = avg >= MIN_AVG_TRANSACTIONS
    return is_valid, avg


def validate_workload(
    results: dict[str, ConditionResult],
    tx_counts_above_150k: list[int] | None = None,
) -> WorkloadValidationResult:
    """Perform full workload validation on benchmark results.

    Checks:
    1. Transaction density (if tx_counts provided)
    2. Event count discrepancy between IPC and eBPF
    3. Per-tracepoint event counts for each condition

    Args:
        results: Mapping of condition name to its result.
        tx_counts_above_150k: Optional list of per-block transaction counts
            for blocks above height 150,000.

    Returns:
        WorkloadValidationResult with all validation outcomes.
    """
    validation = WorkloadValidationResult()

    # 1. Transaction density validation
    if tx_counts_above_150k is not None:
        density_valid, avg_tx = validate_transaction_density(
            tx_counts_above_150k
        )
        validation.density_valid = density_valid
        validation.avg_transactions = avg_tx

        if density_valid:
            logger.info(
                "Transaction density OK: %.1f avg tx/block (threshold: %d)",
                avg_tx,
                MIN_AVG_TRANSACTIONS,
            )
        else:
            msg = (
                f"Insufficient transaction density: {avg_tx:.1f} avg tx/block "
                f"(minimum: {MIN_AVG_TRANSACTIONS})"
            )
            logger.warning(msg)
            validation.warnings.append(msg)

    # 2. Log total events per condition
    for cond_name, result in results.items():
        if result.error is not None:
            continue
        total = sum(result.event_counts.values())
        validation.per_condition_events[cond_name] = total
        logger.info(
            "Condition '%s': %d total tracepoint events", cond_name, total
        )

    # 3. Event count discrepancy between IPC and eBPF
    ipc_result = results.get("ipc")
    ebpf_result = results.get("ebpf")

    if (
        ipc_result is not None
        and ebpf_result is not None
        and ipc_result.error is None
        and ebpf_result.error is None
    ):
        ipc_total = sum(ipc_result.event_counts.values())
        ebpf_total = sum(ebpf_result.event_counts.values())
        validation.ipc_total_events = ipc_total
        validation.ebpf_total_events = ebpf_total

        has_discrepancy = detect_event_discrepancy(ipc_total, ebpf_total)
        validation.event_discrepancy = has_discrepancy

        if has_discrepancy:
            pct = (
                abs(ipc_total - ebpf_total) / ebpf_total * 100
                if ebpf_total > 0
                else 0
            )
            msg = (
                f"Event count discrepancy: IPC={ipc_total}, eBPF={ebpf_total} "
                f"(diff: {pct:.2f}%)"
            )
            logger.warning(msg)
            validation.warnings.append(msg)
        else:
            logger.info(
                "Event parity OK: IPC=%d, eBPF=%d", ipc_total, ebpf_total
            )

    # 4. Per-tracepoint event counts
    for cond_name, result in results.items():
        if result.error is not None:
            continue
        tracepoint_counts: dict[str, int] = {}
        for tp in KEY_TRACEPOINTS:
            count = result.event_counts.get(tp, 0)
            tracepoint_counts[tp] = count
        validation.per_tracepoint_events[cond_name] = tracepoint_counts

        logger.info(
            "Condition '%s' key tracepoints: %s",
            cond_name,
            ", ".join(f"{k}={v}" for k, v in tracepoint_counts.items()),
        )

    return validation


def format_workload_validation(validation: WorkloadValidationResult) -> str:
    """Format workload validation results as a human-readable string.

    Args:
        validation: The validation result to format.

    Returns:
        Multi-line string with validation summary.
    """
    lines: list[str] = []
    lines.append("=== Workload Validation ===")
    lines.append("")

    # Transaction density
    if validation.avg_transactions > 0:
        status = "✓" if validation.density_valid else "✗"
        lines.append(
            f"{status} Transaction density: {validation.avg_transactions:.1f} "
            f"avg tx/block (threshold: {MIN_AVG_TRANSACTIONS})"
        )
    else:
        lines.append("— Transaction density: not measured")

    lines.append("")

    # Event counts per condition
    lines.append("Event counts per condition:")
    for cond_name, total in validation.per_condition_events.items():
        lines.append(f"  {cond_name}: {total:,} events")

    lines.append("")

    # Event parity
    if validation.ipc_total_events > 0 or validation.ebpf_total_events > 0:
        status = "✓" if not validation.event_discrepancy else "✗"
        lines.append(
            f"{status} Event parity: IPC={validation.ipc_total_events:,}, "
            f"eBPF={validation.ebpf_total_events:,}"
        )
    lines.append("")

    # Per-tracepoint breakdown
    if validation.per_tracepoint_events:
        lines.append("Per-tracepoint event counts:")
        # Header
        cond_names = list(validation.per_tracepoint_events.keys())
        header = f"  {'Tracepoint':<30}" + "".join(
            f"{c:>12}" for c in cond_names
        )
        lines.append(header)
        lines.append("  " + "-" * (30 + 12 * len(cond_names)))

        for tp in KEY_TRACEPOINTS:
            row = f"  {tp:<30}"
            for cond_name in cond_names:
                count = validation.per_tracepoint_events[cond_name].get(tp, 0)
                row += f"{count:>12,}"
            lines.append(row)

    # Warnings
    if validation.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in validation.warnings:
            lines.append(f"  ⚠ {w}")

    return "\n".join(lines)
