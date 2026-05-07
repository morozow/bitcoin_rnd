#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
End-to-end parity smoke test for the IPC tracing workers.

For each worker we feed a synthetic NDJSON stream that matches exactly the
format emitted by StdioBusSdkHooks::SerializeEvent() in
src/node/stdio_bus_sdk_hooks.cpp, then assert that the worker produced the
same class of output its eBPF counterpart would.

Run from the repo root:
    python3 contrib/tracing/ipc/test_parity.py
"""

import json
import subprocess
import sys
from pathlib import Path


IPC_DIR = Path(__file__).parent


def _envelope(event_type, **params):
    params["type"] = event_type
    params.setdefault("timestamp_us", 1_000_000)
    return json.dumps({
        "jsonrpc": "2.0",
        "method": "stdio_bus.event",
        "params": params,
    })


def _run(script, args, ndjson_lines):
    p = subprocess.run(
        [sys.executable, str(IPC_DIR / script), *args],
        input="\n".join(ndjson_lines) + "\n",
        capture_output=True, text=True, timeout=30,
    )
    return p.returncode, p.stdout, p.stderr


def _expect(name, ok, detail=""):
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {name} {detail}")
    if not ok:
        globals()["_FAILED"] = True


_FAILED = False


def test_mempool_monitor():
    print("mempool_monitor.py")
    events = [
        _envelope("mempool_added", txid="a" * 64, vsize=200, fee=1000),
        _envelope("tx_removed", txid="b" * 64, reason="block",
                  vsize=250, fee=1500, entry_time=12345),
        _envelope("tx_replaced", replaced_txid="c" * 64,
                  replaced_vsize=200, replaced_fee=1000,
                  replacement_txid="d" * 64,
                  replacement_vsize=210, replacement_fee=2000),
        _envelope("tx_rejected", txid="e" * 64, reason="min-relay-fee-not-met"),
    ]
    rc, out, err = _run("mempool_monitor.py", ["--no-curses"], events)
    _expect("exit 0", rc == 0, f"(rc={rc})")
    _expect("added event logged",
            " added " in out and "a" * 64 in out)
    _expect("removed event logged",
            " removed " in out and "b" * 64 in out and "block" in out)
    _expect("replaced event logged",
            " replaced " in out and "c" * 64 in out and "d" * 64 in out)
    _expect("rejected event logged",
            " rejected " in out and "min-relay-fee-not-met" in out)
    # Summary in stderr must show counts
    summary = json.loads(err.strip().split("\n")[-1])
    _expect("counts (added=1,removed=1,replaced=1,rejected=1)",
            summary == {"added": 1, "removed": 1, "replaced": 1, "rejected": 1},
            f"(got {summary})")


def test_connectblock_benchmark():
    print("connectblock_benchmark.py")
    # 3 blocks: heights 100, 101, 102; one of them slow (>500 ms).
    events = [
        _envelope("block_connected", hash="a" * 64, height=100,
                  tx_count=5, inputs_count=10, sigops_cost=20,
                  duration_ns=30_000_000),      # 30 ms
        _envelope("block_connected", hash="b" * 64, height=101,
                  tx_count=10, inputs_count=15, sigops_cost=25,
                  duration_ns=1_200_000_000),   # 1200 ms  → logged @ threshold=500
        _envelope("block_connected", hash="c" * 64, height=102,
                  tx_count=20, inputs_count=40, sigops_cost=50,
                  duration_ns=70_000_000),      # 70 ms
    ]
    rc, out, err = _run("connectblock_benchmark.py", ["0", "0", "500"], events)
    _expect("exit 0", rc == 0, f"(rc={rc})")
    _expect("header",
            "ConnectBlock logging starting at height 0" in out)
    _expect("slow block logged",
            "Block 101" in out and "1200 ms" in out)
    _expect("fast block not logged",
            "Block 100" not in out and "Block 102" not in out)
    _expect("histogram in stderr",
            "Histogram of block connection times" in err)
    summary = json.loads(err.strip().split("\n")[-1])
    _expect("totals",
            summary["total_blocks"] == 3
            and summary["total_transactions"] == 35
            and summary["total_inputs"] == 65
            and summary["total_sigops"] == 95,
            f"(got {summary})")


def test_p2p_traffic():
    print("p2p_traffic.py")
    events = [
        _envelope("message", peer_id=1, addr="1.2.3.4:8333",
                  conn_type="outbound-full-relay", msg_type="headers",
                  size_bytes=162, received_us=0),
        _envelope("outbound_message", peer_id=1, addr="1.2.3.4:8333",
                  conn_type="outbound-full-relay", msg_type="getdata",
                  size_bytes=37),
    ]
    rc, out, err = _run("p2p_traffic.py", ["--log"], events)
    _expect("exit 0", rc == 0, f"(rc={rc})")
    _expect("inbound line",
            "inbound 'headers' msg from peer 1" in out and "1.2.3.4:8333" in out)
    _expect("outbound line",
            "outbound 'getdata' msg to peer 1" in out and "1.2.3.4:8333" in out)
    summary = json.loads(err.strip().split("\n")[-1])
    _expect("inbound=1, outbound=1",
            summary == {"inbound": 1, "outbound": 1}, f"(got {summary})")


def test_p2p_connections():
    print("p2p_connections.py")
    events = [
        _envelope("peer_connection", peer_id=1, addr="9.9.9.9:8333",
                  conn_type="inbound", network=1, inbound=True,
                  existing_connections=5),
        _envelope("peer_closed", peer_id=1, addr="9.9.9.9:8333",
                  conn_type="inbound", network=1, time_established=120),
        _envelope("peer_evicted", peer_id=2, addr="8.8.8.8:8333",
                  conn_type="inbound", network=1, time_established=30),
        _envelope("peer_misbehaving", peer_id=3, message="invalid-header"),
    ]
    rc, out, err = _run("p2p_connections.py", [], events)
    _expect("exit 0", rc == 0, f"(rc={rc})")
    _expect("INBOUND line", "INBOUND conn from 9.9.9.9:8333" in out and "total=5" in out)
    _expect("CLOSED line", "CLOSED conn to 9.9.9.9:8333" in out)
    _expect("EVICTED line", "EVICTED conn to 8.8.8.8:8333" in out)
    _expect("MISBEHAVING line", "MISBEHAVING conn id=3" in out)


def test_utxocache_flush():
    print("utxocache_flush.py")
    events = [
        _envelope("utxocache_flush", duration_us=1234, mode=2,
                  coins_count=50000, coins_mem_usage=20_000_000,
                  is_flush_for_prune=False),
    ]
    rc, out, err = _run("utxocache_flush.py", [], events)
    _expect("exit 0", rc == 0, f"(rc={rc})")
    _expect("header present",
            "Duration (µs)" in out and "Coins Count" in out)
    _expect("row with PERIODIC mode",
            "PERIODIC" in out and "1234" in out and "50000" in out)


def test_utxocache_utxos():
    print("utxocache_utxos.py")
    events = [
        _envelope("utxocache_add", txid="a" * 64, vout=0, height=100,
                  value=50_0000_0000, is_coinbase=True),
        _envelope("utxocache_spent", txid="b" * 64, vout=1, height=200,
                  value=1_0000_0000, is_coinbase=False),
        _envelope("utxocache_uncache", txid="c" * 64, vout=2, height=300,
                  value=2_0000_0000, is_coinbase=False),
    ]
    rc, out, err = _run("utxocache_utxos.py", ["--verbose"], events)
    _expect("exit 0", rc == 0, f"(rc={rc})")
    _expect("header", "OP" in out and "Outpoint" in out and "Coinbase" in out)
    _expect("Added row", "Added" in out and "a" * 64 in out and "Yes" in out)
    _expect("Spent row", "Spent" in out and "b" * 64 in out and "No" in out)
    _expect("Uncache row", "Uncache" in out and "c" * 64 in out)


def main():
    test_mempool_monitor()
    test_connectblock_benchmark()
    test_p2p_traffic()
    test_p2p_connections()
    test_utxocache_flush()
    test_utxocache_utxos()
    if _FAILED:
        print("\nFAILED")
        sys.exit(1)
    print("\nAll parity smoke tests passed.")


if __name__ == "__main__":
    main()
