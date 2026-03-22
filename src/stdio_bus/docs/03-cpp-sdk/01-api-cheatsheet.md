# API Cheatsheet

Quick reference for all C++ SDK classes and methods.

## Bus Class

RAII wrapper for stdio_bus lifecycle and messaging.

### Construction

```cpp
// From config file
stdiobus::Bus bus("config.json");

// From Options struct
stdiobus::Options opts;
opts.config_path = "config.json";
opts.log_level = 2;
stdiobus::Bus bus(std::move(opts));
```

### Lifecycle Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `start()` | `Error` | Start workers, begin accepting messages |
| `step(timeout)` | `int` | Process I/O, returns events processed or error |
| `stop(timeout)` | `Error` | Graceful shutdown with drain |

```cpp
bus.start();                              // Start
bus.step(std::chrono::milliseconds(100)); // Process I/O
bus.stop(std::chrono::seconds(5));        // Stop with 5s drain
```

### Messaging

| Method | Returns | Description |
|--------|---------|-------------|
| `send(message)` | `Error` | Send JSON message to workers |

```cpp
auto err = bus.send(R"({"jsonrpc":"2.0","method":"ping","id":1})");
if (err) {
    if (err.is_retryable()) { /* retry later */ }
    else { /* handle error */ }
}
```

### State Queries

| Method | Returns | Description |
|--------|---------|-------------|
| `state()` | `State` | Current lifecycle state |
| `is_running()` | `bool` | True if Running |
| `is_created()` | `bool` | True if Created |
| `is_stopped()` | `bool` | True if Stopped |
| `stats()` | `Stats` | Message/byte counters |
| `worker_count()` | `int` | Active workers |
| `session_count()` | `int` | Active sessions |
| `pending_count()` | `int` | Pending requests |
| `client_count()` | `int` | Connected clients (TCP/Unix) |
| `poll_fd()` | `int` | Event loop fd for external integration |

```cpp
if (bus.is_running()) {
    std::cout << "Workers: " << bus.worker_count() << std::endl;
    std::cout << "Sessions: " << bus.session_count() << std::endl;
}

auto stats = bus.stats();
std::cout << "Messages in: " << stats.messages_in << std::endl;
```

### Callbacks

| Method | Callback Signature |
|--------|-------------------|
| `on_message(cb)` | `void(std::string_view msg)` |
| `on_error(cb)` | `void(ErrorCode, std::string_view)` |
| `on_log(cb)` | `void(int level, std::string_view)` |
| `on_worker(cb)` | `void(int id, std::string_view event)` |
| `on_client_connect(cb)` | `void(int id, std::string_view peer)` |
| `on_client_disconnect(cb)` | `void(int id, std::string_view reason)` |

```cpp
bus.on_message([](std::string_view msg) {
    std::cout << "Response: " << msg << std::endl;
});

bus.on_error([](stdiobus::ErrorCode code, std::string_view msg) {
    std::cerr << "Error " << static_cast<int>(code) << ": " << msg << std::endl;
});
```

---

## BusBuilder Class

Fluent builder for Bus configuration.

### Configuration Methods

| Method | Description |
|--------|-------------|
| `config_path(path)` | Set JSON config file path |
| `config_json(json)` | Set inline JSON config |
| `log_level(level)` | 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR |
| `listen_tcp(host, port)` | Enable TCP listener |
| `listen_unix(path)` | Enable Unix socket listener |

### Callback Methods

| Method | Description |
|--------|-------------|
| `on_message(cb)` | Set message callback |
| `on_error(cb)` | Set error callback |
| `on_log(cb)` | Set log callback |
| `on_worker(cb)` | Set worker event callback |

### Build

| Method | Returns |
|--------|---------|
| `build()` | `Bus` |

```cpp
auto bus = stdiobus::BusBuilder()
    .config_path("config.json")
    .log_level(1)
    .listen_tcp("0.0.0.0", 9800)
    .on_message([](auto msg) { std::cout << msg << std::endl; })
    .on_error([](auto code, auto msg) { std::cerr << msg << std::endl; })
    .build();
```

