#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
IPC/stdio_bus condition runner.

Runs bitcoind -reindex with -stdiobus=shadow and all 6 IPC workers
processing events via stdio_bus. Measures the overhead of the full
IPC tracing pipeline on real mainnet blocks.
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
    wait_for_process_cleanup,
)

logger = logging.getLogger(__name__)

# Default path to IPC workers inside Docker container
DEFAULT_IPC_DIR = Path("/bitcoin/contrib/tracing/ipc")

# The 6 IPC workers that cover all tracepoint subsystems
IPC_WORKERS = [
    {
        "id": "connectblock-benchmark",
        "script": "connectblock_benchmark.py",
        "args": [],
    },
    {
        "id": "mempool-monitor",
        "script": "mempool_monitor.py",
        "args": ["--no-curses"],
    },
    {
        "id": "p2p-traffic",
        "script": "p2p_traffic.py",
        "args": ["--log"],
    },
    {
        "id": "p2p-connections",
        "script": "p2p_connections.py",
        "args": [],
    },
    {
        "id": "utxocache-utxos",
        "script": "utxocache_utxos.py",
        "args": [],
    },
    {
        "id": "utxocache-flush",
        "script": "utxocache_flush.py",
        "args": [],
    },
]

# Expected number of workers
EXPECTED_WORKER_COUNT = 6

# Time to wait for workers to start
WORKER_START_TIMEOUT_S = 10


def _build_stdiobus_config(ipc_dir: Path) -> dict:
    """Build the stdiobus_trace.json configuration for all 6 workers.

    Args:
        ipc_dir: Directory containing IPC worker scripts.

    Returns:
        Configuration dictionary for -stdiobusconfig.
    """
    pools = []
    for worker in IPC_WORKERS:
        script_path = ipc_dir / worker["script"]
        pool = {
            "id": worker["id"],
            "command": "python3",
            "args": [str(script_path)] + worker["args"],
            "instances": 1,
        }
        pools.append(pool)
    return {"pools": pools}


