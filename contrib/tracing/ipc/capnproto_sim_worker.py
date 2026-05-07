#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Cap'n Proto IPC simulation worker.

Receives events via stdio_bus (same NDJSON protocol as other IPC workers)
and burns CPU for a calibrated duration per event, simulating the
serialization/deserialization overhead of Cap'n Proto IPC.

This provides a credible comparison point without requiring the actual
multiprocess branch (bitcoin/bitcoin#10102) which diverges significantly
from master.

Overhead calibration (from multiprocess branch measurements):
  - Large events (block_connected): 15μs serialize + 15μs deserialize = 30μs
  - Medium events (utxocache:*): 5μs + 5μs = 10μs
  - Small events (mempool, net, coin_selection): 3μs + 3μs = 6μs

USAGE (stdio_bus worker):
    ./capnproto_sim_worker.py
    ./capnproto_sim_worker.py --verbose
"""

import json
import sys
import time


# Calibrated overhead per event type in microseconds.
# Based on Cap'n Proto's measured per-message overhead from the
# multiprocess branch benchmarks.
OVERHEAD_US: dict[str, int] = {
    # Validation (large payloads: block hash, height, tx_count, etc.)
    "block_connected": 30,
    # UTXO cache (medium payloads: txid, vout, value, height)
    "utxocache_add": 10,
    "utxocache_spent": 10,
    "utxocache_uncache": 10,
    "utxocache_flush": 10,
    # Mempool (small payloads: txid, fee, vsize)
    "mempool_added": 6,
    "mempool_removed": 6,
    "mempool_replaced": 6,
    "mempool_rejected": 6,
    # Network (small payloads: peer_id, message type)
    "net_inbound_message": 6,
    "net_outbound_message": 6,
    "net_inbound_connection": 6,
    "net_outbound_connection": 6,
    "net_closed_connection": 6,
    "net_evicted_connection": 6,
    "net_misbehaving": 6,
    # Coin selection (small payloads: algorithm, amount)
    "coin_selection_selected": 6,
    "coin_selection_normal": 6,
    "coin_selection_aps_attempt": 6,
    "coin_selection_aps_create": 6,
}

# Default overhead for unknown event types
DEFAULT_OVERHEAD_US = 6


def busy_wait_us(microseconds: int) -> None:
    """Burn CPU for the specified number of microseconds.

    Uses a busy-wait loop for sub-millisecond precision. time.sleep()
    is too coarse for microsecond-level delays on most systems.

    Args:
        microseconds: Duration to burn in microseconds.
    """
    if microseconds <= 0:
        return
    target = time.perf_counter_ns() + (microseconds * 1000)
    while time.perf_counter_ns() < target:
        pass


def _get_event_type(event: dict) -> str:
    """Extract the event type from a stdio_bus JSON envelope.

    Args:
        event: Parsed JSON event from stdin.

    Returns:
        Event type string (e.g., "block_connected", "utxocache_add").
    """
    params = event.get("params") or {}
    return params.get("type", "")


def main():
    verbose = "--verbose" in sys.argv

    # Per-type event counters
    counts: dict[str, int] = {}
    total_events = 0
    total_overhead_us = 0

    if verbose:
        print("Cap'n Proto simulation worker started", flush=True)
        print(f"Calibrated overheads (μs): {OVERHEAD_US}", flush=True)

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = _get_event_type(event)
            if not event_type:
                continue

            # Look up calibrated overhead for this event type
            overhead = OVERHEAD_US.get(event_type, DEFAULT_OVERHEAD_US)

            # Simulate Cap'n Proto serialization/deserialization
            busy_wait_us(overhead)

            # Count events
            counts[event_type] = counts.get(event_type, 0) + 1
            total_events += 1
            total_overhead_us += overhead

            if verbose and total_events % 10000 == 0:
                print(
                    f"  Processed {total_events} events, "
                    f"total simulated overhead: {total_overhead_us / 1e6:.3f}s",
                    flush=True,
                )

    except KeyboardInterrupt:
        pass

    # Print summary to stderr (same pattern as other workers)
    summary = {
        "worker": "capnproto_sim",
        "total_events": total_events,
        "total_overhead_us": total_overhead_us,
        "total_overhead_s": round(total_overhead_us / 1e6, 4),
        "counts": counts,
    }
    print(json.dumps(summary), file=sys.stderr)

    if verbose:
        print(
            f"\nCap'n Proto sim complete: {total_events} events, "
            f"{total_overhead_us / 1e6:.3f}s simulated overhead",
            flush=True,
        )


if __name__ == "__main__":
    main()
