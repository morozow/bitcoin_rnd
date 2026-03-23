# stdio_bus Integration Design Document

## Overview

This document describes the integration of stdio_bus into Bitcoin Core for performance optimization and security research. The integration follows Bitcoin Core's contribution guidelines and maintains consensus safety.

## Goals

1. **Performance Optimization**: Address issues #21803, #27623, #27677, #18678
2. **Security Research**: Enable controlled message delivery for vulnerability discovery
3. **Observability**: Shadow-mode telemetry without affecting consensus

## Non-Goals

- Modifying consensus logic
- Changing P2P protocol semantics
- Breaking backward compatibility

## Architecture

### Integration Points

```
┌─────────────────────────────────────────────────────────────┐
│                      Bitcoin Core                            │
├─────────────────────────────────────────────────────────────┤
│  init.cpp                                                    │
│    └── PeerManager::make() ← inject StdioBusHooks           │
├─────────────────────────────────────────────────────────────┤
│  net.cpp                                                     │
│    └── CConnman::ThreadMessageHandler ← OnMsgHandlerLoop    │
├─────────────────────────────────────────────────────────────┤
│  net_processing.cpp                                          │
│    ├── ProcessMessage ← OnMessage                           │
│    ├── HEADERS branch ← OnHeaders                           │
│    └── ProcessBlock ← OnBlockReceived                       │
├─────────────────────────────────────────────────────────────┤
│  validation.cpp                                              │
│    └── ProcessNewBlock ← OnBlockValidated                   │
├─────────────────────────────────────────────────────────────┤
│  txmempool.cpp                                               │
│    └── AcceptToMemoryPool ← OnTxAdmission                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    StdioBusHooks Interface                   │
│  (src/node/stdio_bus_hooks.h)                               │
│                                                              │
│  - Shadow mode only (observe, don't modify)                 │
│  - Non-blocking callbacks                                    │
│  - Bounded queue for async processing                       │
│  - Fail-open on errors                                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    stdio_bus C++ SDK                         │
│  (src/stdio_bus/)                                           │
│                                                              │
│  - stdiobus::Bus (RAII)                                     │
│  - Callbacks (on_message, on_error)                         │
│  - TCP/Unix/Embedded modes                                   │
└─────────────────────────────────────────────────────────────┘
```

### Feature Flag

```
-stdiobus=<mode>    Enable stdio_bus integration
                    off     - Disabled (default)
                    shadow  - Observe only, no behavior change
                    active  - Enable optimizations (future)
```

## Baseline Metrics

### #21803: Block Processing Delays

| Metric | Description | Sampling Point |
|--------|-------------|----------------|
| `block_announce_to_process_start_ms` | Time from HEADERS/CMPCTBLOCK to ProcessBlock entry | HEADERS branch → ProcessBlock |
| `block_request_to_receive_ms` | Time from GETDATA to BLOCK/BLOCKTXN received | BlockRequested → block received |
| `block_receive_to_accept_ms` | Time from ProcessBlock to ProcessNewBlock complete | ProcessBlock → ProcessNewBlock |
| `inflight_block_count` | Blocks in-flight per peer | BlockRequested tracking |
| `peer_selection_churn` | Times block source was re-selected | Peer selection logic |

### #27623: Message Handler Saturation

| Metric | Description | Sampling Point |
|--------|-------------|----------------|
| `msghand_loop_cycle_ms` | Duration of ThreadMessageHandler iteration | Loop start/end |
| `process_message_cpu_ms` | CPU time per ProcessMessage by msg_type | ProcessMessage entry/exit |
| `message_queue_wait_ms` | Time message waited in queue | Queue entry → ProcessMessage |
| `headers_parse_ms` | Headers deserialization time | HEADERS parsing |
| `block_parse_ms` | Block deserialization time | BLOCK parsing |
| `msghand_cpu_utilization_pct` | CPU utilization of msghand thread | perf/tracepoints |

### #27677: Mempool Performance

| Metric | Description | Sampling Point |
|--------|-------------|----------------|
| `tx_admission_latency_ms` | Time from TX received to AcceptToMemoryPool result | TX received → ATMP complete |
| `tx_admission_throughput_tps` | Transactions per second through admission | Counter over time window |
| `mempool_lock_wait_ms` | Lock contention on mempool.cs, cs_main | Lock acquire timing |
| `package_accept_latency_ms` | Package validation latency | ProcessNewPackage |
| `mempool_eviction_rate` | Evictions per second | TrimToSize/Expire |

### #18678: P2P/RPC Degradation

