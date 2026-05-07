#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
Smoke-test for IPC tracing workers: feeds synthetic events covering every
USDT tracepoint into each worker and checks they exit cleanly and emit
non-empty CSV output where applicable.

Run:
    python3 contrib/tracing/ipc/test_smoke.py
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def envelope(params):
    return json.dumps({
        "jsonrpc": "2.0",
        "method": "stdio_bus.event",
        "params": params,
    })


# Synthetic events — one representative per USDT tracepoint.
EVENTS = [
    # net:*_message
    {"type": "message", "peer_id": 1, "msg_type": "headers",
     "size_bytes": 162, "received_us": 1000, "timestamp_us": 1000},
    {"type": "outbound_message", "peer_id": 2, "addr": "1.2.3.4:8333",
     "conn_type": "outbound-full-relay", "msg_type": "ping",
     "size_bytes": 8, "timestamp_us": 2000},
    # net:*_connection
    {"type": "peer_connection", "peer_id": 3, "addr": "5.6.7.8:8333",
     "conn_type": "inbound", "network": 0, "inbound": True,
     "existing_connections": 4, "timestamp_us": 3000},
    {"type": "peer_connection", "peer_id": 4, "addr": "9.10.11.12:8333",
     "conn_type": "outbound-full-relay", "network": 0, "inbound": False,
     "existing_connections": 8, "timestamp_us": 4000},
    {"type": "peer_closed", "peer_id": 5, "addr": "1.2.3.4:8333",
     "conn_type": "outbound-full-relay", "network": 0,
     "time_established": 60, "timestamp_us": 5000},
    {"type": "peer_evicted", "peer_id": 6, "addr": "5.6.7.8:8333",
     "conn_type": "inbound", "network": 0,
     "time_established": 45, "timestamp_us": 6000},
    {"type": "peer_misbehaving", "peer_id": 7,
     "message": "getdata size = 50001", "timestamp_us": 7000},
    # mempool:*
    {"type": "mempool_added", "txid": "aa" * 32, "vsize": 250, "fee": 1250,
     "timestamp_us": 8000},
    {"type": "tx_removed", "txid": "bb" * 32, "reason": "expiry",
     "vsize": 260, "fee": 0, "entry_time": 1000, "timestamp_us": 9000},
    {"type": "tx_replaced",
     "replaced_txid": "cc" * 32, "replaced_vsize": 250,
     "replaced_fee": 1000, "replaced_entry_time": 500,
     "replacement_txid": "dd" * 32, "replacement_vsize": 260,
     "replacement_fee": 2000, "timestamp_us": 10000},
    {"type": "tx_rejected", "txid": "ee" * 32, "reason": "min-relay-fee",
     "timestamp_us": 11000},
    # validation:block_connected
    {"type": "block_connected", "hash": "11" * 32, "height": 100, "tx_count": 5,
     "inputs_count": 10, "sigops_cost": 50, "duration_ns": 123456,
     "timestamp_us": 12000},
    # utxocache:*
    {"type": "utxocache_add", "txid": "22" * 32, "vout": 0,
     "height": 101, "value": 50000, "is_coinbase": True,
     "timestamp_us": 13000},
    {"type": "utxocache_spent", "txid": "33" * 32, "vout": 1,
     "height": 90, "value": 40000, "is_coinbase": False,
     "timestamp_us": 14000},
    {"type": "utxocache_uncache", "txid": "44" * 32, "vout": 2,
     "height": 85, "value": 30000, "is_coinbase": False,
     "timestamp_us": 15000},
    {"type": "utxocache_flush", "duration_us": 2560, "mode": 0,
     "coins_count": 1500, "coins_mem_usage": 1 << 20,
     "is_flush_for_prune": False, "timestamp_us": 16000},
    # coin_selection:*
    {"type": "coin_selection_selected_coins", "wallet_name": "w",
     "algorithm": "BnB", "target": 10000, "waste": 50,
     "selected_value": 10100, "timestamp_us": 17000},
    {"type": "coin_selection_normal_create_tx", "wallet_name": "w",
     "success": True, "fee": 1000, "change_pos": 1, "timestamp_us": 18000},
    {"type": "coin_selection_attempting_aps", "wallet_name": "w",
     "timestamp_us": 19000},
    {"type": "coin_selection_aps_create_tx", "wallet_name": "w",
     "use_aps": True, "success": True, "fee": 900, "change_pos": 1,
     "timestamp_us": 20000},
]


def run_worker(script, extra_args=None):
    cmd = [sys.executable, os.path.join(HERE, script)]
    if extra_args:
        cmd.extend(extra_args)
    ndjson = "\n".join(envelope(e) for e in EVENTS) + "\n"
    proc = subprocess.run(cmd, input=ndjson, text=True,
                          capture_output=True, timeout=15)
    return proc


def main():
    failures = []

    with tempfile.TemporaryDirectory() as tmp:
        cases = [
            ("p2p_connections.py", ["--csv", os.path.join(tmp, "p2p.csv")]),
            ("utxocache_utxos.py", ["--csv", os.path.join(tmp, "utxo.csv")]),
            ("coin_selection.py", ["--csv", os.path.join(tmp, "cs.csv")]),
            ("all_events_recorder.py", ["--csv", os.path.join(tmp, "all.csv")]),
            ("mempool_monitor.py", []),
            ("utxocache_flush.py", []),
        ]
        for script, args in cases:
            if not os.path.exists(os.path.join(HERE, script)):
                failures.append(f"{script}: missing")
                continue
            proc = run_worker(script, args)
            if proc.returncode != 0:
                failures.append(
                    f"{script}: rc={proc.returncode}\nstderr:\n{proc.stderr}\n"
                )
                continue
            # Verify CSV output where applicable.
            if args and args[0] == "--csv":
                csv_path = args[1]
                if not os.path.exists(csv_path):
                    failures.append(f"{script}: no CSV produced at {csv_path}")
                elif os.path.getsize(csv_path) == 0:
                    failures.append(f"{script}: CSV is empty")
            print(f"ok  {script}")

    if failures:
        print("FAILED:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("all IPC workers OK")


if __name__ == "__main__":
    main()
