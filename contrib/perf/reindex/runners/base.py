#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Base condition runner protocol and shared reindex execution logic.

Defines the ConditionRunner protocol that all tracing conditions implement,
and provides the shared `run_reindex` helper that starts bitcoind -reindex,
waits for completion, and returns timing metrics.
"""

import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Default paths inside Docker container
DEFAULT_BITCOIND = Path("/bitcoin/build/bin/bitcoind")

# Maximum time to wait for bitcoind to exit after reindex completes
BITCOIND_SHUTDOWN_TIMEOUT_S = 120

# Maximum time to wait for reindex to complete (generous for 50k blocks)
REINDEX_TIMEOUT_S = 7200  # 2 hours


@dataclass
class TracingMetrics:
    """Metrics collected from a tracing session.

    Attributes:
        event_counts: Per-tracepoint event counts.
        probe_count: Number of probes/workers attached (for verification).
        extra: Any additional metrics specific to the condition.
    """

    event_counts: dict[str, int] = field(default_factory=dict)
    probe_count: int = 0
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class ReindexResult:
    """Result from a single reindex execution.

    Attributes:
        elapsed_s: Wall-clock elapsed time in seconds.
        blocks_processed: Number of blocks processed (from -stopatheight).
        returncode: bitcoind process exit code.
        error: Error message if something went wrong, None otherwise.
    """

    elapsed_s: float
    blocks_processed: int
    returncode: int
    error: str | None = None


@runtime_checkable
class ConditionRunner(Protocol):
    """Protocol defining the interface for benchmark condition runners.

    Each tracing condition (baseline, eBPF, IPC, Cap'n Proto) implements
    this protocol to provide condition-specific setup, tracing attachment,
    and cleanup logic.
    """

    def setup(self, datadir: Path, block_dir: Path) -> None:
        """Prepare the data directory with symlinked block files.

        Args:
            datadir: The condition's data directory.
            block_dir: Source directory containing mainnet blk*.dat files.
        """
        ...

    def start_tracing(self, bitcoind_pid: int) -> None:
        """Attach tracing (bpftrace/workers) after bitcoind starts.

        Args:
            bitcoind_pid: PID of the running bitcoind process.
        """
        ...

    def verify_tracing_active(self) -> bool:
        """Confirm tracing is attached and processing events.

        Returns:
            True if tracing is verified active, False otherwise.
        """
        ...

    def stop_tracing(self) -> TracingMetrics:
        """Stop tracing and return collected metrics.

        Returns:
            TracingMetrics with event counts and probe information.
        """
        ...

    def get_bitcoind_args(self) -> list[str]:
        """Return extra bitcoind CLI args for this condition.

        Returns:
            List of additional command-line arguments.
        """
        ...


def run_reindex(
    datadir: Path,
    stop_height: int,
    extra_args: list[str] | None = None,
    bitcoind_path: Path = DEFAULT_BITCOIND,
    timeout_s: int = REINDEX_TIMEOUT_S,
) -> ReindexResult:
    """Start bitcoind -reindex -stopatheight=N, wait for completion.

    Launches bitcoind in the foreground (non-daemon mode), measures
    wall-clock time from start to exit, and returns the result.

    Args:
        datadir: Bitcoin data directory (must contain blocks/ with symlinks).
        stop_height: Height at which bitcoind stops reindexing.
        extra_args: Additional bitcoind CLI arguments.
        bitcoind_path: Path to the bitcoind binary.
        timeout_s: Maximum time to wait for reindex completion.

    Returns:
        ReindexResult with elapsed time and blocks processed.
    """
    cmd = [
        str(bitcoind_path),
        f"-datadir={datadir}",
        "-reindex",
        f"-stopatheight={stop_height}",
        "-daemon=0",
        "-server=0",
        "-listen=0",
        "-noconnect",
        "-txindex=0",
        "-printtoconsole=0",
    ]
    if extra_args:
        cmd.extend(extra_args)

    logger.info("Starting reindex: %s", " ".join(cmd))
    start_time = time.monotonic()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for bitcoind to complete reindex and exit
        stdout, stderr = proc.communicate(timeout=timeout_s)
        elapsed = time.monotonic() - start_time

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            if not error_msg:
                error_msg = f"bitcoind exited with code {proc.returncode}"
            logger.error(
                "bitcoind reindex failed (code %d): %s",
                proc.returncode,
                error_msg[:500],
            )
            return ReindexResult(
                elapsed_s=elapsed,
                blocks_processed=0,
                returncode=proc.returncode,
                error=error_msg[:1000],
            )

        logger.info(
            "Reindex completed in %.2fs (stop_height=%d)",
            elapsed,
            stop_height,
        )
        return ReindexResult(
            elapsed_s=elapsed,
            blocks_processed=stop_height,
            returncode=0,
        )

    except subprocess.TimeoutExpired:
        logger.error("Reindex timed out after %ds", timeout_s)
        proc.kill()
        proc.wait(timeout=10)
        elapsed = time.monotonic() - start_time
        return ReindexResult(
            elapsed_s=elapsed,
            blocks_processed=0,
            returncode=-1,
            error=f"Reindex timed out after {timeout_s}s",
        )
    except OSError as e:
        elapsed = time.monotonic() - start_time
        logger.error("Failed to start bitcoind: %s", e)
        return ReindexResult(
            elapsed_s=elapsed,
            blocks_processed=0,
            returncode=-1,
            error=f"Failed to start bitcoind: {e}",
        )


def wait_for_process_cleanup(
    proc: subprocess.Popen | None,
    timeout_s: int = BITCOIND_SHUTDOWN_TIMEOUT_S,
) -> None:
    """Wait for a process to fully terminate, ensuring cleanup between conditions.

    Args:
        proc: The subprocess to wait for (may be None).
        timeout_s: Maximum time to wait before force-killing.
    """
    if proc is None:
        return

    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        logger.warning(
            "Process %d did not exit within %ds, sending SIGKILL",
            proc.pid,
            timeout_s,
        )
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.error("Process %d could not be killed", proc.pid)

    logger.debug("Process %d terminated (code=%s)", proc.pid, proc.returncode)
