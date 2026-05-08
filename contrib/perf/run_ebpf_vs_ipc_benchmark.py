#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
eBPF vs IPC comparative benchmark.

Runs inside a Docker container with bpftrace + USDT-enabled bitcoind.
Measures the same workload (N blocks on regtest) under three conditions:

  1. Baseline:  -stdiobus=off, no eBPF attached
  2. eBPF:      -stdiobus=off, bpftrace attached to USDT tracepoints
  3. IPC:       -stdiobus=shadow (stdio_bus hooks active, workers running)

Reports blocks/s for each and computes overhead percentages.

USAGE (inside container):
    python3 /bitcoin/contrib/perf/run_ebpf_vs_ipc_benchmark.py [--blocks=N]

Or from host:
    docker run --privileged --rm bitcoin-ebpf-vs-ipc --blocks=500
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
IPC_DIR = Path("/bitcoin/contrib/tracing/ipc")
CONFIG_FILE = Path("/bitcoin/contrib/perf/stdiobus_trace.json")

# bpftrace script that attaches to the same tracepoints our IPC workers cover.
# We use a minimal script that just counts events (no output processing) to
# measure pure eBPF overhead without userspace processing cost.
BPFTRACE_SCRIPT = """
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
    cmd.extend(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def _start_bitcoind(datadir, extra_args=None):
    cmd = [
        str(BITCOIND),
        f"-datadir={datadir}",
        "-regtest",
        "-daemon=0",
        "-server=1",
        "-listen=0",
        "-txindex=0",
        "-printtoconsole=0",
    ]
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Wait for RPC to be ready
    for _ in range(60):
        time.sleep(0.5)
        try:
            _cli("-regtest", "getblockchaininfo", datadir=datadir, timeout=5)
            return proc
        except Exception:
            continue
    raise RuntimeError("bitcoind did not start in time")


def _stop_bitcoind(proc, datadir):
    try:
        _cli("-regtest", "stop", datadir=datadir, timeout=10)
    except Exception:
        pass
    proc.wait(timeout=30)


def _generate_blocks(datadir, n):
    """Generate n blocks and return elapsed time."""
    # Create wallet if needed
    try:
        _cli("-regtest", "createwallet", "bench", datadir=datadir, timeout=30)
    except Exception:
        pass
    addr = _cli("-regtest", "getnewaddress", datadir=datadir)
    start = time.monotonic()
    # Generate in batches of 100
    remaining = n
    while remaining > 0:
        batch = min(100, remaining)
        _cli("-regtest", "generatetoaddress", str(batch), addr,
             datadir=datadir, timeout=300)
        remaining -= batch
    elapsed = time.monotonic() - start
    return elapsed


def run_baseline(datadir, blocks):
    """Condition 1: no tracing at all."""
    print("  [1/3] Baseline (no tracing)...")
    proc = _start_bitcoind(datadir, ["-stdiobus=off"])
    elapsed = _generate_blocks(datadir, blocks)
    _stop_bitcoind(proc, datadir)
    return elapsed


def run_ebpf(datadir, blocks):
    """Condition 2: bpftrace attached to all USDT probes."""
    print("  [2/3] eBPF (bpftrace attached to all USDT probes)...")
    proc = _start_bitcoind(datadir, ["-stdiobus=off"])

    # Write bpftrace script
    script = BPFTRACE_SCRIPT.format(binary=str(BITCOIND))
    script_file = Path(datadir) / "bench.bt"
    script_file.write_text(script)

    # Start bpftrace
    bpf_proc = subprocess.Popen(
        ["bpftrace", "-p", str(proc.pid), str(script_file)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(2)  # Let probes attach

    elapsed = _generate_blocks(datadir, blocks)

    # Stop bpftrace
    bpf_proc.send_signal(signal.SIGINT)
    bpf_proc.wait(timeout=10)

    _stop_bitcoind(proc, datadir)
    return elapsed


def run_ipc(datadir, blocks):
    """Condition 3: stdio_bus shadow mode with all IPC workers."""
    print("  [3/3] IPC (stdio_bus shadow, all workers)...")

    # Write config with all workers
    config = {"pools": [
        {"id": "block-bench", "command": "python3",
         "args": [str(IPC_DIR / "connectblock_benchmark.py")], "instances": 1},
        {"id": "mempool-mon", "command": "python3",
         "args": [str(IPC_DIR / "mempool_monitor.py"), "--no-curses"], "instances": 1},
        {"id": "p2p-traffic", "command": "python3",
         "args": [str(IPC_DIR / "p2p_traffic.py"), "--log"], "instances": 1},
        {"id": "p2p-connections", "command": "python3",
         "args": [str(IPC_DIR / "p2p_connections.py")], "instances": 1},
        {"id": "utxocache-utxos", "command": "python3",
         "args": [str(IPC_DIR / "utxocache_utxos.py")], "instances": 1},
        {"id": "utxocache-flush", "command": "python3",
         "args": [str(IPC_DIR / "utxocache_flush.py")], "instances": 1},
    ]}
    CONFIG_FILE.write_text(json.dumps(config, indent=2))

    proc = _start_bitcoind(datadir, [
        "-stdiobus=shadow",
        f"-stdiobusconfig={CONFIG_FILE}",
    ])
    elapsed = _generate_blocks(datadir, blocks)
    _stop_bitcoind(proc, datadir)
    return elapsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=500)
    ap.add_argument("--only", type=str, default=None,
                    choices=["baseline", "ebpf", "ipc"],
                    help="Run only one condition (for cache-fair measurement)")
    args = ap.parse_args()

    print("=" * 70)
    print("eBPF vs IPC Comparative Benchmark")
    print(f"Blocks per condition: {args.blocks}")
    print("=" * 70)

    all_conditions = [
        ("baseline", run_baseline),
        ("ebpf", run_ebpf),
        ("ipc", run_ipc),
    ]

    if args.only:
        all_conditions = [(n, r) for n, r in all_conditions if n == args.only]

    results = {}

    with tempfile.TemporaryDirectory(prefix="btc_bench_") as tmpdir:
        # Each condition gets a fresh datadir
        for condition, runner in all_conditions:
            datadir = os.path.join(tmpdir, condition)
            os.makedirs(datadir, exist_ok=True)
            elapsed = runner(datadir, args.blocks)
            bps = args.blocks / elapsed
            results[condition] = {
                "elapsed_s": round(elapsed, 2),
                "blocks_per_s": round(bps, 2),
            }
            print(f"    → {condition}: {elapsed:.2f}s ({bps:.2f} blocks/s)")

    # Compute overheads
    baseline_bps = results["baseline"]["blocks_per_s"]
    for key in ("ebpf", "ipc"):
        overhead = ((results["baseline"]["elapsed_s"] / results[key]["elapsed_s"]) - 1) * -100
        # More intuitive: how much slower
        overhead_pct = ((results[key]["elapsed_s"] - results["baseline"]["elapsed_s"])
                        / results["baseline"]["elapsed_s"]) * 100
        results[key]["overhead_pct"] = round(overhead_pct, 2)

    print("\n" + "=" * 70)
    print("RESULTS: eBPF vs IPC Overhead Comparison")
    print("=" * 70)
    print(f"{'Condition':<12} {'Time (s)':>10} {'Blocks/s':>10} {'Overhead':>10}")
    print("-" * 42)
    for key in ("baseline", "ebpf", "ipc"):
        r = results[key]
        oh = f"+{r.get('overhead_pct', 0):.2f}%" if "overhead_pct" in r else "—"
        print(f"{key:<12} {r['elapsed_s']:>10.2f} {r['blocks_per_s']:>10.2f} {oh:>10}")

    print("\n" + "=" * 70)
    if results["ipc"]["overhead_pct"] <= results["ebpf"]["overhead_pct"] * 1.5:
        print("✓ IPC overhead is within 1.5x of eBPF overhead — competitive.")
    else:
        print("✗ IPC overhead exceeds 1.5x of eBPF overhead.")
    print("=" * 70)

    # Save JSON report
    report_path = Path("/bitcoin/contrib/perf/results/ebpf_vs_ipc_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2))
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
