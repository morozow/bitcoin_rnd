# Quickstart: Unix Socket Mode

Unix socket mode provides high-performance local IPC with filesystem-based access control.

## When to Use

- Single-host production deployments
- Lowest latency local communication
- Filesystem permission-based security
- Container/sandbox environments

## Minimal Example

```cpp
#include <stdiobus.hpp>
#include <iostream>
#include <csignal>
#include <atomic>

static std::atomic<bool> g_running{true};
void signal_handler(int) { g_running = false; }

int main() {
    const char* socket_path = "/tmp/stdio_bus.sock";
    
    auto bus = stdiobus::BusBuilder()
        .config_path("config.json")
        .listen_unix(socket_path)
        .on_message([](std::string_view msg) {
            std::cout << "[MSG] " << msg << std::endl;
        })
        .on_client_connect([](int id, std::string_view peer) {
            std::cout << "[CONNECT] Client " << id << std::endl;
        })
        .build();
    
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    if (auto err = bus.start(); err) {
        std::cerr << "Failed: " << err.message() << std::endl;
        return 1;
    }
    
    std::cout << "Unix socket server at " << socket_path << std::endl;
    
    while (g_running && bus.is_running()) {
        bus.step(std::chrono::milliseconds(100));
    }
    
    bus.stop(std::chrono::seconds(5));
    
    // Clean up socket file
    unlink(socket_path);
    
    return 0;
}
```

## Build & Run

```bash
make lib

/opt/local/bin/g++-mp-15 -std=c++17 \
    -I sdk/cpp/include -I include \
    sdk/cpp/src/bus.cpp unix_server.cpp \
    build/libstdio_bus.a -o unix_server

./unix_server
```

## Test with socat

```bash
# Connect to Unix socket
socat - UNIX-CONNECT:/tmp/stdio_bus.sock

# Send JSON-RPC request
{"jsonrpc":"2.0","method":"ping","id":1}
```

## Test with netcat (macOS)

```bash
nc -U /tmp/stdio_bus.sock
```

## Socket Path Conventions

| Path | Use Case |
|------|----------|
| `/tmp/stdio_bus.sock` | Development/testing |
| `/var/run/stdio_bus/bus.sock` | System daemon |
| `/run/user/1000/stdio_bus.sock` | User-level service |
| `./bus.sock` | Application-local |

## Filesystem Permissions

```cpp
#include <sys/stat.h>

int main() {
    const char* socket_path = "/var/run/stdio_bus/bus.sock";
    
    // Create directory with restricted permissions
    mkdir("/var/run/stdio_bus", 0750);
    
    auto bus = stdiobus::BusBuilder()
        .config_path("config.json")
        .listen_unix(socket_path)
        .build();
    
    bus.start();
    
    // Set socket permissions (owner + group only)
    chmod(socket_path, 0660);
    
    // ... event loop ...
}
```

## Cleanup on Exit

```cpp
#include <cstdlib>

const char* g_socket_path = nullptr;

void cleanup() {
    if (g_socket_path) {
        unlink(g_socket_path);
    }
}

int main() {
    g_socket_path = "/tmp/stdio_bus.sock";
    std::atexit(cleanup);
    
    // ... rest of code ...
}
```

## Systemd Integration

```ini
# /etc/systemd/system/stdio-bus.service
[Unit]
Description=stdio_bus Agent Transport
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/stdio_bus_server
ExecStopPost=/bin/rm -f /var/run/stdio_bus/bus.sock
RuntimeDirectory=stdio_bus
User=stdio_bus
Group=stdio_bus

[Install]
WantedBy=multi-user.target
```

## Performance Comparison

| Mode | Latency | Throughput | Security |
|------|---------|------------|----------|
| Embedded | Lowest | Highest | Process isolation |
| Unix Socket | Very Low | High | FS permissions |
| TCP | Low | Medium | Network policies |

## When to Prefer Unix Socket over TCP

- Same-host communication only
- Need filesystem-based access control
- Want to avoid network stack overhead
- Running in containers with shared volumes