| Metric | Description | Sampling Point |
|--------|-------------|----------------|
| `rpc_latency_ms` | RPC latency by method (P50/P95/P99) | RPC entry/exit |
| `rpc_qps_sustained` | Sustained QPS under P2P load | RPC counter |
| `p2p_rpc_interference` | RPC latency increase vs P2P throughput | Correlation analysis |
| `http_queue_depth` | HTTP server queue depth | HTTP server |
| `eventloop_delay_ms` | Delay between network receive and RPC response | Event loop timing |

## Event Log Format

All events are logged in NDJSON format with monotonic timestamps:

```json
{"ts_us": 1234567890123, "event": "headers_received", "peer_id": 42, "count": 2000, "first_prev": "00000..."}
{"ts_us": 1234567890456, "event": "block_requested", "peer_id": 42, "hash": "00000...", "height": 800000}
{"ts_us": 1234567891234, "event": "block_validated", "hash": "00000...", "height": 800000, "duration_us": 778}
{"ts_us": 1234567892000, "event": "tx_admitted", "txid": "abc123...", "duration_us": 1234, "result": "accepted"}
{"ts_us": 1234567893000, "event": "rpc_call", "method": "getblockchaininfo", "duration_us": 567}
```

## Event Schema (v1.0)

Stable event schema for baseline comparisons. All timestamps are monotonic microseconds.

### MessageEvent
| Field | Type | Description |
|-------|------|-------------|
| `peer_id` | int64 | Node ID of the peer |
| `msg_type` | string | P2P message type (e.g., "headers", "block", "tx") |
| `size_bytes` | size_t | Message size in bytes |
| `received_us` | int64 | Monotonic timestamp when received |

### HeadersEvent
| Field | Type | Description |
|-------|------|-------------|
| `peer_id` | int64 | Node ID of the peer |
| `count` | size_t | Number of headers in message |
| `first_prev_hash` | uint256 | Previous block hash of first header |
| `received_us` | int64 | Monotonic timestamp when received |

### BlockReceivedEvent
| Field | Type | Description |
|-------|------|-------------|
| `peer_id` | int64 | Node ID of the peer |
| `hash` | uint256 | Block hash |
| `height` | int | Block height (-1 if unknown) |
| `size_bytes` | size_t | Block size in bytes |
| `tx_count` | size_t | Number of transactions |
| `received_us` | int64 | Monotonic timestamp when received |

### BlockValidatedEvent
| Field | Type | Description |
|-------|------|-------------|
| `hash` | uint256 | Block hash |
| `height` | int | Block height |
| `tx_count` | size_t | Number of transactions |
| `received_us` | int64 | Monotonic timestamp when received |
| `validated_us` | int64 | Monotonic timestamp when validation completed |
| `accepted` | bool | Whether block was accepted |
| `reject_reason` | string | Rejection reason (empty if accepted) |

### TxAdmissionEvent
| Field | Type | Description |
|-------|------|-------------|
| `txid` | uint256 | Transaction ID |
| `wtxid` | uint256 | Witness transaction ID |
| `size_bytes` | size_t | Transaction size in bytes |
| `received_us` | int64 | Monotonic timestamp when received |
| `processed_us` | int64 | Monotonic timestamp when processed |
| `accepted` | bool | Whether transaction was accepted |
| `reject_reason` | string | Rejection reason (empty if accepted) |

### MsgHandlerLoopEvent
| Field | Type | Description |
|-------|------|-------------|
| `iteration` | int64 | Loop iteration counter |
| `start_us` | int64 | Monotonic timestamp at loop start |
| `end_us` | int64 | Monotonic timestamp at loop end |
| `messages_processed` | int | Number of messages processed |
| `had_work` | bool | Whether there was work to do |

### RpcCallEvent
| Field | Type | Description |
|-------|------|-------------|
| `method` | string | RPC method name |
| `start_us` | int64 | Monotonic timestamp at call start |
| `end_us` | int64 | Monotonic timestamp at call end |
| `success` | bool | Whether call succeeded |

## Consensus Safety Invariants

1. **No consensus decisions through stdio_bus** - All validation logic unchanged
2. **Async mechanisms don't affect acceptance** - Final result identical to baseline
3. **Fail-open on hook errors** - Return to standard path on any failure
4. **No modification of message content** - Hooks are read-only observers
5. **No lock inversion** - Hooks must not acquire locks held by callers
6. **No blocking I/O** - All hook callbacks must be non-blocking

## Lock and Latency Budget

### Latency Requirements

| Hook | Max Latency | Rationale |
|------|-------------|-----------|
| `OnMessage` | ≤100μs | Hot path in message handler loop |
| `OnHeaders` | ≤100μs | Called for every HEADERS message |
| `OnBlockReceived` | ≤500μs | Less frequent, larger event struct |
| `OnBlockValidated` | ≤500μs | Called from validation thread |
| `OnTxAdmission` | ≤100μs | High frequency during mempool activity |
| `OnMsgHandlerLoop` | ≤50μs | Called every loop iteration |
| `OnRpcCall` | ≤100μs | RPC latency sensitive |

