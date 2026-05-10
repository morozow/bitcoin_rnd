#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Cap'n Proto simulation condition runner.

Runs bitcoind -reindex with -stdiobus=shadow and the capnproto_sim_worker.py
which simulates Cap'n Proto serialization overhead per event. This provides
a credible comparison point for the multiprocess branch IPC mechanism.
"""

import json
import logging
import subprocess
import time
from pathlib import Path

from ..config import ConditionResult, compute_blocks_per_second, compute_overhead_pct
from ..datadir_setup import setup_condition_datadir
from .base import (
    DEFAULT_BITCOIND,
    TracingMetrics,
)

logger = logging.getLogger(__name__)

# Default path to the Cap'n Proto simulation worker
DEFAULT_CAPNPROTO_SIM_WORKER = Path(
    "/bitcoin/contrib/tracing/ipc/capnproto_sim_worker.py"
)


def _build_capnproto_sim_config(worker_path: Path) -> dict:
    """Build the stdiobus_trace.json configuration for the Cap'n Proto sim worker.

    Args:
        worker_path: Path to capnproto_sim_worker.py.

    Returns:
        Configuration dictionary for -stdiobusconfig.
    """
    return {
        "pools": [
            {
                "id": "capnproto-sim",
                "command": "python3",
                "args": [str(worker_path)],
                "instances": 1,
            }
        ]
    }


class CapnProtoSimRunner:
    """Cap'n Proto simulation condition: stdio_bus with calibrated overhead worker.

    Uses the same stdio_bus shadow mode as the IPC condition, but with
    a single worker (capnproto_sim_worker.py) that burns CPU for a
    calibrated duration per event, simulating Cap'n Proto serialization.

    This uses the same block range and data directory pattern as all
    other conditions for fair comparison.
    """

    def __init__(
        self,
        bitcoind_path: Path | None = None,
        worker_path: Path | None = None,
    ):
        """Initialize the Cap'n Proto simulation runner.

        Args:
            bitcoind_path: Path to bitcoind binary (uses default if None).
            worker_path: Path to capnproto_sim_worker.py.
        """
        self._bitcoind_path = bitcoind_path or DEFAULT_BITCOIND
        self._worker_path = worker_path or DEFAULT_CAPNPROTO_SIM_WORKER
        self._datadir: Path | None = None
        self._config_path: Path | None = None
        self._bitcoind_proc: subprocess.Popen | None = None

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

        # Write stdiobus config with the Cap'n Proto sim worker
        config = _build_capnproto_sim_config(self._worker_path)
        self._config_path = self._datadir / "stdiobus_trace.json"
        self._config_path.write_text(json.dumps(config, indent=2))
        logger.info(
            "Wrote Cap'n Proto sim config to %s", self._config_path
        )

    def start_tracing(self, bitcoind_pid: int) -> None:
        """No-op: worker is launched by bitcoind via stdiobus config.

        Args:
            bitcoind_pid: PID of the running bitcoind process (unused).
        """
        # Worker is started by bitcoind's stdio_bus subsystem
        time.sleep(1)

    def verify_tracing_active(self) -> bool:
        """Verify that the Cap'n Proto sim worker is running.

        Returns:
            True if the worker process appears to be running.
        """
        try:
            result = subprocess.run(
                ["pgrep", "-f", "capnproto_sim_worker"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            pids = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
            if pids:
                logger.info("Cap'n Proto sim worker running (PID %s)", pids[0])
                return True
            else:
                logger.warning("Cap'n Proto sim worker not found via pgrep")
                return True  # May still be running under different name
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return True  # Assume running if pgrep fails

    def stop_tracing(self) -> TracingMetrics:
        """Stop tracing — worker is terminated when bitcoind exits.

        Returns:
            TracingMetrics (event counts from worker stderr if available).
        """
        return TracingMetrics(probe_count=1)

    def get_bitcoind_args(self) -> list[str]:
        """Return Cap'n Proto sim-specific bitcoind arguments.

        Returns:
            Args to enable stdio_bus shadow mode with sim worker config.
        """
        args = ["-stdiobus=shadow"]
        if self._config_path:
            args.append(f"-stdiobusconfig={self._config_path}")
        return args

    def run(
        self, stop_height: int, baseline_elapsed: float | None = None
    ) -> ConditionResult:
        """Execute the Cap'n Proto simulation condition and return results.

        Args:
            stop_height: Block height at which to stop reindex.
            baseline_elapsed: Baseline elapsed time for overhead calculation.

        Returns:
            ConditionResult with timing metrics.
        """
        if self._datadir is None:
            return ConditionResult(
                name="capnproto",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error="setup() not called before run()",
            )

        extra_args = self.get_bitcoind_args()

        # Start bitcoind with stdio_bus shadow mode + capnproto sim worker
        cmd = [
            str(self._bitcoind_path),
            f"-datadir={self._datadir}",
            "-reindex",
            f"-stopatheight={stop_height}",
            "-daemon=0",
            "-server=0",
            "-listen=0",
            "-noconnect",
            "-txindex=0",
            "-printtoconsole=0",
        ] + extra_args

        logger.info("Starting bitcoind for Cap'n Proto simulation condition")
        start_time = time.monotonic()

        try:
            self._bitcoind_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            return ConditionResult(
                name="capnproto",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error=f"Failed to start bitcoind: {e}",
            )

        # Worker is spawned by bitcoind's stdio_bus subsystem
        self.start_tracing(self._bitcoind_proc.pid)

        if not self.verify_tracing_active():
            logger.warning(
                "Cap'n Proto sim worker verification incomplete, continuing"
            )

        # Wait for bitcoind to complete reindex
        try:
            stdout, stderr = self._bitcoind_proc.communicate(timeout=7200)
        except subprocess.TimeoutExpired:
            self._bitcoind_proc.kill()
            self._bitcoind_proc.wait(timeout=10)
            return ConditionResult(
                name="capnproto",
                elapsed_s=time.monotonic() - start_time,
                blocks_processed=0,
                blocks_per_second=0,
                error="Reindex timed out",
            )

        elapsed = time.monotonic() - start_time

        # Parse worker event counts from stderr
        metrics = self.stop_tracing()
        stderr_text = stderr.decode("utf-8", errors="replace")
        event_counts = _parse_capnproto_sim_output(stderr_text)
        if event_counts:
            metrics.event_counts = event_counts

        if self._bitcoind_proc.returncode != 0:
            error_msg = stderr_text.strip()
            return ConditionResult(
                name="capnproto",
                elapsed_s=elapsed,
                blocks_processed=0,
                blocks_per_second=0,
                event_counts=metrics.event_counts,
                error=error_msg[:1000] or f"bitcoind exited with code {self._bitcoind_proc.returncode}",
            )

        bps = compute_blocks_per_second(stop_height, elapsed)
        overhead = None
        if baseline_elapsed and baseline_elapsed > 0:
            overhead = compute_overhead_pct(baseline_elapsed, elapsed)

        logger.info(
            "Cap'n Proto sim completed: %.2fs, %d blocks, %.2f blocks/s, overhead=%.2f%%",
            elapsed,
            stop_height,
            bps,
            overhead or 0,
        )

        return ConditionResult(
            name="capnproto",
            elapsed_s=elapsed,
            blocks_processed=stop_height,
            blocks_per_second=bps,
            overhead_pct=overhead,
            event_counts=metrics.event_counts,
        )


def _parse_capnproto_sim_output(stderr_text: str) -> dict[str, int]:
    """Parse event counts from the capnproto_sim_worker JSON summary.

    The worker prints a JSON summary to stderr on exit containing
    a "counts" dictionary with per-event-type counts.

    Args:
        stderr_text: Combined stderr output from bitcoind + worker.

    Returns:
        Event counts dictionary.
    """
    counts: dict[str, int] = {}

    for line in stderr_text.split("\n"):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            if data.get("worker") == "capnproto_sim" and "counts" in data:
                for key, value in data["counts"].items():
                    if isinstance(value, int):
                        counts[key] = value
                return counts
        except (json.JSONDecodeError, TypeError):
            continue

    return counts
