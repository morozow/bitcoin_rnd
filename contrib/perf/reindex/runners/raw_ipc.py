#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Raw IPC condition runner.

Runs bitcoind -reindex with -stdiobus=raw_pipe and all 6 IPC workers
receiving events via direct Unix pipes (no stdio_bus library).

This isolates the pure IPC overhead:
  - Event struct construction in C++
  - JSON serialization (ostringstream)
  - pipe write() syscall
  - Worker process read + parse + process

Without:
  - stdio_bus framing protocol
  - stdio_bus routing/multiplexing
  - stdio_bus event loop
  - stdio_bus worker lifecycle management

The workers are IDENTICAL to the IPC (stdio_bus) condition — same
scripts, same input format, same processing. Only the transport differs.
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

# Same 6 workers as the stdio_bus IPC condition — identical workload
RAW_IPC_WORKERS = [
    {
        "id": "connectblock-benchmark",
        "command": "python3",
        "args": ["connectblock_benchmark.py"],
    },
    {
        "id": "mempool-monitor",
        "command": "python3",
        "args": ["mempool_monitor.py", "--no-curses"],
    },
    {
        "id": "p2p-traffic",
        "command": "python3",
        "args": ["p2p_traffic.py", "--log"],
    },
    {
        "id": "p2p-connections",
        "command": "python3",
        "args": ["p2p_connections.py"],
    },
    {
        "id": "utxocache-utxos",
        "command": "python3",
        "args": ["utxocache_utxos.py"],
    },
    {
        "id": "utxocache-flush",
        "command": "python3",
        "args": ["utxocache_flush.py"],
    },
]

EXPECTED_WORKER_COUNT = 6


def _build_raw_pipe_config(ipc_dir: Path) -> dict:
    """Build the raw pipe configuration (same JSON format as stdiobus_trace.json).

    The raw_pipe C++ implementation reads the same config format but
    spawns workers via raw fork/exec + pipe instead of stdio_bus.

    Args:
        ipc_dir: Directory containing IPC worker scripts.

    Returns:
        Configuration dictionary.
    """
    pools = []
    for worker in RAW_IPC_WORKERS:
        script_path = ipc_dir / worker["args"][0]
        pool = {
            "id": worker["id"],
            "command": worker["command"],
            "args": [str(script_path)] + worker["args"][1:],
            "instances": 1,
        }
        pools.append(pool)
    return {"pools": pools}