**Total overhead target**: ≤1ms per message handler loop iteration in shadow mode.

### Lock Ordering Rules

Hooks are called while holding various locks. Implementations MUST NOT:

1. **Acquire `cs_main`** - Already held during validation hooks
2. **Acquire `m_peer_mutex`** - Already held during P2P hooks
3. **Acquire `mempool.cs`** - May be held during tx admission
4. **Perform blocking I/O** - Use bounded async queue instead
5. **Allocate unbounded memory** - Use pre-allocated buffers

### Recommended Implementation Pattern

```cpp
class StdioBusSdkHooks : public StdioBusHooks {
    // Bounded lock-free queue (SPSC or MPSC)
    BoundedQueue<Event, 4096> m_queue;
    
    // Background thread for I/O
    std::thread m_worker;
    
    void OnMessage(const MessageEvent& ev) override {
        // Fast path: try_push is lock-free, O(1)
        if (!m_queue.try_push(ev)) {
            // Queue full - drop event (fail-open)
            ++m_dropped_events;
        }
    }
};
```

### Fail-Open Behavior

On any error condition, hooks MUST fail silently and allow normal processing:

| Condition | Behavior |
|-----------|----------|
| Queue full | Drop event, increment counter |
| SDK error | Log debug, continue |
| Exception thrown | Catch, log, continue |
| Timeout | Skip event, continue |
| Memory allocation failure | Skip event, continue |

### Monitoring

Shadow mode should track:

- `stdio_bus_events_total` - Total events by type
- `stdio_bus_events_dropped` - Dropped events (queue full)
- `stdio_bus_hook_latency_us` - Hook callback latency histogram
- `stdio_bus_queue_depth` - Current queue depth

## Known Limitations (Phase 1)

1. **OnTxAdmission only covers successful admissions** - Rejections via `TransactionAddedToMempool` 
   are not captured. Full reject telemetry requires instrumentation in `AcceptToMemoryPool`.

2. **Block receive time approximation** - `BlockValidatedEvent.received_us` may equal 
   `validated_us` if block wasn't tracked through `OnBlockReceived` first.

3. **No RPC hooks yet** - `OnRpcCall` is defined but not wired in Phase 1.

## Phase 4: Mempool Redesign Preparation (#27677)

Phase 4 adds comprehensive mempool observability for the mempool redesign effort.

### New Event Types

#### TxAdmissionSource
Identifies the source of transaction admission:
- `P2P` (0) - Received from peer
- `RPC` (1) - Submitted via RPC
- `Reorg` (2) - Re-added after reorg
- `Package` (3) - Part of package submission
- `Wallet` (4) - From wallet

#### MempoolAdmissionResult
Result of mempool admission attempt:
- `Accepted` (0) - Successfully added
- `Rejected` (1) - Rejected (policy or consensus)
- `MempoolEntry` (2) - Already in mempool
- `DifferentWitness` (3) - Same txid, different witness
- `PackageRejected` (4) - Rejected as part of package

#### MempoolEvictionReason
Reason for transaction eviction:
- `SizeLimit` (0) - Mempool size limit
- `Expiry` (1) - Transaction expired
- `Reorg` (2) - Removed during reorg
- `Replaced` (3) - Replaced by RBF
- `Conflict` (4) - Conflicting transaction
- `BlockConfirm` (5) - Confirmed in block

### New Events

#### MempoolAdmissionAttemptEvent
Fired at entry to `AcceptToMemoryPool`:
| Field | Type | Description |
|-------|------|-------------|
| `txid` | uint256 | Transaction ID |
| `wtxid` | uint256 | Witness transaction ID |
| `source` | TxAdmissionSource | Source of admission |
| `vsize` | int32 | Virtual size |
| `fee_sat` | int64 | Fee in satoshis |
| `timestamp_us` | int64 | Monotonic timestamp |

#### MempoolAdmissionResultEvent
Fired at exit from `AcceptToMemoryPool`:
| Field | Type | Description |
|-------|------|-------------|
| `txid` | uint256 | Transaction ID |
| `wtxid` | uint256 | Witness transaction ID |
| `result` | MempoolAdmissionResult | Admission result |
| `reject_code` | int32 | Rejection code (0 if accepted) |
| `reject_reason` | string | Rejection reason |
| `replaced_count` | int32 | Number of replaced transactions |
| `effective_feerate_sat_vb` | int64 | Effective feerate × 1000 |
| `start_us` | int64 | Start timestamp |
| `end_us` | int64 | End timestamp |

