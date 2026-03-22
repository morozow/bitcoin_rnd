# Quickstart: Embedded Mode

Embedded mode runs stdio_bus within your application process, communicating with workers via stdin/stdout pipes.

## When to Use

- Single-host deployments
- Tightly-coupled host-worker architecture
- Minimal operational complexity
- Testing and development

## Minimal Example

```cpp
#include <stdiobus.hpp>
#include <iostream>

int main() {
    // Create bus from config file
    stdiobus::Bus bus("config.json");
    
    // Set message callback
    bus.on_message([](std::string_view msg) {
        std::cout << "Response: " << msg << std::endl;
    });
    
    // Start workers
    if (auto err = bus.start(); err) {
        std::cerr << "Failed to start: " << err.message() << std::endl;
        return 1;
    }
    
    std::cout << "Bus running with " << bus.worker_count() << " workers" << std::endl;
    
    // Send a request
    bus.send(R"({"jsonrpc":"2.0","method":"echo","params":{"msg":"hello"},"id":1})");
    
    // Event loop - process until stopped
    while (bus.is_running()) {
        bus.step(std::chrono::milliseconds(100));
    }
    
    return 0;
}
```

## Config File (config.json)

```json
{
  "pools": [
    {
      "name": "default",
      "command": ["node", "worker.js"],
      "count": 2,
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

## Build & Run

```bash
# Build libstdio_bus
make lib

# Compile your application
/opt/local/bin/g++-mp-15 -std=c++17 \
    -I sdk/cpp/include -I include \
    sdk/cpp/src/bus.cpp main.cpp \
    build/libstdio_bus.a -o myapp

# Run
./myapp
```

## With BusBuilder

```cpp
#include <stdiobus.hpp>

int main() {
    auto bus = stdiobus::BusBuilder()
        .config_path("config.json")
        .log_level(1)  // INFO
        .on_message([](std::string_view msg) {
            std::cout << msg << std::endl;
        })
        .on_error([](stdiobus::ErrorCode code, std::string_view msg) {
            std::cerr << "Error " << static_cast<int>(code) << ": " << msg << std::endl;
        })
        .on_worker([](int id, std::string_view event) {
            std::cout << "Worker " << id << ": " << event << std::endl;
        })
        .build();
    
    if (!bus) {
        std::cerr << "Failed to create bus" << std::endl;
        return 1;
    }
    
    bus.start();
    
    // Your application logic here
    
    bus.stop(std::chrono::seconds(5));
    return 0;
}
```

## Persistent Daemon with Signal Handling

```cpp
#include <stdiobus.hpp>
#include <csignal>
#include <atomic>

static std::atomic<bool> g_running{true};

void signal_handler(int) { g_running = false; }

int main(int argc, char* argv[]) {
    const char* config = argc > 1 ? argv[1] : "config.json";
    
    stdiobus::Bus bus(config);
    
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
    std::cout << "Stopped." << std::endl;
    return 0;
}
```

## Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| Forgetting to call `step()` | Messages won't be processed without event loop |
| Blocking in callbacks | Keep callbacks fast, offload work to queues |
| Missing error handling | Always check `start()` and `send()` return values |
| Not stopping on exit | Use signal handlers for graceful shutdown |
