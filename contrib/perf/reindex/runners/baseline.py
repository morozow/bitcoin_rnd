#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Baseline condition runner — no tracing active.

Runs bitcoind -reindex with -stdiobus=off and no eBPF probes attached,
establishing the reference throughput for overhead calculations.
"""

import logging
from pathlib import Path

from ..config import ConditionResult, compute_blocks_per_second
from ..datadir_setup import setup_condition_datadir
from .base import ReindexResult, TracingMetrics, run_reindex

logger = logging.getLogger(__name__)


class BaselineRunner:
    """Baseline condition: no tracing, -stdiobus=off.

    Provides the reference measurement against which all tracing
    conditions compute their overhead percentage.
    """

    def __init__(self, bitcoind_path: Path | None = None):
        """Initialize the baseline runner.

        Args:
            bitcoind_path: Path to bitcoind binary (uses default if None).
        """
        self._bitcoind_path = bitcoind_path
        self._datadir: Path | None = None

    def setup(self, datadir: Path, block_dir: Path) -> None:
        """Prepare data directory with symlinked block files.

        Args:
            datadir: Base directory for this condition's data.
            block_dir: Source directory containing mainnet blk*.dat files.
        """
        self._datadir = setup_condition_datadir(
            base=datadir.parent,
            condition_name=datadir.name,
            block_dir=block_dir,
        )

    def start_tracing(self, bitcoind_pid: int) -> None:
        """No-op: baseline has no tracing."""
        pass

    def verify_tracing_active(self) -> bool:
        """No-op: baseline has no tracing to verify.

        Returns:
            Always True (no tracing to fail).
        """
        return True

    def stop_tracing(self) -> TracingMetrics:
        """No-op: baseline has no tracing to stop.

        Returns:
            Empty TracingMetrics.
        """
        return TracingMetrics()

    def get_bitcoind_args(self) -> list[str]:
        """Return baseline-specific bitcoind arguments.

        Returns:
            Args to disable stdio_bus.
        """
        return ["-stdiobus=off"]

    def run(self, stop_height: int) -> ConditionResult:
        """Execute the baseline condition and return results.

        Args:
            stop_height: Block height at which to stop reindex.

        Returns:
            ConditionResult with timing metrics.
        """
        if self._datadir is None:
            return ConditionResult(
                name="baseline",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error="setup() not called before run()",
            )

        extra_args = self.get_bitcoind_args()
        kwargs = {}
        if self._bitcoind_path:
            kwargs["bitcoind_path"] = self._bitcoind_path

        result: ReindexResult = run_reindex(
            datadir=self._datadir,
            stop_height=stop_height,
            extra_args=extra_args,
            **kwargs,
        )

        if result.error:
            return ConditionResult(
                name="baseline",
                elapsed_s=result.elapsed_s,
                blocks_processed=result.blocks_processed,
                blocks_per_second=0,
                error=result.error,
            )

        bps = compute_blocks_per_second(result.blocks_processed, result.elapsed_s)

        logger.info(
            "Baseline completed: %.2fs, %d blocks, %.2f blocks/s",
            result.elapsed_s,
            result.blocks_processed,
            bps,
        )

        return ConditionResult(
            name="baseline",
            elapsed_s=result.elapsed_s,
            blocks_processed=result.blocks_processed,
            blocks_per_second=bps,
            overhead_pct=None,  # Baseline is the reference
        )
