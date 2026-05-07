#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
Attach to every Bitcoin Core USDT tracepoint via BCC and emit a uniform CSV
that can be joined against the stdio_bus IPC recorder
(contrib/tracing/ipc/all_events_recorder.py) for latency comparison.

Coverage (20 tracepoints):
  - net:inbound_message, outbound_message
  - net:inbound_connection, outbound_connection, closed_connection,
    evicted_inbound_connection, misbehaving_connection
  - mempool:added, removed, replaced, rejected
  - validation:block_connected
  - utxocache:add, spent, uncache, flush
  - coin_selection:selected_coins, normal_create_tx_internal,
    attempting_aps_create_tx, aps_create_tx_internal

CSV columns (matches compare_latency.py expectations):
    tracepoint, event_type, event_id, core_ts_us, ebpf_worker_ts_us,
    ebpf_latency_us, params

USAGE:
  sudo python3 all_tracepoints_ebpf_recorder.py \
      --pid $(pidof bitcoind) --csv /tmp/ebpf.csv

REQUIREMENTS: BCC (python3-bcc), root privileges, Linux kernel with
BPF+USDT support.

This script intentionally mirrors the data selection of the existing
bpftrace/BCC scripts in this directory:
  - log_p2p_traffic.bt                (net:inbound_message/outbound_message)
  - log_p2p_connections.bt            (net:*_connection)
  - connectblock_benchmark.bt         (validation:block_connected)
  - log_utxocache_flush.py            (utxocache:flush)
  - log_utxos.bt                      (utxocache:add/spent/uncache)
  - mempool_monitor.py                (mempool:*)

so that `compare_latency.py` is comparing apples to apples.
"""

import argparse
import csv
import ctypes
import sys
import time


BPF_PROGRAM = r"""
#include <uapi/linux/ptrace.h>

// Fixed-width event used for every tracepoint. We inline string args as
// fixed-size char arrays to stay within the eBPF stack budget.
#define MAX_STR 64

struct event_t {
    u64 core_ts_us;        // Bitcoin Core monotonic us (when available)
    u64 kernel_ts_us;      // kernel monotonic us at tracepoint
    u32 type_id;           // see TYPE_* below
    s64 int_a;
    s64 int_b;
    s64 int_c;
    u64 uint_a;
    u64 uint_b;
    u8  bool_a;
    char str_a[MAX_STR];
    char str_b[MAX_STR];
    char hash[32];
};

BPF_PERF_OUTPUT(events);

#define TYPE_INBOUND_MESSAGE         1
#define TYPE_OUTBOUND_MESSAGE        2
#define TYPE_INBOUND_CONNECTION      3
#define TYPE_OUTBOUND_CONNECTION     4
#define TYPE_CLOSED_CONNECTION       5
#define TYPE_EVICTED_CONNECTION      6
#define TYPE_MISBEHAVING_CONNECTION  7
#define TYPE_MEMPOOL_ADDED           8
#define TYPE_MEMPOOL_REMOVED         9
#define TYPE_MEMPOOL_REPLACED       10
#define TYPE_MEMPOOL_REJECTED       11
#define TYPE_VALIDATION_BLOCK_CONNECTED 12
#define TYPE_UTXOCACHE_ADD          13
#define TYPE_UTXOCACHE_SPENT        14
#define TYPE_UTXOCACHE_UNCACHE      15
#define TYPE_UTXOCACHE_FLUSH        16
#define TYPE_COIN_SELECTION_SELECTED 17
#define TYPE_COIN_SELECTION_NORMAL   18
#define TYPE_COIN_SELECTION_APS_ATTEMPT 19
#define TYPE_COIN_SELECTION_APS      20

static __always_inline u64 now_us() {
    return bpf_ktime_get_ns() / 1000;
}

// === net === ==============================================================

