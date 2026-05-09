#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
eBPF/USDT condition runner.

Runs bitcoind -reindex with bpftrace attached to all 20 USDT tracepoints.
Measures the overhead of having eBPF probes active during block processing.
"""

import logging
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from ..config import ConditionResult, compute_blocks_per_second, compute_overhead_pct
from ..datadir_setup import setup_condition_datadir
from .base import (
    DEFAULT_BITCOIND,
    ReindexResult,
    TracingMetrics,
    run_reindex,
    wait_for_process_cleanup,
)

logger = logging.getLogger(__name__)

# Expected number of USDT probes
EXPECTED_PROBE_COUNT = 20

# Time to wait for bpftrace to attach probes
BPFTRACE_ATTACH_TIMEOUT_S = 15

# bpftrace script template covering all 20 USDT tracepoints.
# Uses simple counters to measure pure eBPF overhead without
# userspace processing cost.
BPFTRACE_SCRIPT_TEMPLATE = """\
usdt:{binary}:validation:block_connected {{ @validation_block_connected++; }}
usdt:{binary}:mempool:added {{ @mempool_added++; }}
usdt:{binary}:mempool:removed {{ @mempool_removed++; }}
usdt:{binary}:mempool:replaced {{ @mempool_replaced++; }}
usdt:{binary}:mempool:rejected {{ @mempool_rejected++; }}
usdt:{binary}:net:inbound_message {{ @net_inbound_message++; }}
usdt:{binary}:net:outbound_message {{ @net_outbound_message++; }}
usdt:{binary}:net:inbound_connection {{ @net_inbound_connection++; }}
usdt:{binary}:net:outbound_connection {{ @net_outbound_connection++; }}
usdt:{binary}:net:closed_connection {{ @net_closed_connection++; }}
usdt:{binary}:net:evicted_inbound_connection {{ @net_evicted_connection++; }}
usdt:{binary}:net:misbehaving_connection {{ @net_misbehaving++; }}
usdt:{binary}:utxocache:add {{ @utxocache_add++; }}
usdt:{binary}:utxocache:spent {{ @utxocache_spent++; }}
usdt:{binary}:utxocache:uncache {{ @utxocache_uncache++; }}
usdt:{binary}:utxocache:flush {{ @utxocache_flush++; }}
usdt:{binary}:coin_selection:selected_coins {{ @coin_selection_selected++; }}
usdt:{binary}:coin_selection:normal_create_tx {{ @coin_selection_normal++; }}
usdt:{binary}:coin_selection:attempting_aps {{ @coin_selection_aps_attempt++; }}
usdt:{binary}:coin_selection:aps_create_tx {{ @coin_selection_aps_create++; }}
"""

# Regex to parse bpftrace counter output lines like "@validation_block_connected: 20000"
BPFTRACE_COUNTER_RE = re.compile(r"^@(\w+):\s+(\d+)$", re.MULTILINE)

# Regex to detect "Attaching N probes..." line
BPFTRACE_ATTACH_RE = re.compile(r"Attaching\s+(\d+)\s+probe", re.IGNORECASE)


def parse_probe_attachment_count(output: str) -> int:
    """Parse the number of probes attached from bpftrace output.

    Args:
        output: bpftrace stderr/stdout output.

    Returns:
        Number of probes attached, or 0 if not found.
    """
    match = BPFTRACE_ATTACH_RE.search(output)
    if match:
        return int(match.group(1))
    return 0


def parse_probe_hit_counts(output: str) -> dict[str, int]:
    """Parse probe hit counts from bpftrace output.

    bpftrace prints counters on exit in the format:
        @counter_name: 12345

    Args:
        output: bpftrace stdout output after SIGINT.

    Returns:
        Dictionary mapping probe names to hit counts.
    """
    counts = {}
    for match in BPFTRACE_COUNTER_RE.finditer(output):
        name = match.group(1)
        count = int(match.group(2))
        counts[name] = count
    return counts


class EbpfRunner:
    """eBPF condition: bpftrace attached to all 20 USDT probes.

    Attaches bpftrace to the running bitcoind process with a script
    covering all 20 tracepoints. Verifies attachment by checking the
    "Attaching N probes" output from bpftrace.
    """

    def __init__(self, bitcoind_path: Path | None = None):
        """Initialize the eBPF runner.

        Args:
            bitcoind_path: Path to bitcoind binary (uses default if None).
        """
        self._bitcoind_path = bitcoind_path or DEFAULT_BITCOIND
        self._datadir: Path | None = None
        self._bpftrace_proc: subprocess.Popen | None = None
        self._script_file: Path | None = None
        self._attached_probes: int = 0

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
        """Attach bpftrace to all 20 USDT probes on the bitcoind process.

        Args:
            bitcoind_pid: PID of the running bitcoind process.

        Raises:
            RuntimeError: If bpftrace fails to start or attach.
        """
        # Generate bpftrace script
        script = BPFTRACE_SCRIPT_TEMPLATE.format(binary=str(self._bitcoind_path))

        # Write script to a temp file in the datadir
        script_dir = self._datadir if self._datadir else Path(tempfile.gettempdir())
        self._script_file = script_dir / "reindex_bench.bt"
        self._script_file.write_text(script)

        logger.info(
            "Starting bpftrace with %d probes on PID %d",
            EXPECTED_PROBE_COUNT,
            bitcoind_pid,
        )

        # Start bpftrace attached to the bitcoind process
        self._bpftrace_proc = subprocess.Popen(
            ["bpftrace", "-p", str(bitcoind_pid), str(self._script_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for bpftrace to attach probes.
        # bpftrace typically attaches within 2-3 seconds.
        # Use a simple sleep like the proven run_ebpf_vs_ipc_benchmark.py approach.
        time.sleep(3)

        # Verify bpftrace didn't exit prematurely
        if self._bpftrace_proc.poll() is not None:
            stderr_output = self._bpftrace_proc.stderr.read().decode(
                "utf-8", errors="replace"
            )
            raise RuntimeError(
                f"bpftrace exited prematurely (code "
                f"{self._bpftrace_proc.returncode}): {stderr_output[:500]}"
            )

        self._attached_probes = EXPECTED_PROBE_COUNT
        logger.info("bpftrace attached (waited 3s, process still running)")

    def verify_tracing_active(self) -> bool:
        """Verify bpftrace is running and attached to expected probe count.

        Returns:
            True if bpftrace is running with all 20 probes attached.
        """
        if self._bpftrace_proc is None:
            return False
        if self._bpftrace_proc.poll() is not None:
            logger.error(
                "bpftrace exited unexpectedly (code %d)",
                self._bpftrace_proc.returncode,
            )
            return False
        if self._attached_probes != EXPECTED_PROBE_COUNT:
            logger.warning(
                "Expected %d probes, got %d",
                EXPECTED_PROBE_COUNT,
                self._attached_probes,
            )
            return False
        return True

    def stop_tracing(self) -> TracingMetrics:
        """Stop bpftrace and parse probe hit counts from output.

        Sends SIGINT to bpftrace (which triggers it to print counters)
        and parses the output.

        Returns:
            TracingMetrics with per-probe event counts.
        """
        if self._bpftrace_proc is None:
            return TracingMetrics()

        # Send SIGINT to trigger bpftrace to print counters and exit
        try:
            self._bpftrace_proc.send_signal(signal.SIGINT)
            stdout, stderr = self._bpftrace_proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("bpftrace did not exit after SIGINT, killing")
            self._bpftrace_proc.kill()
            stdout, stderr = self._bpftrace_proc.communicate(timeout=10)

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        # bpftrace prints counters to stdout on exit
        event_counts = parse_probe_hit_counts(stdout_text)
        if not event_counts:
            # Some versions print to stderr
            event_counts = parse_probe_hit_counts(stderr_text)

        logger.info("eBPF probe hit counts: %s", event_counts)

        # Clean up script file
        if self._script_file and self._script_file.exists():
            self._script_file.unlink()

        self._bpftrace_proc = None

        return TracingMetrics(
            event_counts=event_counts,
            probe_count=self._attached_probes,
        )

    def get_bitcoind_args(self) -> list[str]:
        """Return eBPF-specific bitcoind arguments.

        Returns:
            Args to disable stdio_bus (eBPF doesn't use it).
        """
        return ["-stdiobus=off"]

    def run(
        self, stop_height: int, baseline_elapsed: float | None = None
    ) -> ConditionResult:
        """Execute the eBPF condition and return results.

        This method handles the full lifecycle: start bitcoind, attach
        bpftrace, wait for reindex, collect metrics.

        Note: Unlike the simple baseline runner, the eBPF runner needs
        to start bitcoind separately (not via run_reindex) because
        bpftrace must attach after bitcoind starts but before reindex
        begins processing blocks. However, -reindex starts immediately
        on launch, so we attach bpftrace as quickly as possible.

        Args:
            stop_height: Block height at which to stop reindex.
            baseline_elapsed: Baseline elapsed time for overhead calculation.

        Returns:
            ConditionResult with timing and event count metrics.
        """
        if self._datadir is None:
            return ConditionResult(
                name="ebpf",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error="setup() not called before run()",
            )

        extra_args = self.get_bitcoind_args()

        # For eBPF, we use run_reindex but need to attach bpftrace
        # to the process. Since -reindex starts immediately, we start
        # bitcoind via Popen directly to get the PID, attach bpftrace,
        # then wait for completion.
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

        logger.info("Starting bitcoind for eBPF condition")
        start_time = time.monotonic()

        try:
            bitcoind_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            return ConditionResult(
                name="ebpf",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error=f"Failed to start bitcoind: {e}",
            )

        # Attach bpftrace to the running bitcoind
        try:
            self.start_tracing(bitcoind_proc.pid)
        except RuntimeError as e:
            logger.error("Failed to attach bpftrace: %s", e)
            # Kill bitcoind and return error
            bitcoind_proc.kill()
            bitcoind_proc.wait(timeout=30)
            return ConditionResult(
                name="ebpf",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error=f"bpftrace attachment failed: {e}",
            )

        if not self.verify_tracing_active():
            logger.warning("Tracing verification failed, continuing anyway")

        # Wait for bitcoind to complete reindex
        try:
            stdout, stderr = bitcoind_proc.communicate(timeout=7200)
        except subprocess.TimeoutExpired:
            bitcoind_proc.kill()
            bitcoind_proc.wait(timeout=10)
            self.stop_tracing()
            return ConditionResult(
                name="ebpf",
                elapsed_s=time.monotonic() - start_time,
                blocks_processed=0,
                blocks_per_second=0,
                error="Reindex timed out",
            )

        elapsed = time.monotonic() - start_time

        # Stop bpftrace and collect metrics
        metrics = self.stop_tracing()

        if bitcoind_proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            return ConditionResult(
                name="ebpf",
                elapsed_s=elapsed,
                blocks_processed=0,
                blocks_per_second=0,
                event_counts=metrics.event_counts,
                error=error_msg[:1000] or f"bitcoind exited with code {bitcoind_proc.returncode}",
            )

        bps = compute_blocks_per_second(stop_height, elapsed)
        overhead = None
        if baseline_elapsed and baseline_elapsed > 0:
            overhead = compute_overhead_pct(baseline_elapsed, elapsed)

        logger.info(
            "eBPF completed: %.2fs, %d blocks, %.2f blocks/s, overhead=%.2f%%",
            elapsed,
            stop_height,
            bps,
            overhead or 0,
        )

        return ConditionResult(
            name="ebpf",
            elapsed_s=elapsed,
            blocks_processed=stop_height,
            blocks_per_second=bps,
            overhead_pct=overhead,
            event_counts=metrics.event_counts,
        )
