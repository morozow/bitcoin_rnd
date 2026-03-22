# stdiobus-cpp

C++ SDK for stdio_bus - the AI agent transport layer.

## Documentation

📚 **[Full Documentation](docs/README.md)** - Comprehensive guides and API reference

| Document | Description |
|----------|-------------|
| [Overview](docs/00-overview/) | What is stdio_bus, invariants, guarantees |
| [Getting Started](docs/01-getting-started/) | Quickstarts for Embedded, TCP, Unix modes |
| [Core Concepts](docs/02-core-concepts/) | Lifecycle, callbacks, threading |
| [API Reference](docs/03-cpp-sdk/01-api-cheatsheet.md) | Complete API cheatsheet |
| [Operating Modes](docs/05-operating-modes/01-mode-capability-matrix.md) | Mode comparison matrix |
| [Integration Patterns](docs/06-integration-patterns/) | Retry, timeout, circuit breaker |
| [Complete Capabilities](docs/07-use-cases/01-complete-capabilities.md) | Full R&D reference |

## Features

- **Two-layer design**:
  - Thin C++ wrapper (1:1 over C API) - `stdiobus::ffi`
  - Idiomatic C++ facade with RAII - `stdiobus::Bus`
- **Modern C++17** - std::string_view, std::chrono, std::function
- **RAII** - Automatic resource cleanup
- **No exceptions by default** - Status-style error handling
- **Optional exceptions** - Define `STDIOBUS_CPP_EXCEPTIONS=1`

## Requirements

- C++17 compiler (GCC 7+, Clang 5+, MSVC 2017+)
- libstdio_bus.a (build from main repo with `make lib`)
- CMake 3.14+

## Installation

### From Source (CMake)

```bash
# Build libstdio_bus first
cd /path/to/stdio_bus
make lib

# Build C++ SDK
cd sdk/cpp
mkdir build && cd build
cmake -DSTDIO_BUS_LIB_DIR=/path/to/stdio_bus/build ..
make
```

### From Source (Direct compilation, no CMake)

```bash
# Build libstdio_bus first
make lib

# Compile directly with g++ (GCC 7+ or Clang 5+)
g++ -std=c++17 -Wall \
  -I sdk/cpp/include \
  -I include \
  sdk/cpp/src/bus.cpp \
  your_app.cpp \
  build/libstdio_bus.a \
  -o your_app
```

### CMake Integration

```cmake
# In your CMakeLists.txt
add_subdirectory(path/to/sdk/cpp)
target_link_libraries(your_app PRIVATE stdiobus)
```

## Quick Start

```cpp
#include <stdiobus.hpp>
#include <iostream>

int main() {
    // Create bus from config file
    stdiobus::Bus bus("config.json");
    
    // Set message callback
    bus.on_message([](std::string_view msg) {
        std::cout << "Received: " << msg << std::endl;
    });
    
    // Start workers
    if (auto err = bus.start(); err) {
        std::cerr << "Failed to start: " << err.message() << std::endl;
        return 1;
    }
    
    // Send a request
    bus.send(R"({"jsonrpc":"2.0","method":"echo","params":{"msg":"hello"},"id":1})");
    
    // Event loop
    while (bus.is_running()) {
        bus.step(std::chrono::milliseconds(100));
    }
    
    return 0;
}
```

## Running as Persistent Daemon

To run stdio_bus as a long-running service (until Ctrl+C):

```cpp
#include <stdiobus.hpp>
#include <iostream>
#include <csignal>
#include <atomic>

static std::atomic<bool> g_running{true};

void signal_handler(int) { g_running = false; }

int main(int argc, char* argv[]) {
    const char* config = argc > 1 ? argv[1] : "config.json";
    
    stdiobus::Bus bus(config);
    if (!bus) return 1;
    
    bus.on_message([](std::string_view msg) {
        std::cout << "[MSG] " << msg << std::endl;
    });
    
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    if (auto err = bus.start(); err) {
        std::cerr << "Failed: " << err.message() << std::endl;
        return 1;
    }
    
    std::cout << "stdio_bus running. Ctrl+C to stop." << std::endl;
    
    while (g_running && bus.is_running()) {
        bus.step(std::chrono::milliseconds(100));
    }
    
    bus.stop(std::chrono::seconds(5));
    return 0;
}
```