int trace_inbound_message(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_INBOUND_MESSAGE;
    bpf_usdt_readarg(1, ctx, &e.int_a);        // peer_id
    u64 addr_p, mtype_p;
    bpf_usdt_readarg(2, ctx, &addr_p);
    bpf_probe_read_user_str(&e.str_a, sizeof(e.str_a), (void*)addr_p);
    bpf_usdt_readarg(4, ctx, &mtype_p);
    bpf_probe_read_user_str(&e.str_b, sizeof(e.str_b), (void*)mtype_p);
    bpf_usdt_readarg(5, ctx, &e.uint_a);       // size
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

int trace_outbound_message(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_OUTBOUND_MESSAGE;
    bpf_usdt_readarg(1, ctx, &e.int_a);
    u64 addr_p, mtype_p;
    bpf_usdt_readarg(2, ctx, &addr_p);
    bpf_probe_read_user_str(&e.str_a, sizeof(e.str_a), (void*)addr_p);
    bpf_usdt_readarg(4, ctx, &mtype_p);
    bpf_probe_read_user_str(&e.str_b, sizeof(e.str_b), (void*)mtype_p);
    bpf_usdt_readarg(5, ctx, &e.uint_a);
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

#define CONN_PROBE(NAME, TID)                              \
int trace_##NAME(struct pt_regs *ctx) {                     \
    struct event_t e = {};                                  \
    e.kernel_ts_us = now_us();                              \
    e.type_id = TID;                                        \
    bpf_usdt_readarg(1, ctx, &e.int_a);                     \
    u64 addr_p;                                             \
    bpf_usdt_readarg(2, ctx, &addr_p);                      \
    bpf_probe_read_user_str(&e.str_a, sizeof(e.str_a), (void*)addr_p); \
    events.perf_submit(ctx, &e, sizeof(e));                 \
    return 0;                                               \
}

CONN_PROBE(inbound_connection, TYPE_INBOUND_CONNECTION)
CONN_PROBE(outbound_connection, TYPE_OUTBOUND_CONNECTION)
CONN_PROBE(closed_connection, TYPE_CLOSED_CONNECTION)
CONN_PROBE(evicted_inbound_connection, TYPE_EVICTED_CONNECTION)

int trace_misbehaving_connection(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_MISBEHAVING_CONNECTION;
    bpf_usdt_readarg(1, ctx, &e.int_a);
    u64 msg_p;
    bpf_usdt_readarg(2, ctx, &msg_p);
    bpf_probe_read_user_str(&e.str_a, sizeof(e.str_a), (void*)msg_p);
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

// === mempool === ==========================================================

#define MEMPOOL_PROBE_ADDED                                 \
int trace_mempool_added(struct pt_regs *ctx) {              \
    struct event_t e = {};                                  \
    e.kernel_ts_us = now_us();                              \
    e.type_id = TYPE_MEMPOOL_ADDED;                         \
    u64 hash_p;                                             \
    bpf_usdt_readarg(1, ctx, &hash_p);                      \
    bpf_probe_read_user(&e.hash, 32, (void*)hash_p);        \
    bpf_usdt_readarg(2, ctx, &e.uint_a);                    \
    bpf_usdt_readarg(3, ctx, &e.int_a);                     \
    events.perf_submit(ctx, &e, sizeof(e));                 \
    return 0;                                               \
}
MEMPOOL_PROBE_ADDED

int trace_mempool_removed(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_MEMPOOL_REMOVED;
    u64 hash_p, reason_p;
    bpf_usdt_readarg(1, ctx, &hash_p);
    bpf_probe_read_user(&e.hash, 32, (void*)hash_p);
    bpf_usdt_readarg(2, ctx, &reason_p);
    bpf_probe_read_user_str(&e.str_a, sizeof(e.str_a), (void*)reason_p);
    bpf_usdt_readarg(3, ctx, &e.uint_a);
    bpf_usdt_readarg(4, ctx, &e.int_a);
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

int trace_mempool_replaced(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_MEMPOOL_REPLACED;
    u64 old_hash, new_hash;
    bpf_usdt_readarg(1, ctx, &old_hash);
    bpf_probe_read_user(&e.hash, 32, (void*)old_hash);
    bpf_usdt_readarg(5, ctx, &new_hash);
    bpf_usdt_readarg(2, ctx, &e.uint_a);
    bpf_usdt_readarg(3, ctx, &e.int_a);
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

int trace_mempool_rejected(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_MEMPOOL_REJECTED;
    u64 hash_p, reason_p;
    bpf_usdt_readarg(1, ctx, &hash_p);
    bpf_probe_read_user(&e.hash, 32, (void*)hash_p);
    bpf_usdt_readarg(2, ctx, &reason_p);
    bpf_probe_read_user_str(&e.str_a, sizeof(e.str_a), (void*)reason_p);
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

// === validation === =======================================================

int trace_block_connected(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_VALIDATION_BLOCK_CONNECTED;
    u64 hash_p;
    bpf_usdt_readarg(1, ctx, &hash_p);
    bpf_probe_read_user(&e.hash, 32, (void*)hash_p);
    bpf_usdt_readarg(2, ctx, &e.int_a);        // height
    bpf_usdt_readarg(3, ctx, &e.int_b);        // tx_count
    bpf_usdt_readarg(6, ctx, &e.uint_a);       // duration_ns
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

// === utxocache === ========================================================

#define UTXOCACHE_PROBE(NAME, TID)                          \
int trace_##NAME(struct pt_regs *ctx) {                     \
    struct event_t e = {};                                  \
    e.kernel_ts_us = now_us();                              \
    e.type_id = TID;                                        \
    u64 hash_p;                                             \
    bpf_usdt_readarg(1, ctx, &hash_p);                      \
    bpf_probe_read_user(&e.hash, 32, (void*)hash_p);        \
    bpf_usdt_readarg(2, ctx, &e.uint_a);                    \
    bpf_usdt_readarg(3, ctx, &e.uint_b);                    \
    bpf_usdt_readarg(4, ctx, &e.int_a);                     \
    bpf_usdt_readarg(5, ctx, &e.bool_a);                    \
    events.perf_submit(ctx, &e, sizeof(e));                 \
    return 0;                                               \
}

UTXOCACHE_PROBE(utxocache_add, TYPE_UTXOCACHE_ADD)
UTXOCACHE_PROBE(utxocache_spent, TYPE_UTXOCACHE_SPENT)
UTXOCACHE_PROBE(utxocache_uncache, TYPE_UTXOCACHE_UNCACHE)

int trace_utxocache_flush(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_UTXOCACHE_FLUSH;
    bpf_usdt_readarg(1, ctx, &e.int_a);        // duration_us
    bpf_usdt_readarg(2, ctx, &e.uint_a);       // mode
    bpf_usdt_readarg(3, ctx, &e.uint_b);       // coins_count
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

// === coin_selection === ===================================================

int trace_cs_selected(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_COIN_SELECTION_SELECTED;
    u64 wallet_p, algo_p;
    bpf_usdt_readarg(1, ctx, &wallet_p);
    bpf_probe_read_user_str(&e.str_a, sizeof(e.str_a), (void*)wallet_p);
    bpf_usdt_readarg(2, ctx, &algo_p);
    bpf_probe_read_user_str(&e.str_b, sizeof(e.str_b), (void*)algo_p);
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

int trace_cs_normal(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_COIN_SELECTION_NORMAL;
    u64 wallet_p;
    bpf_usdt_readarg(1, ctx, &wallet_p);
    bpf_probe_read_user_str(&e.str_a, sizeof(e.str_a), (void*)wallet_p);
    bpf_usdt_readarg(2, ctx, &e.bool_a);
    bpf_usdt_readarg(3, ctx, &e.int_a);
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

int trace_cs_aps_attempt(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_COIN_SELECTION_APS_ATTEMPT;
    u64 wallet_p;
    bpf_usdt_readarg(1, ctx, &wallet_p);
    bpf_probe_read_user_str(&e.str_a, sizeof(e.str_a), (void*)wallet_p);
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}

int trace_cs_aps(struct pt_regs *ctx) {
    struct event_t e = {};
    e.kernel_ts_us = now_us();
    e.type_id = TYPE_COIN_SELECTION_APS;
    u64 wallet_p;
    bpf_usdt_readarg(1, ctx, &wallet_p);
    bpf_probe_read_user_str(&e.str_a, sizeof(e.str_a), (void*)wallet_p);
    bpf_usdt_readarg(2, ctx, &e.bool_a);
    bpf_usdt_readarg(3, ctx, &e.bool_a);
    bpf_usdt_readarg(4, ctx, &e.int_a);
    events.perf_submit(ctx, &e, sizeof(e));
    return 0;
}
"""


TYPE_NAMES = {
    1: ("net:inbound_message", "message"),
    2: ("net:outbound_message", "outbound_message"),
    3: ("net:inbound_connection", "peer_connection"),
    4: ("net:outbound_connection", "peer_connection"),
    5: ("net:closed_connection", "peer_closed"),
    6: ("net:evicted_inbound_connection", "peer_evicted"),
    7: ("net:misbehaving_connection", "peer_misbehaving"),
    8: ("mempool:added", "mempool_added"),
    9: ("mempool:removed", "tx_removed"),
    10: ("mempool:replaced", "tx_replaced"),
    11: ("mempool:rejected", "tx_rejected"),
    12: ("validation:block_connected", "block_connected"),
    13: ("utxocache:add", "utxocache_add"),
    14: ("utxocache:spent", "utxocache_spent"),
    15: ("utxocache:uncache", "utxocache_uncache"),
    16: ("utxocache:flush", "utxocache_flush"),
    17: ("coin_selection:selected_coins", "coin_selection_selected_coins"),
    18: ("coin_selection:normal_create_tx_internal", "coin_selection_normal_create_tx"),
    19: ("coin_selection:attempting_aps_create_tx", "coin_selection_attempting_aps"),
    20: ("coin_selection:aps_create_tx_internal", "coin_selection_aps_create_tx"),
}


PROBES = [
    ("net", "inbound_message", "trace_inbound_message"),
    ("net", "outbound_message", "trace_outbound_message"),
    ("net", "inbound_connection", "trace_inbound_connection"),
    ("net", "outbound_connection", "trace_outbound_connection"),
    ("net", "closed_connection", "trace_closed_connection"),
    ("net", "evicted_inbound_connection", "trace_evicted_inbound_connection"),
    ("net", "misbehaving_connection", "trace_misbehaving_connection"),
    ("mempool", "added", "trace_mempool_added"),
    ("mempool", "removed", "trace_mempool_removed"),
    ("mempool", "replaced", "trace_mempool_replaced"),
    ("mempool", "rejected", "trace_mempool_rejected"),
    ("validation", "block_connected", "trace_block_connected"),
    ("utxocache", "add", "trace_utxocache_add"),
    ("utxocache", "spent", "trace_utxocache_spent"),
    ("utxocache", "uncache", "trace_utxocache_uncache"),
    ("utxocache", "flush", "trace_utxocache_flush"),
    ("coin_selection", "selected_coins", "trace_cs_selected"),
    ("coin_selection", "normal_create_tx_internal", "trace_cs_normal"),
    ("coin_selection", "attempting_aps_create_tx", "trace_cs_aps_attempt"),
    ("coin_selection", "aps_create_tx_internal", "trace_cs_aps"),
]


CSV_FIELDS = [
    "tracepoint", "event_type", "event_id",
    "core_ts_us", "ebpf_worker_ts_us", "ebpf_latency_us",
    "params",
]


def _event_id(type_id, event):
    tp, etype = TYPE_NAMES[type_id]
    h = bytes(event.hash).hex()
    if etype in ("mempool_added", "tx_removed", "tx_replaced", "tx_rejected"):
        return h
    if etype in ("utxocache_add", "utxocache_spent", "utxocache_uncache"):
        return f"{h}:{int(event.uint_a)}"
    if etype in ("block_connected",):
        return h
    if etype in ("message", "outbound_message",
                 "peer_connection", "peer_closed", "peer_evicted",
                 "peer_misbehaving"):
        return f"peer={int(event.int_a)}"
    if etype.startswith("coin_selection_"):
        return bytes(event.str_a).split(b"\x00", 1)[0].decode("utf-8", "replace")
    if etype == "utxocache_flush":
        return f"flush@{int(event.kernel_ts_us)}"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--duration", type=int, default=0,
                    help="Stop after N seconds (0 = run until Ctrl-C).")
    args = ap.parse_args()

    try:
        from bcc import BPF, USDT
    except ImportError:
        print("BCC not installed. Install python3-bcc and rerun with sudo.", file=sys.stderr)
        sys.exit(1)

    usdt = USDT(pid=args.pid)
    for context, name, handler in PROBES:
        try:
            usdt.enable_probe(probe=f"{context}:{name}", fn_name=handler)
        except Exception as exc:
            print(f"[warn] probe {context}:{name} not enabled: {exc}", file=sys.stderr)

    bpf = BPF(text=BPF_PROGRAM, usdt_contexts=[usdt])

    csv_file = open(args.csv, "w", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
    writer.writeheader()

    total = [0]

    def handle(cpu, data, size):
        event = bpf["events"].event(data)
        type_id = int(event.type_id)
        if type_id not in TYPE_NAMES:
            return
        tp, etype = TYPE_NAMES[type_id]
        core_ts = int(event.core_ts_us)  # currently 0 (USDT doesn't carry
                                         # Core's GetMonotonicTimeUs())
        ebpf_ts = int(event.kernel_ts_us)
        # For USDT side the "latency" we report is the bpf dispatch delay
        # which is 0 in the event context; compare_latency.py recomputes
        # it as ebpf_ts - core_ts once IPC stamps are present.
        writer.writerow({
            "tracepoint": tp,
            "event_type": etype,
            "event_id": _event_id(type_id, event),
            "core_ts_us": core_ts,
            "ebpf_worker_ts_us": ebpf_ts,
            "ebpf_latency_us": 0,
            "params": "{}",
        })
        total[0] += 1

    bpf["events"].open_perf_buffer(handle, page_cnt=256)

    start = time.monotonic()
    try:
        while True:
            bpf.perf_buffer_poll(timeout=500)
            if args.duration and (time.monotonic() - start) >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        csv_file.close()
        print(f"[ebpf_recorder] total_events={total[0]}", file=sys.stderr)


if __name__ == "__main__":
    main()
