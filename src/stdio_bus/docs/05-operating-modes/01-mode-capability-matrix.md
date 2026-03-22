# Mode Capability Matrix

## Overview

stdio_bus supports three operating modes:

| Mode | Description | Use Case |
|------|-------------|----------|
| **Embedded** | No external listener, host sends/receives directly | Single-process, testing |
| **TCP** | Network socket listener | Remote clients, multi-host |
| **Unix Socket** | Local filesystem socket | High-perf local IPC |

## Capability Comparison

| Capability | Embedded | TCP | Unix Socket |
|------------|----------|-----|-------------|
| Local process communication | ✅ | ✅ | ✅ |
| Remote network clients | ❌ | ✅ | ❌ |
| Lowest latency | ⭐⭐⭐ | ⭐ | ⭐⭐ |
| Highest throughput | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Easy sandboxing | ⭐⭐ | ⭐ | ⭐⭐⭐ |
| Multi-host deployment | ❌ | ✅ | ❌ |
| Firewall/NAT traversal | N/A | Required | N/A |
| FS permission security | N/A | ❌ | ✅ |
| Operational complexity | Low | High | Medium |

## Configuration

### Embedded Mode (Default)

```cpp
auto bus = stdiobus::BusBuilder()
    .config_path("config.json")
    // No listen_* call = embedded mode
    .build();
```

### TCP Mode

```cpp
auto bus = stdiobus::BusBuilder()
    .config_path("config.json")
    .listen_tcp("0.0.0.0", 9800)  // All interfaces
    .build();

// Or localhost only
.listen_tcp("127.0.0.1", 9800)
```

### Unix Socket Mode

```cpp
auto bus = stdiobus::BusBuilder()
    .config_path("config.json")
    .listen_unix("/tmp/stdio_bus.sock")
    .build();
```

## Performance Characteristics

| Metric | Embedded | TCP | Unix Socket |
|--------|----------|-----|-------------|
| Message latency | ~10μs | ~100μs | ~50μs |
| Max throughput | ~1M msg/s | ~100K msg/s | ~500K msg/s |
| Memory overhead | Minimal | Per-connection buffers | Per-connection buffers |
| CPU overhead | Minimal | Syscall + network stack | Syscall only |

*Note: Numbers are approximate and depend on hardware/OS.*

## Security Considerations

### Embedded Mode

| Risk | Mitigation |
|------|------------|
| Process isolation only | Use OS-level sandboxing |
| Shared memory space | Careful with worker trust |

### TCP Mode

| Risk | Mitigation |
|------|------------|
| Unauthorized access | Bind to localhost, use firewall |
| Data interception | TLS termination proxy |
| DoS attacks | Connection limits, rate limiting |
| Protocol abuse | Input validation |

### Unix Socket Mode

| Risk | Mitigation |
|------|------------|
| Unauthorized access | Filesystem permissions (chmod) |
| Socket hijacking | Secure directory permissions |
| Stale socket | Cleanup on startup/shutdown |

## Reliability Comparison

| Dimension | Embedded | TCP | Unix Socket |
|-----------|----------|-----|-------------|
| Connection loss | Process exit | Network instability | Daemon lifecycle |
| Retry strategy | Process restart | Reconnect + backoff | Reconnect + backoff |
| Backpressure | Pipe buffers | Per-socket queues | Per-socket queues |

## Selection Guide

### Choose Embedded When:

- Single process or tightly-coupled host-worker
- Maximum performance required
- Testing and development
- No external client access needed

### Choose TCP When:

- Remote workers on different hosts
- External client connections required
- Load balancer integration
- Kubernetes/container orchestration

### Choose Unix Socket When:

- Single-host production deployment
- Need filesystem-based access control
- Want lowest latency for local IPC
- Container environments with shared volumes

## Migration Between Modes

### Embedded → TCP

```cpp
// Before
auto bus = stdiobus::BusBuilder()
    .config_path("config.json")
    .build();

// After
auto bus = stdiobus::BusBuilder()
    .config_path("config.json")
    .listen_tcp("127.0.0.1", 9800)
    .on_client_connect([](int id, auto peer) {
        std::cout << "Client " << id << " connected" << std::endl;
    })
    .build();
```

### TCP → Unix Socket

```cpp
// Before
.listen_tcp("127.0.0.1", 9800)

// After
.listen_unix("/var/run/stdio_bus/bus.sock")
```

## Client Connection Callbacks

Only available in TCP and Unix Socket modes:

```cpp
bus.on_client_connect([](int client_id, std::string_view peer_info) {
    // TCP: peer_info = "192.168.1.100:54321"
    // Unix: peer_info = "unix"
    std::cout << "Client " << client_id << " from " << peer_info << std::endl;
});

bus.on_client_disconnect([](int client_id, std::string_view reason) {
    // reason: "closed", "error", "timeout"
    std::cout << "Client " << client_id << " disconnected: " << reason << std::endl;
});
```

## Monitoring by Mode

```cpp
while (bus.is_running()) {
    bus.step(100ms);
    
    // Mode-specific monitoring
    if (/* TCP or Unix mode */) {
        std::cout << "Connected clients: " << bus.client_count() << std::endl;
    }
    
    // Common monitoring
    std::cout << "Workers: " << bus.worker_count() << std::endl;
    std::cout << "Sessions: " << bus.session_count() << std::endl;
    
    auto stats = bus.stats();
    std::cout << "Messages: " << stats.messages_in << "/" << stats.messages_out << std::endl;
}
```