Build and run:

```bash
# Build
make lib
g++ -std=c++17 -I sdk/cpp/include -I include \
    sdk/cpp/src/bus.cpp runner.cpp build/libstdio_bus.a -o runner

# Run
./runner --config your-config.json
```

See `sdk/cpp/examples/runner.cpp` for a complete example.

## Builder Pattern

```cpp
#include <stdiobus.hpp>

auto bus = stdiobus::BusBuilder()
    .config_path("config.json")
    .log_level(2)  // WARN
    .on_message([](auto msg) { 
        std::cout << msg << std::endl; 
    })
    .on_error([](auto code, auto msg) {
        std::cerr << "Error " << static_cast<int>(code) << ": " << msg << std::endl;
    })
    .build();
```

## Error Handling

### Status-style (default)

```cpp
if (auto err = bus.start(); err) {
    std::cerr << "Error: " << err.message() << std::endl;
    if (err.is_retryable()) {
        // Retry logic
    }
    return 1;
}
```

### Exception mode

```cpp
// Compile with -DSTDIOBUS_CPP_EXCEPTIONS=1

try {
    stdiobus::throw_if_error(bus.start());
    // ...
} catch (const stdiobus::Exception& e) {
    std::cerr << "Exception: " << e.what() << std::endl;
    std::cerr << "Code: " << static_cast<int>(e.code()) << std::endl;
}
```

## API Reference

### Bus Class

```cpp
// Construction
Bus(std::string_view config_path);
Bus(Options options);

// Lifecycle
Error start();
int step(Duration timeout = Duration::zero());
Error stop(std::chrono::seconds timeout = 5s);

// Messaging
Error send(std::string_view message);

// State
State state() const;
bool is_running() const;
bool is_created() const;
bool is_stopped() const;
Stats stats() const;
int worker_count() const;
int session_count() const;
int pending_count() const;
int client_count() const;
int poll_fd() const;

// Callbacks
void on_message(MessageCallback cb);
void on_error(ErrorCallback cb);
void on_log(LogCallback cb);
void on_worker(WorkerCallback cb);
void on_client_connect(ClientConnectCallback cb);
void on_client_disconnect(ClientDisconnectCallback cb);

// Advanced
stdio_bus_t* raw_handle() const;
```

### Error Codes

| Code | Value | Description |
|------|-------|-------------|
| Ok | 0 | Success |
| Error | -1 | Generic error |
| Again | -2 | Try again (retryable) |
| Eof | -3 | End of file |
| Full | -4 | Buffer full (retryable) |
| NotFound | -5 | Not found |
| Invalid | -6 | Invalid argument |
| Config | -10 | Configuration error |
| Worker | -11 | Worker error |
| Routing | -12 | Routing error |
| Buffer | -13 | Buffer error |
| State | -15 | Invalid state |
| Timeout | -20 | Timeout (retryable) |
| PolicyDenied | -21 | Policy denied |

### States

| State | Description |
|-------|-------------|
| Created | Created but not started |
| Starting | Workers being spawned |
| Running | Running and accepting messages |
| Stopping | Graceful shutdown in progress |
| Stopped | Fully stopped |

## Thin Wrapper (FFI)

For direct C API access:

```cpp
#include <stdiobus/ffi.hpp>

// Create using C API directly
stdio_bus_options_t opts{};
opts.config_path = "config.json";
opts.on_message = my_callback;

auto handle = stdiobus::ffi::create(&opts);
handle.start();
handle.step(100);
handle.stop(5);
stdiobus::ffi::destroy(handle);
```

## Thread Safety

- `Bus` instances are NOT thread-safe
- Use one `Bus` per thread, or synchronize externally
- Callbacks are invoked from the thread calling `step()`

## Integration with Event Loops

```cpp
// Get poll fd for external event loop (epoll/kqueue/libuv)
int fd = bus.poll_fd();
if (fd >= 0) {
    // Add to your event loop
    // When fd is readable, call bus.step(0)
}
```

## Platform Support

| Platform | Status |
|----------|--------|
| Linux x64 | ✅ |
| Linux arm64 | ✅ |
| macOS x64 | ✅ |
| macOS arm64 | ✅ |
| Windows | ❌ (use Docker backend) |

## License

Apache-2.0
