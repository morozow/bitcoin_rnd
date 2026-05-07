#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
Catch-all IPC recorder for all stdio_bus events.

Writes one CSV row per incoming event with the normalized columns that
compare_latency.py expects.

Covered event types (all 20 USDT tracepoints + Phase 2 internal events):

  message, outbound_message, headers
  peer_connection, peer_closed, peer_evicted, peer_misbehaving
  block_received, block_validated, block_connected, block_announce,
  block_request_decision, block_in_flight, staller_detected,
  compact_block_decision, block_source_resolved
  tx_admission, tx_removed, tx_replaced, tx_rejected, mempool_added
  utxocache_add, utxocache_spent, utxocache_uncache, utxocache_flush
  coin_selection_selected_coins, coin_selection_normal_create_tx,
  coin_selection_attempting_aps, coin_selection_aps_create_tx

USAGE:
  ./all_events_recorder.py --csv /tmp/ipc.csv
"""

import argparse
import csv
import json
import sys
import time


# Mapping event "type" field to the USDT tracepoint name it mirrors.
TYPE_TO_TRACEPOINT = {
    # P2P
    "message": "net:inbound_message",
    "outbound_message": "net:outbound_message",
    "headers": "net:inbound_message[headers]",
    "peer_connection": "net:inbound_connection|net:outbound_connection",
    "peer_closed": "net:closed_connection",
    "peer_evicted": "net:evicted_inbound_connection",
    "peer_misbehaving": "net:misbehaving_connection",
    # Block / validation
    "block_received": "net:inbound_message[block]",
    "block_validated": "(internal BlockChecked)",
    "block_connected": "validation:block_connected",
    "block_announce": "(internal)",
    "block_request_decision": "(internal)",
    "block_in_flight": "(internal)",
    "staller_detected": "(internal)",
    "compact_block_decision": "(internal)",
    "block_source_resolved": "(internal)",
    # Mempool
    "tx_admission": "(internal TransactionAddedToMempool)",
    "mempool_added": "mempool:added",
    "tx_removed": "mempool:removed",
    "tx_replaced": "mempool:replaced",
    "tx_rejected": "mempool:rejected",
    # UTXO cache
    "utxocache_add": "utxocache:add",
    "utxocache_spent": "utxocache:spent",
    "utxocache_uncache": "utxocache:uncache",
    "utxocache_flush": "utxocache:flush",
    # Coin selection
    "coin_selection_selected_coins": "coin_selection:selected_coins",
    "coin_selection_normal_create_tx": "coin_selection:normal_create_tx_internal",
    "coin_selection_attempting_aps": "coin_selection:attempting_aps_create_tx",
    "coin_selection_aps_create_tx": "coin_selection:aps_create_tx_internal",
}


CSV_FIELDS = [
    "tracepoint", "event_type", "event_id",
    "core_ts_us", "ipc_worker_ts_us", "ipc_latency_us",
    "params",
]


def _event_id_for(event_type, params):
    """Pick a stable identifier so eBPF and IPC logs can be joined."""
    if event_type in ("utxocache_add", "utxocache_spent", "utxocache_uncache"):
        return f"{params.get('txid','')}:{params.get('vout', 0)}"
    if event_type in ("utxocache_flush",):
        return f"flush@{params.get('timestamp_us', 0)}"
    if event_type in ("mempool_added", "tx_removed", "tx_rejected"):
        return params.get("txid", "")
    if event_type == "tx_admission":
        return params.get("txid", "")
    if event_type == "tx_replaced":
        return params.get("replaced_txid", "")
    if event_type in ("block_connected", "block_validated",
                      "block_announce", "block_request_decision",
                      "block_in_flight", "staller_detected",
                      "compact_block_decision", "block_source_resolved",
                      "block_received"):
        return params.get("hash", "")
    if event_type in ("peer_connection", "peer_closed", "peer_evicted",
                      "peer_misbehaving", "message", "outbound_message",
                      "headers"):
        return f"peer={params.get('peer_id', -1)}"
    if event_type.startswith("coin_selection_"):
        return params.get("wallet_name", "")
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True,
                    help="Destination CSV for compare_latency.py")
    ap.add_argument("--heartbeat-every", type=int, default=1000,
                    help="Print progress to stderr every N events.")
    args = ap.parse_args()

    csv_file = open(args.csv, "w", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
    writer.writeheader()

    counts = {}
    total = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        params = event.get("params", {}) or {}
        event_type = params.get("type") or event.get("method", "")
        tracepoint = TYPE_TO_TRACEPOINT.get(event_type, event_type)

        core_ts = int(params.get("timestamp_us")
                      or params.get("received_us")
                      or params.get("validated_us")
                      or 0)
        ipc_now = int(time.monotonic() * 1_000_000)
        ipc_latency = (ipc_now - core_ts) if core_ts else 0

        writer.writerow({
            "tracepoint": tracepoint,
            "event_type": event_type,
            "event_id": _event_id_for(event_type, params),
            "core_ts_us": core_ts,
            "ipc_worker_ts_us": ipc_now,
            "ipc_latency_us": ipc_latency,
            "params": json.dumps(params, separators=(",", ":")),
        })

        counts[event_type] = counts.get(event_type, 0) + 1
        total += 1
        if total % args.heartbeat_every == 0:
            print(f"[ipc_recorder] events={total}", file=sys.stderr)

    csv_file.close()
    print(json.dumps({"total": total, "by_type": counts}), file=sys.stderr)


if __name__ == "__main__":
    main()