#### PackageAdmissionEvent
Fired for `ProcessNewPackage`:
| Field | Type | Description |
|-------|------|-------------|
| `package_hash` | uint256 | Hash of sorted txids |
| `strategy` | PackageOrderingStrategy | Ordering strategy used |
| `tx_count` | int32 | Number of transactions |
| `total_vsize` | int32 | Total virtual size |
| `total_fees_sat` | int64 | Total fees |
| `accepted_count` | int32 | Accepted transactions |
| `rejected_count` | int32 | Rejected transactions |
| `start_us` | int64 | Start timestamp |
| `end_us` | int64 | End timestamp |

#### MempoolBatchEvent
Fired for batch operations (`Apply`, `TrimToSize`, etc.):
| Field | Type | Description |
|-------|------|-------------|
| `batch_type` | MempoolBatchType | Type of batch operation |
| `tx_count_in` | int32 | Transactions entering |
| `tx_count_out` | int32 | Transactions remaining |
| `bytes_affected` | int64 | Bytes affected |
| `start_us` | int64 | Start timestamp |
| `end_us` | int64 | End timestamp |

#### MempoolOrderingEvent
Fired for ordering/work operations:
| Field | Type | Description |
|-------|------|-------------|
| `phase` | MempoolOrderingPhase | Ordering phase |
| `candidate_count` | int32 | Candidate transactions |
| `cluster_count` | int32 | Number of clusters |
| `work_budget` | int64 | Work budget |
| `work_used` | int64 | Work consumed |
| `start_us` | int64 | Start timestamp |
| `end_us` | int64 | End timestamp |

#### MempoolEvictionEvent
Fired when transactions are evicted:
| Field | Type | Description |
|-------|------|-------------|
| `reason` | MempoolEvictionReason | Eviction reason |
| `tx_count` | int32 | Transactions evicted |
| `bytes_removed` | int64 | Bytes removed |
| `fees_removed_sat` | int64 | Fees removed |
| `timestamp_us` | int64 | Monotonic timestamp |

### Hook Points

| Location | Event | Description |
|----------|-------|-------------|
| `validation.cpp:AcceptToMemoryPool` entry | `OnMempoolAdmissionAttempt` | Track admission start |
| `validation.cpp:AcceptToMemoryPool` exit | `OnMempoolAdmissionResult` | Track admission result |
| `validation.cpp:ProcessNewPackage` | `OnPackageAdmission` | Track package processing |
| `txmempool.cpp:Apply` | `OnMempoolBatch`, `OnMempoolOrdering` | Track batch operations |
| `txmempool.cpp:TrimToSize` | `OnMempoolEviction` | Track size limit evictions |
| `txmempool.cpp:Expire` | `OnMempoolEviction` | Track expiry evictions |

### Metrics Enabled

| Metric | Description |
|--------|-------------|
| `tx_admission_latency_us` | End-to-end admission latency |
| `package_admission_latency_us` | Package processing latency |
| `admission_throughput_tps` | Transactions per second |
| `mempool_lock_wait_us` | Lock contention time |
| `ordering_cost_us` | TxGraph work cost |
| `eviction_rate` | Evictions per second by reason |

### Wiring

stdio_bus_hooks is wired to mempool via `MemPoolOptions::stdio_bus_hooks` in `init.cpp` 
after PeerManager creation. This ensures hooks are available for all mempool operations.

## Test Requirements

Before merge, all changes must pass:
- `test_bitcoin` (unit tests)
- `test/functional/` (functional tests)
- Fuzz targets
- Sanitizers (ASan, UBSan, TSan)
- Performance regression check (baseline comparison)

## Implementation Phases

### Phase 0: Baseline (This Document)
- Define metrics and methodology
- Create perf harness
- Establish reproducible baseline

### Phase 1: Shadow Hooks
- StdioBusHooks interface
- Injection via PeerManager::Options
- Shadow-mode telemetry

### Phase 2-5: Optimizations
- Address specific issues with measured improvements
- Each optimization behind feature flag

### Phase 6: Security Research
- Controlled fault injection
- Race condition campaigns
- Differential testing

### Phase 7: Upstream
- PR stack preparation
- Documentation
- Review process

## References

- [#21803: Block processing delays](https://github.com/bitcoin/bitcoin/issues/21803)
- [#27623: CPU 100% message handling](https://github.com/bitcoin/bitcoin/issues/27623)
- [#27677: Mempool redesign](https://github.com/bitcoin/bitcoin/issues/27677)
- [#18678: P2P/RPC degradation](https://github.com/bitcoin/bitcoin/issues/18678)
- [Bitcoin Core Developer Notes](https://github.com/bitcoin/bitcoin/blob/master/doc/developer-notes.md)
