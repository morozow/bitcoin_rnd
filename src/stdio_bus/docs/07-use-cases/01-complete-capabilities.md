# Complete Capabilities Reference

This document lists ALL capabilities of stdio_bus + C++ SDK for R&D reference.

## Transport Capabilities

### Operating Modes

| Mode | API | Description |
|------|-----|-------------|
| Embedded | Default | Direct host-worker communication via pipes |
| TCP | `listen_tcp(host, port)` | Network server for remote clients |
| Unix Socket | `listen_unix(path)` | High-performance local IPC |

### Message Routing

| Capability | Description |
|------------|-------------|
| Session affinity | Same sessionId → same worker |
| Round-robin assignment | New sessions distributed evenly |
| Request correlation | Match responses by request id |
| NDJSON framing | Newline-delimited JSON messages |

### Backpressure Control

| Capability | Description |
|------------|-------------|
| Input buffer limits | Configurable max input buffer |
| Output queue limits | Configurable max output queue |
| Flow control signals | EAGAIN/Full error codes |
| Drain on shutdown | Graceful message delivery |

## Process Management

### Worker Lifecycle

| Capability | Description |
|------------|-------------|
| Spawn workers | Fork/exec from config |
| Monitor workers | Detect crashes via SIGCHLD |
| Restart workers | Automatic restart on failure |
| Graceful stop | SIGTERM → wait → SIGKILL |

### Worker Pools

| Capability | Description |
|------------|-------------|
| Multiple pools | Different worker types |
| Pool sizing | Configurable worker count |
| Restart policies | always, on-failure, never |
| Command configuration | Custom worker commands |

## C++ SDK Features

### Bus Class

| Feature | Method | Description |
|---------|--------|-------------|
| RAII lifecycle | Constructor/Destructor | Automatic cleanup |
| Start workers | `start()` | Begin accepting messages |
| Event processing | `step(timeout)` | Non-blocking I/O pump |
| Send messages | `send(msg)` | Queue message for routing |
| Graceful stop | `stop(timeout)` | Drain and shutdown |
| State queries | `state()`, `is_running()` | Lifecycle state |
| Statistics | `stats()` | Message/byte counters |
| Worker count | `worker_count()` | Active workers |
| Session count | `session_count()` | Active sessions |
| Pending count | `pending_count()` | Awaiting response |
| Client count | `client_count()` | Connected clients |
| Poll FD | `poll_fd()` | External event loop integration |

### BusBuilder

| Feature | Method | Description |
|---------|--------|-------------|
| Config file | `config_path(path)` | Load JSON config |
| Inline config | `config_json(json)` | Inline JSON string |
| Log level | `log_level(level)` | 0=DEBUG to 3=ERROR |
| TCP mode | `listen_tcp(host, port)` | Enable TCP listener |
| Unix mode | `listen_unix(path)` | Enable Unix socket |
| Message callback | `on_message(cb)` | Response handler |
| Error callback | `on_error(cb)` | Error handler |
| Log callback | `on_log(cb)` | Log handler |
| Worker callback | `on_worker(cb)` | Worker events |
| Build | `build()` | Create Bus instance |

### AsyncBus

| Feature | Method | Description |
|---------|--------|-------------|
| Async requests | `request_async(msg, timeout)` | Returns std::future |
| Notifications | `notify(msg)` | Fire-and-forget |
| I/O pump | `pump(timeout)` | Process pending I/O |
| Timeout check | `check_timeouts()` | Resolve expired requests |
| Bus access | `bus()` | Underlying Bus reference |

### Error Handling

| Feature | Description |
|---------|-------------|
| Status mode | Default, check Error return values |
| Exception mode | Compile with STDIOBUS_CPP_EXCEPTIONS=1 |
| Error codes | Ok, Error, Again, Eof, Full, NotFound, Invalid, Config, Worker, Routing, Buffer, State, Timeout, PolicyDenied |
| Retryable check | `err.is_retryable()` |
| Error message | `err.message()` |

### FFI Layer

| Feature | Description |
|---------|-------------|
| Direct C API | `stdiobus::ffi::Handle` |
| Type conversion | `to_state()`, `to_stats()` |
| Raw handle access | `bus.raw_handle()` |

## Callbacks

| Callback | Signature | When |
|----------|-----------|------|
| on_message | `void(string_view)` | Response from worker |
| on_error | `void(ErrorCode, string_view)` | Error occurred |
| on_log | `void(int, string_view)` | Log message |
| on_worker | `void(int, string_view)` | Worker event |
| on_client_connect | `void(int, string_view)` | Client connected |
| on_client_disconnect | `void(int, string_view)` | Client disconnected |

## Configuration (JSON)

```json
{
  "pools": [
    {
      "name": "default",
      "command": ["node", "worker.js"],
      "count": 4,
      "restart_policy": "always"
    }
  ],
  "limits": {
    "max_input_buffer": 1048576,
    "max_output_queue": 1000,
    "request_timeout_ms": 30000
  }
}
```

## Integration Patterns Supported

| Pattern | Description |
|---------|-------------|
| Request/Reply | Send request, receive response via callback |
| Fire-and-forget | Send notification, no response expected |
| Session management | Stateful conversations via sessionId |
| Retry with backoff | Retry retryable errors with exponential backoff |
| Circuit breaker | Fail fast when backend unhealthy |
| Timeout handling | Request-level timeouts |
| Graceful shutdown | Drain messages before exit |
| External event loop | Integrate via poll_fd() |

## Platform Support

| Platform | Status |
|----------|--------|
| Linux x64 | ✅ Full support (epoll) |
| Linux arm64 | ✅ Full support (epoll) |
| macOS x64 | ✅ Full support (kqueue) |
| macOS arm64 | ✅ Full support (kqueue) |
| Windows | ❌ Not supported |

## Build Requirements

| Requirement | Version |
|-------------|---------|
| C++ Standard | C++17 |
| GCC | 7+ |
| Clang | 5+ |
| CMake | 3.14+ (optional) |

## What You CAN Do

1. ✅ Run AI agent workers (ACP/MCP)
2. ✅ Route messages by session
3. ✅ Manage worker lifecycle
4. ✅ Handle backpressure
5. ✅ Expose TCP/Unix endpoints
6. ✅ Integrate with external event loops
7. ✅ Monitor statistics
8. ✅ Graceful shutdown
9. ✅ Async request/response
10. ✅ Custom error handling

## What You CANNOT Do

1. ❌ Persist messages across restarts
2. ❌ Multi-threaded access to Bus
3. ❌ Windows support
4. ❌ Built-in TLS (use proxy)
5. ❌ Message transformation (protocol agnostic)
6. ❌ Distributed multi-host routing (single bus instance)

## R&D Checklist

When integrating into a new project:

- [ ] Choose operating mode (Embedded/TCP/Unix)
- [ ] Create worker pool configuration
- [ ] Implement message callback
- [ ] Implement error callback
- [ ] Add signal handlers for graceful shutdown
- [ ] Configure timeouts
- [ ] Implement retry policy for retryable errors
- [ ] Add circuit breaker for resilience
- [ ] Set up monitoring/logging
- [ ] Test backpressure behavior
- [ ] Test worker restart scenarios
- [ ] Test graceful shutdown