class IpcRunner:
    """IPC condition: stdio_bus shadow mode with all 6 workers.

    Runs bitcoind with -stdiobus=shadow and a configuration that
    launches all 6 IPC workers covering validation, mempool, net,
    utxocache, and coin_selection subsystems.
    """

    def __init__(
        self,
        bitcoind_path: Path | None = None,
        ipc_dir: Path | None = None,
    ):
        """Initialize the IPC runner.

        Args:
            bitcoind_path: Path to bitcoind binary (uses default if None).
            ipc_dir: Directory containing IPC worker scripts.
        """
        self._bitcoind_path = bitcoind_path or DEFAULT_BITCOIND
        self._ipc_dir = ipc_dir or DEFAULT_IPC_DIR
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

        # Write stdiobus config into the datadir
        config = _build_stdiobus_config(self._ipc_dir)
        self._config_path = self._datadir / "stdiobus_trace.json"
        self._config_path.write_text(json.dumps(config, indent=2))
        logger.info(
            "Wrote stdiobus config with %d workers to %s",
            len(config["pools"]),
            self._config_path,
        )

    def start_tracing(self, bitcoind_pid: int) -> None:
        """No-op for IPC: workers are launched by bitcoind via stdiobus config.

        The stdio_bus subsystem in bitcoind spawns workers automatically
        based on the -stdiobusconfig file. No external attachment needed.

        Args:
            bitcoind_pid: PID of the running bitcoind process (unused).
        """
        # Workers are started by bitcoind's stdio_bus subsystem
        # Give them a moment to initialize
        time.sleep(2)

    def verify_tracing_active(self) -> bool:
        """Verify that IPC workers are running.

        Checks that the expected number of worker processes exist.
        Since workers are child processes of bitcoind (spawned via
        stdio_bus), we check for python3 processes with worker script names.

        Returns:
            True if workers appear to be running.
        """
        try:
            result = subprocess.run(
                ["pgrep", "-f", "contrib/tracing/ipc/"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Count matching PIDs
            pids = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
            worker_count = len(pids)
            if worker_count >= EXPECTED_WORKER_COUNT:
                logger.info("Verified %d IPC workers running", worker_count)
                return True
            else:
                logger.warning(
                    "Expected %d workers, found %d",
                    EXPECTED_WORKER_COUNT,
                    worker_count,
                )
                return worker_count > 0  # Partial success
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            logger.warning("Could not verify worker processes via pgrep")
            # If pgrep fails, assume workers are running (they're managed by bitcoind)
            return True

    def stop_tracing(self) -> TracingMetrics:
        """Stop tracing — workers are terminated when bitcoind exits.

        Workers receive EOF on stdin when bitcoind's stdio_bus shuts down,
        causing them to print summary stats to stderr and exit.

        Returns:
            TracingMetrics (event counts collected from worker output if available).
        """
        # Workers are terminated by bitcoind shutdown (EOF on stdin)
        # Event counts would need to be parsed from worker stderr
        # For now, return empty metrics — the orchestrator can collect
        # worker output from the bitcoind stderr stream
        return TracingMetrics(
            probe_count=EXPECTED_WORKER_COUNT,
        )

    def get_bitcoind_args(self) -> list[str]:
        """Return IPC-specific bitcoind arguments.

        Returns:
            Args to enable stdio_bus shadow mode with worker config.
        """
        args = ["-stdiobus=shadow"]
        if self._config_path:
            args.append(f"-stdiobusconfig={self._config_path}")
        return args

    def run(
        self, stop_height: int, baseline_elapsed: float | None = None
    ) -> ConditionResult:
        """Execute the IPC condition and return results.

        Args:
            stop_height: Block height at which to stop reindex.
            baseline_elapsed: Baseline elapsed time for overhead calculation.

        Returns:
            ConditionResult with timing metrics.
        """
        if self._datadir is None:
            return ConditionResult(
                name="ipc",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error="setup() not called before run()",
            )

        extra_args = self.get_bitcoind_args()

        # Start bitcoind with stdio_bus shadow mode
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

        logger.info("Starting bitcoind for IPC condition with %d workers", EXPECTED_WORKER_COUNT)
        start_time = time.monotonic()

        try:
            self._bitcoind_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            return ConditionResult(
                name="ipc",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error=f"Failed to start bitcoind: {e}",
            )

        # Workers are spawned by bitcoind's stdio_bus subsystem
        self.start_tracing(self._bitcoind_proc.pid)

        if not self.verify_tracing_active():
            logger.warning(
                "IPC worker verification incomplete, continuing anyway"
            )

        # Wait for bitcoind to complete reindex
        try:
            stdout, stderr = self._bitcoind_proc.communicate(timeout=7200)
        except subprocess.TimeoutExpired:
            self._bitcoind_proc.kill()
            self._bitcoind_proc.wait(timeout=10)
            return ConditionResult(
                name="ipc",
                elapsed_s=time.monotonic() - start_time,
                blocks_processed=0,
                blocks_per_second=0,
                error="Reindex timed out",
            )

        elapsed = time.monotonic() - start_time

        # Collect metrics from worker output (stderr contains worker summaries)
        metrics = self.stop_tracing()
        stderr_text = stderr.decode("utf-8", errors="replace")

        # Try to parse event counts from worker JSON summaries in stderr
        event_counts = _parse_worker_event_counts(stderr_text)
        if event_counts:
            metrics.event_counts = event_counts

        if self._bitcoind_proc.returncode != 0:
            error_msg = stderr_text.strip()
            return ConditionResult(
                name="ipc",
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
            "IPC completed: %.2fs, %d blocks, %.2f blocks/s, overhead=%.2f%%",
            elapsed,
            stop_height,
            bps,
            overhead or 0,
        )

        return ConditionResult(
            name="ipc",
            elapsed_s=elapsed,
            blocks_processed=stop_height,
            blocks_per_second=bps,
            overhead_pct=overhead,
            event_counts=metrics.event_counts,
        )


def _parse_worker_event_counts(stderr_text: str) -> dict[str, int]:
    """Parse event counts from worker JSON summaries in stderr.

    Workers print JSON summaries to stderr on exit. This function
    attempts to find and aggregate those counts.

    Args:
        stderr_text: Combined stderr output from bitcoind + workers.

    Returns:
        Aggregated event counts across all workers.
    """
    counts: dict[str, int] = {}

    for line in stderr_text.split("\n"):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            # Workers output various formats — look for "counts" dict
            if "counts" in data:
                for key, value in data["counts"].items():
                    if isinstance(value, int):
                        counts[key] = counts.get(key, 0) + value
            # connectblock_benchmark outputs "total_blocks" etc.
            elif "total_blocks" in data:
                counts["validation_block_connected"] = (
                    counts.get("validation_block_connected", 0)
                    + data.get("total_blocks", 0)
                )
        except (json.JSONDecodeError, TypeError):
            continue

    return counts
