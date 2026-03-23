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

## Phase 5: P2P/RPC Degradation Events (#18678)

Phase 5 adds comprehensive RPC/HTTP layer monitoring to diagnose and address
P2P/RPC interference patterns on resource-constrained systems.

### New Event Types

#### RpcHttpEnqueueEvent
Fired when an HTTP request is received and queued (or rejected).

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | int64 | Unique request identifier |
| `uri` | string | Request URI (e.g., "/", "/wallet/") |
| `peer_addr` | string | Client address |
| `received_us` | int64 | When request was received |
| `queue_depth` | int | Queue depth at admission time |
| `max_queue_depth` | int | Maximum queue capacity |
| `admitted` | bool | Whether request was admitted |
| `reject_reason` | enum | Reason if rejected (None, QueueFull, P2PLoad, etc.) |

#### RpcHttpDispatchEvent
Fired when an HTTP request is dispatched to a worker thread.

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | int64 | Unique request identifier |
| `enqueued_us` | int64 | When request was enqueued |
| `dispatched_us` | int64 | When request was dispatched |
| `worker_id` | int | Worker thread ID (0-based) |
| `active_workers` | int | Number of active workers |
| `total_workers` | int | Total worker pool size |

#### RpcCallLifecycleEvent
Comprehensive event capturing the entire RPC call lifecycle.

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | int64 | Unique request identifier |
| `method` | string | RPC method name |
| `peer_addr` | string | Client address |
| `priority` | enum | Method priority (High/Medium/Low) |
| `http_received_us` | int64 | HTTP request received |
| `queue_entered_us` | int64 | Entered work queue |
| `dispatch_us` | int64 | Dispatched to worker |
| `parse_start_us` | int64 | JSON parsing started |
| `exec_start_us` | int64 | RPC execution started |
| `exec_end_us` | int64 | RPC execution completed |
| `response_sent_us` | int64 | HTTP response sent |
| `success` | bool | Whether call succeeded |
| `http_status` | int | HTTP status code |
| `response_size` | size_t | Response size in bytes |

#### RpcBackpressureEvent
Fired when a QoS/backpressure decision is made.

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | int64 | Unique request identifier |
| `method` | string | RPC method (if known) |
| `timestamp_us` | int64 | When decision was made |
| `decision` | enum | Action taken (Admit/Reject/Throttle/Prioritize) |
| `reason` | enum | Why this decision |
| `queue_depth` | int | Current queue depth |
| `active_rpc_calls` | int | Active RPC calls |
| `p2p_load_score` | double | P2P subsystem load (0.0-1.0) |
| `method_calls_last_sec` | int64 | Calls to this method in last second |

#### P2PRpcInterferenceSnapshotEvent
Periodic snapshot for correlation analysis.

| Field | Type | Description |
|-------|------|-------------|
| `timestamp_us` | int64 | Snapshot timestamp |
| `snapshot_interval_us` | int64 | Time since last snapshot |
| `p2p_messages_processed` | int | Messages processed in interval |
| `p2p_processing_us` | int64 | Total P2P processing time |
| `p2p_queue_depth` | int | Current P2P message queue depth |
| `connected_peers` | int | Number of connected peers |
| `rpc_calls_completed` | int | RPC calls completed in interval |
| `rpc_total_latency_us` | int64 | Total RPC latency in interval |
| `rpc_queue_depth` | int | Current RPC queue depth |
| `active_rpc_calls` | int | Currently executing RPC calls |
| `rpc_latency_p50_us` | int64 | 50th percentile latency |
| `rpc_latency_p95_us` | int64 | 95th percentile latency |
| `rpc_latency_p99_us` | int64 | 99th percentile latency |
| `p2p_load_score` | double | P2P load (0.0-1.0) |
| `rpc_degradation_score` | double | RPC degradation vs baseline |
| `interference_correlation` | double | Correlation coefficient |

### RPC Method Priority Classification

Methods are classified for QoS decisions:

| Priority | Methods | Rationale |
|----------|---------|-----------|
| High | stop, getblockchaininfo, getnetworkinfo, ping, help | Critical control/status |
| Medium | sendtoaddress, getnewaddress, etc. | Normal operations |
| Low | scantxoutset, rescanblockchain, importwallet, getblock | Heavy/long-running |

### Hook Points

| File | Function | Hook |
|------|----------|------|
| `httpserver.cpp` | `http_request_cb()` | OnRpcHttpEnqueue |
| `httpserver.cpp` | worker lambda | OnRpcHttpDispatch |
| `httprpc.cpp` | `HTTPReq_JSONRPC()` | OnRpcCallLifecycle |
| `httpserver.cpp` | queue full check | OnRpcBackpressure |

### Phase 5 Latency Requirements

| Hook | Max Latency | Rationale |
|------|-------------|-----------|
| `OnRpcHttpEnqueue` | ≤50μs | Called on every HTTP request |
| `OnRpcHttpDispatch` | ≤50μs | Called when dispatching to worker |
| `OnRpcCallLifecycle` | ≤100μs | Called after RPC completion |
| `OnRpcBackpressure` | ≤50μs | Called on QoS decisions |
| `OnP2PRpcInterferenceSnapshot` | ≤500μs | Called periodically (1/sec) |

### Files Added/Modified

**New files:**
- `src/node/stdio_bus_rpc_metrics.h` - RPC metrics collector
- `src/node/stdio_bus_rpc_metrics.cpp` - Implementation

**Modified files:**
- `src/node/stdio_bus_hooks.h` - Added Phase 5 event types and methods
- `src/node/stdio_bus_sdk_hooks.h` - Added Phase 5 methods to SDK
- `src/node/stdio_bus_sdk_hooks.cpp` - Added Phase 5 serialization
- `src/httpserver.h` - Added SetHttpServerStdioBusHooks()
- `src/httpserver.cpp` - Added hooks in http_request_cb()
- `src/httprpc.h` - Added SetHttpRpcStdioBusHooks()
- `src/httprpc.cpp` - Added hooks in HTTPReq_JSONRPC()
- `src/test/stdio_bus_hooks_tests.cpp` - Added Phase 5 tests

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

## Known Limitations (Phase 5)

1. **Queue timing approximation** - `queue_entered_us` and `dispatch_us` in RpcCallLifecycleEvent
   are approximations since exact timing requires deeper integration with ThreadPool.

2. **Worker ID not tracked** - `worker_id` in RpcHttpDispatchEvent is always 0; actual worker
   identification requires ThreadPool modifications.

3. **P2P load score placeholder** - `p2p_load_score` in backpressure events is currently 0.0;
   requires integration with P2P metrics from net_processing.

4. **Interference snapshots not automated** - P2PRpcInterferenceSnapshotEvent requires manual
   triggering or timer integration; not automatically fired in Phase 5.

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