---

## AsyncBus Class

Promise-based async wrapper with `std::future`.

### Construction

```cpp
stdiobus::AsyncBus bus("config.json");
// or
stdiobus::AsyncBus bus(options);
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `start()` | `Error` | Start the bus |
| `stop(timeout)` | `Error` | Stop the bus |
| `pump(timeout)` | `int` | Process I/O (call regularly) |
| `request_async(msg, timeout)` | `std::future<AsyncResult>` | Send request, get future |
| `notify(msg)` | `Error` | Send notification (no response) |
| `check_timeouts()` | `void` | Resolve timed-out requests |
| `bus()` | `Bus&` | Access underlying Bus |

```cpp
stdiobus::AsyncBus bus("config.json");
bus.start();

auto future = bus.request_async(
    R"({"jsonrpc":"2.0","method":"work","id":1})",
    std::chrono::seconds(30)
);

// Pump until ready
while (future.wait_for(0ms) != std::future_status::ready) {
    bus.pump(10ms);
    bus.check_timeouts();
}

auto result = future.get();
if (result) {
    std::cout << "Response: " << result.response << std::endl;
} else {
    std::cerr << "Error: " << result.error.message() << std::endl;
}
```

---

## Error Handling

### Error Class

```cpp
stdiobus::Error err = bus.start();

if (err) {  // true if error
    std::cout << "Code: " << static_cast<int>(err.code()) << std::endl;
    std::cout << "Message: " << err.message() << std::endl;
    
    if (err.is_retryable()) {
        // Safe to retry
    }
}
```

### Error Codes

| Code | Value | Retryable | Description |
|------|-------|-----------|-------------|
| Ok | 0 | - | Success |
| Error | -1 | No | Generic error |
| Again | -2 | Yes | Try again |
| Eof | -3 | No | End of file |
| Full | -4 | Yes | Buffer full |
| NotFound | -5 | No | Not found |
| Invalid | -6 | No | Invalid argument |
| Config | -10 | No | Configuration error |
| Worker | -11 | No | Worker error |
| Routing | -12 | No | Routing error |
| Buffer | -13 | No | Buffer error |
| State | -15 | No | Invalid state |
| Timeout | -20 | Yes | Timeout |
| PolicyDenied | -21 | No | Policy denied |

### Exception Mode

```cpp
// Compile with -DSTDIOBUS_CPP_EXCEPTIONS=1

try {
    stdiobus::throw_if_error(bus.start());
} catch (const stdiobus::Exception& e) {
    std::cerr << "Exception: " << e.what() << std::endl;
    std::cerr << "Code: " << static_cast<int>(e.code()) << std::endl;
}
```

---

## Types

### State Enum

```cpp
enum class State {
    Created = 0,
    Starting = 1,
    Running = 2,
    Stopping = 3,
    Stopped = 4
};

std::cout << stdiobus::state_name(bus.state()) << std::endl;
```

### Stats Struct

```cpp
struct Stats {
    uint64_t messages_in;
    uint64_t messages_out;
    uint64_t bytes_in;
    uint64_t bytes_out;
    uint64_t worker_restarts;
    uint64_t routing_errors;
    uint64_t client_connects;
    uint64_t client_disconnects;
};
```

### ListenMode Enum

```cpp
enum class ListenMode {
    None = 0,   // Embedded mode
    Tcp = 1,    // TCP listener
    Unix = 2    // Unix socket
};
```

---

## FFI Layer (Direct C API)

```cpp
#include <stdiobus/ffi.hpp>

// Create using C API
stdio_bus_options_t opts{};
opts.config_path = "config.json";
opts.on_message = my_callback;
opts.user_data = my_context;

auto handle = stdiobus::ffi::create(&opts);
handle.start();
handle.step(100);
handle.stop(5);
stdiobus::ffi::destroy(handle);
```