class RawIpcRunner:
    """Raw IPC condition: direct Unix pipes with all 6 workers.

    Runs bitcoind with -stdiobus=raw_pipe and a configuration that
    spawns all 6 IPC workers via raw fork/exec + pipe. Workers receive
    the same NDJSON events as in the stdio_bus condition, but without
    the stdio_bus protocol library in the path.

    This provides the "pure IPC cost" baseline for comparison:
    - vs baseline: shows the inherent cost of IPC tracing
    - vs stdio_bus IPC: shows the overhead of the protocol library
    - vs eBPF: shows IPC vs kernel-side tracing
    """

    def __init__(
        self,
        bitcoind_path: Path | None = None,
        ipc_dir: Path | None = None,
    ):
        """Initialize the raw IPC runner.

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

        # Write raw pipe config (same format as stdiobus_trace.json)
        config = _build_raw_pipe_config(self._ipc_dir)
        self._config_path = self._datadir / "raw_pipe_config.json"
        self._config_path.write_text(json.dumps(config, indent=2))
        logger.info(
            "Wrote raw_pipe config with %d workers to %s",
            len(config["pools"]),
            self._config_path,
        )

    def start_tracing(self, bitcoind_pid: int) -> None:
        """No-op: workers are spawned by bitcoind's raw_pipe subsystem.

        Args:
            bitcoind_pid: PID of the running bitcoind process (unused).
        """
        # Workers are started by bitcoind's raw_pipe implementation
        # (fork/exec at startup). Give them a moment to initialize.
        time.sleep(2)

    def verify_tracing_active(self) -> bool:
        """Verify that raw IPC workers are running.

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
            pids = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
            worker_count = len(pids)
            if worker_count >= EXPECTED_WORKER_COUNT:
                logger.info("Verified %d raw IPC workers running", worker_count)
                return True
            else:
                logger.warning(
                    "Expected %d workers, found %d",
                    EXPECTED_WORKER_COUNT,
                    worker_count,
                )
                return worker_count > 0
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            logger.warning("Could not verify worker processes via pgrep")
            return True

    def stop_tracing(self) -> TracingMetrics:
        """Stop tracing — workers exit when pipe is closed (EOF on stdin).

        Returns:
            TracingMetrics.
        """
        return TracingMetrics(probe_count=EXPECTED_WORKER_COUNT)

    def get_bitcoind_args(self) -> list[str]:
        """Return raw IPC-specific bitcoind arguments.

        Returns:
            Args to enable raw_pipe mode with worker config.
        """
        args = ["-stdiobus=raw_pipe"]
        if self._config_path:
            args.append(f"-stdiobusconfig={self._config_path}")
        return args

    def run(
        self, stop_height: int, baseline_elapsed: float | None = None
    ) -> ConditionResult:
        """Execute the raw IPC condition and return results.

        Args:
            stop_height: Block height at which to stop reindex.
            baseline_elapsed: Baseline elapsed time for overhead calculation.

        Returns:
            ConditionResult with timing metrics.
        """
        if self._datadir is None:
            return ConditionResult(
                name="raw_ipc",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error="setup() not called before run()",
            )

        extra_args = self.get_bitcoind_args()

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

        logger.info(
            "Starting bitcoind for raw IPC condition with %d workers",
            EXPECTED_WORKER_COUNT,
        )
        start_time = time.monotonic()

        try:
            self._bitcoind_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            return ConditionResult(
                name="raw_ipc",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error=f"Failed to start bitcoind: {e}",
            )

        # Workers are spawned by bitcoind's raw_pipe subsystem
        self.start_tracing(self._bitcoind_proc.pid)

        if not self.verify_tracing_active():
            logger.warning(
                "Raw IPC worker verification incomplete, continuing anyway"
            )

        # Wait for bitcoind to complete reindex
        try:
            stdout, stderr = self._bitcoind_proc.communicate(timeout=7200)
        except subprocess.TimeoutExpired:
            self._bitcoind_proc.kill()
            self._bitcoind_proc.wait(timeout=10)
            return ConditionResult(
                name="raw_ipc",
                elapsed_s=time.monotonic() - start_time,
                blocks_processed=0,
                blocks_per_second=0,
                error="Reindex timed out",
            )

        elapsed = time.monotonic() - start_time

        # Collect metrics from worker stderr output
        metrics = self.stop_tracing()
        stderr_text = stderr.decode("utf-8", errors="replace")

        # Log stderr diagnostics
        stderr_lines = [l for l in stderr_text.split("\n") if l.strip()]
        logger.info(
            "Raw IPC stderr: %d bytes, %d non-empty lines",
            len(stderr_text),
            len(stderr_lines),
        )

        # Parse event counts (same parser as IPC condition)
        event_counts = _parse_worker_event_counts(stderr_text)
        if event_counts:
            metrics.event_counts = event_counts

        if self._bitcoind_proc.returncode != 0:
            error_msg = stderr_text.strip()
            return ConditionResult(
                name="raw_ipc",
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
            "Raw IPC completed: %.2fs, %d blocks, %.2f blocks/s, overhead=%.2f%%",
            elapsed,
            stop_height,
            bps,
            overhead or 0,
        )

        return ConditionResult(
            name="raw_ipc",
            elapsed_s=elapsed,
            blocks_processed=stop_height,
            blocks_per_second=bps,
            overhead_pct=overhead,
            event_counts=metrics.event_counts,
        )


def _parse_worker_event_counts(stderr_text: str) -> dict[str, int]:
    """Parse event counts from worker JSON summaries in stderr.

    Identical to the IPC runner parser — workers produce the same output.
    """
    counts: dict[str, int] = {}

    for line in stderr_text.split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.startswith("{"):
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue

                if "counts" in data and isinstance(data["counts"], dict):
                    for key, value in data["counts"].items():
                        if isinstance(value, int):
                            counts[key] = counts.get(key, 0) + value
                elif "total_blocks" in data:
                    counts["validation_block_connected"] = (
                        counts.get("validation_block_connected", 0)
                        + data.get("total_blocks", 0)
                    )
                else:
                    all_int_values = all(
                        isinstance(v, int) for v in data.values()
                    )
                    if all_int_values and data:
                        for key, value in data.items():
                            counts[key] = counts.get(key, 0) + value
            except (json.JSONDecodeError, TypeError):
                continue

    return counts
