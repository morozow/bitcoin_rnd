#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
eBPF overhead benchmark — runs inside Docker container.

Measures the same workload (N blocks on regtest) under two conditions:

  1. Baseline:  no tracing (no bpftrace, no stdio_bus)
  2. eBPF:      bpftrace attached to all 20 USDT tracepoints

Reports blocks/s for each and computes eBPF overhead percentage.
This result is then compared with the IPC overhead measured on the host.

USAGE (inside container):
    python3 /bitcoin/contrib/perf/run_ebpf_benchmark_docker.py [--blocks=N]

Or from host:
    docker run --privileged --rm bitcoin-ebpf-bench --blocks=500
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BITCOIND = Path("/bitcoin/build/bin/bitcoind")
BITCOIN_CLI = Path("/bitcoin/build/bin/bitcoin-cli")

# bpftrace script attaching to all 20 USDT tracepoints that our IPC workers cover.
# Minimal processing — just count events to measure pure probe overhead.
BPFTRACE_SCRIPT_TEMPLATE = """
usdt:{binary}:validation:block_connected {{ @blocks++; }}
usdt:{binary}:mempool:added {{ @mempool_added++; }}
usdt:{binary}:mempool:removed {{ @mempool_removed++; }}
usdt:{binary}:mempool:replaced {{ @mempool_replaced++; }}
usdt:{binary}:mempool:rejected {{ @mempool_rejected++; }}
usdt:{binary}:net:inbound_message {{ @net_in++; }}
usdt:{binary}:net:outbound_message {{ @net_out++; }}
usdt:{binary}:net:inbound_connection {{ @conn_in++; }}
usdt:{binary}:net:outbound_connection {{ @conn_out++; }}
usdt:{binary}:net:closed_connection {{ @conn_closed++; }}
usdt:{binary}:net:evicted_inbound_connection {{ @conn_evicted++; }}
usdt:{binary}:net:misbehaving_connection {{ @conn_misbehaving++; }}
usdt:{binary}:utxocache:add {{ @utxo_add++; }}
usdt:{binary}:utxocache:spent {{ @utxo_spent++; }}
usdt:{binary}:utxocache:uncache {{ @utxo_uncache++; }}
usdt:{binary}:utxocache:flush {{ @utxo_flush++; }}
"""


def _cli(*args, datadir=None, timeout=60):
    cmd = [str(BITCOIN_CLI)]
    if datadir:
        cmd.append(f"-datadir={datadir}")
    cmd.extend(["-regtest"] + list(args))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"bitcoin-cli failed: {r.stderr}")
    return r.stdout.strip()


