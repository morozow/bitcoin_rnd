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
