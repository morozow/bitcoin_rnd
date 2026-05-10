#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
eBPF Full condition runner (data extraction + userspace delivery).

Unlike the basic eBPF condition (which only increments kernel counters),
this condition uses bpftrace with printf on every event — extracting
tracepoint arguments and delivering them to userspace via the perf
ring buffer (bpftrace's printf mechanism uses perf internally).

On each tracepoint fire:
  - Kernel: read USDT args, format into printf buffer, submit via perf
  - Userspace: bpftrace runtime receives, formats, writes to file
  - Result: real data extraction + delivery overhead per event

This makes the eBPF workload comparable to IPC:
  - Both extract real data from each tracepoint
  - Both deliver data to userspace
  - Both have userspace processing per event

stdout is redirected to a file (not a pipe) to avoid pipe buffer
overflow blocking bpftrace and causing event drops.
"""

import logging
import os
import signal
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

EXPECTED_PROBE_COUNT = 20
BPFTRACE_ATTACH_TIMEOUT_S = 5

# bpftrace script that extracts data from every tracepoint and prints it.
# printf forces bpftrace to use perf_submit internally — data flows from
# kernel to userspace on every single event.
BPFTRACE_FULL_SCRIPT_TEMPLATE = """\
usdt:{binary}:validation:block_connected {{
  printf("EVT block_connected height=%d txs=%d inputs=%d sigops=%d dur=%llu\\n", arg1, arg2, arg3, arg4, arg5);
}}
usdt:{binary}:mempool:added {{
  printf("EVT mempool_added vsize=%llu fee=%lld\\n", arg1, arg2);
}}
usdt:{binary}:mempool:removed {{
  printf("EVT mempool_removed vsize=%llu fee=%lld\\n", arg2, arg3);
}}
usdt:{binary}:mempool:replaced {{
  printf("EVT mempool_replaced old_vsize=%llu new_vsize=%llu\\n", arg1, arg4);
}}
usdt:{binary}:mempool:rejected {{
  printf("EVT mempool_rejected\\n");
}}
usdt:{binary}:net:inbound_message {{
  printf("EVT net_inbound peer=%lld size=%llu\\n", arg0, arg4);
}}
usdt:{binary}:net:outbound_message {{
  printf("EVT net_outbound peer=%lld size=%llu\\n", arg0, arg4);
}}
usdt:{binary}:net:inbound_connection {{
  printf("EVT conn_in peer=%lld\\n", arg0);
}}
usdt:{binary}:net:outbound_connection {{
  printf("EVT conn_out peer=%lld\\n", arg0);
}}
usdt:{binary}:net:closed_connection {{
  printf("EVT conn_closed peer=%lld\\n", arg0);
}}
usdt:{binary}:net:evicted_inbound_connection {{
  printf("EVT conn_evicted peer=%lld\\n", arg0);
}}
usdt:{binary}:net:misbehaving_connection {{
  printf("EVT conn_misbehaving peer=%lld\\n", arg0);
}}
usdt:{binary}:utxocache:add {{
  printf("EVT utxo_add height=%u value=%lld\\n", arg2, arg3);
}}
usdt:{binary}:utxocache:spent {{
  printf("EVT utxo_spent height=%u value=%lld\\n", arg2, arg3);
}}
usdt:{binary}:utxocache:uncache {{
  printf("EVT utxo_uncache height=%u value=%lld\\n", arg2, arg3);
}}
usdt:{binary}:utxocache:flush {{
  printf("EVT utxo_flush duration=%lld coins=%llu\\n", arg0, arg2);
}}
usdt:{binary}:coin_selection:selected_coins {{
  printf("EVT cs_selected\\n");
}}
usdt:{binary}:coin_selection:normal_create_tx {{
  printf("EVT cs_normal\\n");
}}
usdt:{binary}:coin_selection:attempting_aps {{
  printf("EVT cs_aps_attempt\\n");
}}
usdt:{binary}:coin_selection:aps_create_tx {{
  printf("EVT cs_aps\\n");
}}
"""


class EbpfFullRunner:
    """eBPF Full condition: bpftrace with printf (data extraction per event).

    Uses bpftrace with printf on every tracepoint fire. bpftrace stdout
    is redirected to a file to avoid pipe buffer overflow (which would
    block bpftrace and cause perf ring buffer drops).

    Unlike basic eBPF (counter increment only), this:
      - Reads tracepoint arguments in kernel
      - Formats them into a string (perf buffer copy to userspace)
      - bpftrace runtime writes to file
      - After completion, Python counts total events
    """

    def __init__(self, bitcoind_path: Path | None = None):
        self._bitcoind_path = bitcoind_path or DEFAULT_BITCOIND
        self._datadir: Path | None = None
        self._bpftrace_proc: subprocess.Popen | None = None
        self._script_file: Path | None = None
        self._output_file: Path | None = None
        self._output_fd = None

    def setup(self, datadir: Path, block_dir: Path) -> None:
        self._datadir = setup_condition_datadir(
            base=datadir.parent,
            condition_name=datadir.name,
            block_dir=block_dir,
        )

    def start_tracing(self, bitcoind_pid: int) -> None:
        """Attach bpftrace with printf to all 20 USDT probes.

        stdout goes to a file to prevent pipe buffer overflow.
        """
        script = BPFTRACE_FULL_SCRIPT_TEMPLATE.format(
            binary=str(self._bitcoind_path)
        )

        self._script_file = self._datadir / "ebpf_full_bench.bt"
        self._script_file.write_text(script)

        # Output file for bpftrace stdout (avoids pipe buffer overflow)
        self._output_file = self._datadir / "ebpf_full_output.log"
        self._output_fd = open(self._output_file, "w")

        logger.info(
            "Starting bpftrace (full/printf) with %d probes on PID %d, output → %s",
            EXPECTED_PROBE_COUNT,
            bitcoind_pid,
            self._output_file,
        )

        self._bpftrace_proc = subprocess.Popen(
            ["bpftrace", "-p", str(bitcoind_pid), str(self._script_file)],
            stdout=self._output_fd,
            stderr=subprocess.PIPE,
        )

        time.sleep(BPFTRACE_ATTACH_TIMEOUT_S)

        if self._bpftrace_proc.poll() is not None:
            self._output_fd.close()
            stderr_output = self._bpftrace_proc.stderr.read().decode(
                "utf-8", errors="replace"
            )
            raise RuntimeError(
                f"bpftrace (full) exited prematurely (code "
                f"{self._bpftrace_proc.returncode}): {stderr_output[:500]}"
            )

        logger.info("bpftrace (full/printf) attached, process running")

    def verify_tracing_active(self) -> bool:
        if self._bpftrace_proc is None:
            return False
        if self._bpftrace_proc.poll() is not None:
            return False
        return True

    def stop_tracing(self) -> TracingMetrics:
        """Stop bpftrace and count events from output file."""
        if self._bpftrace_proc is None:
            return TracingMetrics()

        # Send SIGINT to stop bpftrace gracefully
        try:
            self._bpftrace_proc.send_signal(signal.SIGINT)
            _, stderr = self._bpftrace_proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("bpftrace (full) did not exit after SIGINT, killing")
            self._bpftrace_proc.kill()
            _, stderr = self._bpftrace_proc.communicate(timeout=10)

        # Close output file
        if self._output_fd:
            self._output_fd.close()
            self._output_fd = None

        # Count EVT lines in output file
        event_count = 0
        if self._output_file and self._output_file.exists():
            with open(self._output_file, "r") as f:
                for line in f:
                    if line.startswith("EVT "):
                        event_count += 1

            # Log file size for diagnostics
            file_size = self._output_file.stat().st_size
            logger.info(
                "eBPF full output: %d events, %.1f MB file",
                event_count,
                file_size / (1024 * 1024),
            )

        # Check stderr for perf buffer drop warnings
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
        if "lost" in stderr_text.lower() or "drop" in stderr_text.lower():
            logger.warning("bpftrace reported event loss: %s", stderr_text[:200])

        # Cleanup
        if self._script_file and self._script_file.exists():
            self._script_file.unlink()
        # Keep output file for inspection (in datadir, will be cleaned up)

        self._bpftrace_proc = None

        return TracingMetrics(
            event_counts={"ebpf_full_total": event_count},
            probe_count=EXPECTED_PROBE_COUNT,
        )

    def get_bitcoind_args(self) -> list[str]:
        return ["-stdiobus=off"]

    def run(
        self, stop_height: int, baseline_elapsed: float | None = None
    ) -> ConditionResult:
        if self._datadir is None:
            return ConditionResult(
                name="ebpf_full",
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

        logger.info("Starting bitcoind for eBPF full condition")
        start_time = time.monotonic()

        try:
            bitcoind_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            return ConditionResult(
                name="ebpf_full",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error=f"Failed to start bitcoind: {e}",
            )

        # Attach bpftrace with printf → file
        try:
            self.start_tracing(bitcoind_proc.pid)
        except RuntimeError as e:
            logger.error("Failed to attach bpftrace (full): %s", e)
            bitcoind_proc.kill()
            bitcoind_proc.wait(timeout=30)
            return ConditionResult(
                name="ebpf_full",
                elapsed_s=0,
                blocks_processed=0,
                blocks_per_second=0,
                error=f"bpftrace (full) attachment failed: {e}",
            )

        if not self.verify_tracing_active():
            logger.warning("bpftrace (full) verification failed, continuing")

        # Wait for bitcoind to complete reindex
        try:
            stdout, stderr = bitcoind_proc.communicate(timeout=7200)
        except subprocess.TimeoutExpired:
            bitcoind_proc.kill()
            bitcoind_proc.wait(timeout=10)
            self.stop_tracing()
            return ConditionResult(
                name="ebpf_full",
                elapsed_s=time.monotonic() - start_time,
                blocks_processed=0,
                blocks_per_second=0,
                error="Reindex timed out",
            )

        elapsed = time.monotonic() - start_time

        # Stop bpftrace and collect event count
        metrics = self.stop_tracing()

        if bitcoind_proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            return ConditionResult(
                name="ebpf_full",
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
            "eBPF full completed: %.2fs, %d blocks, %.2f blocks/s, overhead=%.2f%%",
            elapsed,
            stop_height,
            bps,
            overhead or 0,
        )

        return ConditionResult(
            name="ebpf_full",
            elapsed_s=elapsed,
            blocks_processed=stop_height,
            blocks_per_second=bps,
            overhead_pct=overhead,
            event_counts=metrics.event_counts,
        )