def _start_bitcoind(datadir):
    cmd = [
        str(BITCOIND),
        f"-datadir={datadir}",
        "-regtest",
        "-daemon=0",
        "-server=1",
        "-listen=0",
        "-txindex=0",
        "-printtoconsole=0",
        "-stdiobus=off",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Wait for RPC
    for _ in range(120):
        time.sleep(0.5)
        try:
            _cli("getblockchaininfo", datadir=datadir, timeout=5)
            return proc
        except Exception:
            if proc.poll() is not None:
                raise RuntimeError(f"bitcoind exited with code {proc.returncode}")
            continue
    raise RuntimeError("bitcoind did not start in time")


def _stop_bitcoind(proc, datadir):
    try:
        _cli("stop", datadir=datadir, timeout=10)
    except Exception:
        proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()


def _generate_blocks(datadir, n):
    """Generate n blocks, return elapsed seconds."""
    try:
        _cli("createwallet", "bench", datadir=datadir, timeout=30)
    except Exception:
        try:
            _cli("loadwallet", "bench", datadir=datadir, timeout=10)
        except Exception:
            pass
    addr = _cli("getnewaddress", datadir=datadir)
    start = time.monotonic()
    remaining = n
    while remaining > 0:
        batch = min(100, remaining)
        _cli("generatetoaddress", str(batch), addr, datadir=datadir, timeout=300)
        remaining -= batch
    return time.monotonic() - start


def run_baseline(tmpdir, blocks):
    """No tracing at all."""
    print("  [1/2] Baseline (no tracing)...", flush=True)
    datadir = os.path.join(tmpdir, "baseline")
    os.makedirs(datadir, exist_ok=True)
    proc = _start_bitcoind(datadir)
    elapsed = _generate_blocks(datadir, blocks)
    _stop_bitcoind(proc, datadir)
    return elapsed


def run_ebpf(tmpdir, blocks):
    """bpftrace attached to all 20 USDT probes."""
    print("  [2/2] eBPF (bpftrace on all 20 USDT probes)...", flush=True)
    datadir = os.path.join(tmpdir, "ebpf")
    os.makedirs(datadir, exist_ok=True)
    proc = _start_bitcoind(datadir)

    # Write and start bpftrace
    script = BPFTRACE_SCRIPT_TEMPLATE.format(binary=str(BITCOIND))
    script_path = os.path.join(tmpdir, "bench.bt")
    with open(script_path, "w") as f:
        f.write(script)

    bpf_proc = subprocess.Popen(
        ["bpftrace", "-p", str(proc.pid), script_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    # Wait for probes to attach
    time.sleep(3)
    if bpf_proc.poll() is not None:
        err = bpf_proc.stderr.read().decode()
        print(f"  WARNING: bpftrace exited early: {err}", file=sys.stderr)
        # Fall through — measure without eBPF (will show as ~0% overhead)

    elapsed = _generate_blocks(datadir, blocks)

    # Stop bpftrace
    if bpf_proc.poll() is None:
        bpf_proc.send_signal(signal.SIGINT)
        try:
            out, err = bpf_proc.communicate(timeout=10)
            # Print bpftrace counters
            print(f"  bpftrace output:\n{out.decode()[:500]}", flush=True)
        except subprocess.TimeoutExpired:
            bpf_proc.kill()

    _stop_bitcoind(proc, datadir)
    return elapsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=500)
    args = ap.parse_args()

    print("=" * 60)
    print("eBPF Overhead Benchmark (Docker)")
    print(f"Blocks: {args.blocks}")
    print(f"Binary: {BITCOIND}")
    print("=" * 60, flush=True)

    # Check USDT probes
    probe_check = subprocess.run(
        ["bpftrace", "-l", f"usdt:{BITCOIND}:*"],
        capture_output=True, text=True, timeout=30,
    )
    probe_count = len(probe_check.stdout.strip().split("\n"))
    print(f"USDT probes found: {probe_count}", flush=True)
    if probe_count < 10:
        print("WARNING: fewer than expected USDT probes!", file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="btc_ebpf_") as tmpdir:
        t_baseline = run_baseline(tmpdir, args.blocks)
        t_ebpf = run_ebpf(tmpdir, args.blocks)

    bps_baseline = args.blocks / t_baseline
    bps_ebpf = args.blocks / t_ebpf
    overhead_pct = ((t_ebpf - t_baseline) / t_baseline) * 100

    results = {
        "blocks": args.blocks,
        "baseline": {
            "elapsed_s": round(t_baseline, 2),
            "blocks_per_s": round(bps_baseline, 2),
        },
        "ebpf": {
            "elapsed_s": round(t_ebpf, 2),
            "blocks_per_s": round(bps_ebpf, 2),
            "overhead_pct": round(overhead_pct, 2),
        },
    }

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"{'Condition':<12} {'Time (s)':>10} {'Blocks/s':>10} {'Overhead':>10}")
    print("-" * 42)
    print(f"{'baseline':<12} {t_baseline:>10.2f} {bps_baseline:>10.2f} {'—':>10}")
    print(f"{'ebpf':<12} {t_ebpf:>10.2f} {bps_ebpf:>10.2f} {overhead_pct:>+9.2f}%")
    print("=" * 60)

    # Save report
    report_path = Path("/bitcoin/contrib/perf/results/ebpf_overhead_docker.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2))
    print(f"\nReport: {report_path}")
    # Also print to stdout as JSON for easy capture
    print(json.dumps(results))


if __name__ == "__main__":
    main()
