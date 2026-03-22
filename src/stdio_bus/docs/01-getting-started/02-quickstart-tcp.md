# Quickstart: TCP Mode

TCP mode exposes stdio_bus as a network server, allowing remote clients to connect.

## When to Use

- Remote worker deployments
- Multi-host architectures
- External client connections
- Load balancer integration

## Minimal Example

```cpp
#include <stdiobus.hpp>
#include <iostream>
#include <csignal>
#include <atomic>

static std::atomic<bool> g_running{true};
void signal_handler(int) { g_running = false; }

int main() {
    auto bus = stdiobus::BusBuilder()
        .config_path("config.json")
        .listen_tcp("0.0.0.0", 9800)  // Listen on all interfaces, port 9800
        .on_message([](std::string_view msg) {
            std::cout << "[MSG] " << msg << std::endl;
        })
        .on_client_connect([](int id, std::string_view peer) {
            std::cout << "[CONNECT] Client " << id << " from " << peer << std::endl;
        })
        .on_client_disconnect([](int id, std::string_view reason) {
            std::cout << "[DISCONNECT] Client " << id << ": " << reason << std::endl;
        })
        .build();
    
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    if (auto err = bus.start(); err) {
        std::cerr << "Failed: " << err.message() << std::endl;
        return 1;
    }
    
    std::cout << "TCP server listening on port 9800" << std::endl;
    std::cout << "Workers: " << bus.worker_count() << std::endl;
    
    while (g_running && bus.is_running()) {
        bus.step(std::chrono::milliseconds(100));
    }
    
    bus.stop(std::chrono::seconds(5));
    
    auto stats = bus.stats();
    std::cout << "Stats: clients=" << stats.client_connects 
              << " messages=" << stats.messages_in << std::endl;
    
    return 0;
}
```

## Build & Run

```bash
make lib

/opt/local/bin/g++-mp-15 -std=c++17 \
    -I sdk/cpp/include -I include \
    sdk/cpp/src/bus.cpp tcp_server.cpp \
    build/libstdio_bus.a -o tcp_server

./tcp_server
```

## Test with netcat

```bash
# Connect to server
nc localhost 9800

# Send JSON-RPC request (type and press Enter)
{"jsonrpc":"2.0","method":"ping","id":1}

# Response will appear
{"jsonrpc":"2.0","result":"pong","id":1}
```

## Test with acp-chat

```bash
# Set environment variable
export ACP_BUS_ADDRESS=127.0.0.1:9800

# Use acp-chat CLI
npx acp-chat new "Hello, agent!"
```

## Binding Options

```cpp
// All interfaces (external access)
.listen_tcp("0.0.0.0", 9800)

// Localhost only (secure)
.listen_tcp("127.0.0.1", 9800)

// Specific interface
.listen_tcp("192.168.1.100", 9800)
```

## Security Considerations

| Risk | Mitigation |
|------|------------|
| Unauthorized access | Bind to localhost or use firewall |
| DoS attacks | Configure connection limits |
| Data interception | Use TLS termination proxy |
| Protocol abuse | Validate JSON-RPC format |

## Production Setup

```cpp
auto bus = stdiobus::BusBuilder()
    .config_path("config.json")
    .listen_tcp("127.0.0.1", 9800)  // Localhost only
    .log_level(2)  // WARN level
    .on_error([](auto code, auto msg) {
        syslog(LOG_ERR, "stdio_bus error %d: %s", 
               static_cast<int>(code), std::string(msg).c_str());
    })
    .build();
```

## Behind Reverse Proxy (nginx)

```nginx
upstream stdio_bus {
    server 127.0.0.1:9800;
}

server {
    listen 443 ssl;
    
    location /bus {
        proxy_pass http://stdio_bus;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

## Monitoring Clients

```cpp
// Periodic stats logging
while (g_running && bus.is_running()) {
    bus.step(std::chrono::milliseconds(100));
    
    static auto last_log = std::chrono::steady_clock::now();
    auto now = std::chrono::steady_clock::now();
    
    if (now - last_log > std::chrono::seconds(60)) {
        std::cout << "Clients: " << bus.client_count() 
                  << " Workers: " << bus.worker_count()
                  << " Sessions: " << bus.session_count() << std::endl;
        last_log = now;
    }
}
```
