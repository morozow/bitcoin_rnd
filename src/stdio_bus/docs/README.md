# stdio_bus C++ SDK Documentation

Comprehensive documentation for the C++ SDK - your gateway to building AI agent transport systems.

## Quick Navigation

| Section | Purpose |
|---------|---------|
| [00-overview](00-overview/) | What is stdio_bus, invariants, guarantees |
| [01-getting-started](01-getting-started/) | Quickstarts for Embedded, TCP, Unix modes |
| [02-core-concepts](02-core-concepts/) | Lifecycle, callbacks, step model, threading, errors |
| [03-cpp-sdk](03-cpp-sdk/) | API cheatsheet for Bus, AsyncBus, BusBuilder |
| [05-operating-modes](05-operating-modes/) | Mode capability matrix |
| [06-integration-patterns](06-integration-patterns/) | Retry, timeout, circuit breaker |
| [07-use-cases](07-use-cases/) | Complete capabilities reference for R&D |

## Document Index

### Overview
- [What is stdio_bus](00-overview/01-what-is-stdio-bus.md)
- [Invariants and Guarantees](00-overview/02-invariants-and-guarantees.md)

### Getting Started
- [Quickstart: Embedded Mode](01-getting-started/01-quickstart-embedded.md)
- [Quickstart: TCP Mode](01-getting-started/02-quickstart-tcp.md)
- [Quickstart: Unix Socket Mode](01-getting-started/03-quickstart-unix-socket.md)

### Core Concepts
- [Lifecycle State Machine](02-core-concepts/01-lifecycle-state-machine.md)
- [Callbacks Contract](02-core-concepts/02-callbacks-contract.md)
- [Event Loop Step Model](02-core-concepts/03-event-loop-step-model.md)
- [Error Model: Status vs Exception](02-core-concepts/04-error-model.md)
- [Thread Safety Matrix](02-core-concepts/05-thread-safety-matrix.md)
- [Failure Taxonomy](02-core-concepts/06-failure-taxonomy.md)

### C++ SDK Reference
- [API Cheatsheet](03-cpp-sdk/01-api-cheatsheet.md)

### Operating Modes
- [Mode Capability Matrix](05-operating-modes/01-mode-capability-matrix.md)

### Integration Patterns
- [Retry, Timeout, Circuit Breaker](06-integration-patterns/01-retry-timeout-circuit-breaker.md)

### Use Cases
- [Complete Capabilities Reference](07-use-cases/01-complete-capabilities.md)

## 5-Minute Start

```cpp
#include <stdiobus.hpp>

int main() {
    // Create bus with TCP listener on port 9800
    auto bus = stdiobus::BusBuilder()
        .config_path("config.json")
        .listen_tcp("0.0.0.0", 9800)
        .on_message([](std::string_view msg) {
            std::cout << "Response: " << msg << std::endl;
        })
        .build();
    
    bus.start();
    
    // Send JSON-RPC request
    bus.send(R"({"jsonrpc":"2.0","method":"ping","id":1})");
    
    // Event loop
    while (bus.is_running()) {
        bus.step(std::chrono::milliseconds(100));
    }
    
    return 0;
}
```

## Build

```bash
# From repository root
make lib                                    # Build libstdio_bus.a
/opt/local/bin/g++-mp-15 -std=c++17 \
    -I sdk/cpp/include -I include \
    sdk/cpp/src/bus.cpp your_app.cpp \
    build/libstdio_bus.a -o your_app
```

## SDK Components

| Component | Header | Purpose |
|-----------|--------|---------|
| Bus | `<stdiobus/bus.hpp>` | RAII wrapper, sync API |
| AsyncBus | `<stdiobus/async.hpp>` | Promise-based async |
| BusBuilder | `<stdiobus/bus.hpp>` | Fluent configuration |
| FFI | `<stdiobus/ffi.hpp>` | Direct C API access |
| Error | `<stdiobus/error.hpp>` | Error codes and handling |
| Types | `<stdiobus/types.hpp>` | Core type definitions |

## R&D Checklist

When integrating into a new project:

- [ ] Choose operating mode (Embedded/TCP/Unix)
- [ ] Configure worker pools in JSON config
- [ ] Set up message callback for responses
- [ ] Implement error handling (status or exception mode)
- [ ] Add graceful shutdown with signal handlers
- [ ] Configure timeouts and retry policy
- [ ] Test backpressure behavior under load
