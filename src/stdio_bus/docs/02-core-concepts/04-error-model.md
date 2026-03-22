# Error Model: Status vs Exception

## Purpose

Defines the unified error model for C/C++ SDK with transparent mapping:
C status codes ↔ C++ status API ↔ exception API.

## Modes

| Mode | Compile Flag | Behavior |
|------|--------------|----------|
| Status (default) | None | Methods return `Error` object |
| Exception | `-DSTDIOBUS_CPP_EXCEPTIONS=1` | Methods throw on error |

## Error Categories

| Category | Description | Retryable |
|----------|-------------|-----------|
| Ok | Success | N/A |
| WouldBlock | Resource temporarily unavailable | Yes |
| QueueFull | Buffer/queue at capacity | Yes |
| Timeout | Operation timed out | Yes |
| EndOfStream | Peer closed connection | Maybe |
| NotFound | Session/route not found | No |
| InvalidArgument | Bad parameter | No |
| InvalidState | Wrong lifecycle state | No |
| ConfigError | Configuration problem | No |
| WorkerError | Worker process issue | No |
| RoutingError | Message routing failed | No |
| InternalError | Unexpected failure | No |

## Mapping Table

| C Code | Value | C++ ErrorCode | Retryable | Description |
|--------|-------|---------------|-----------|-------------|
| `STDIO_BUS_OK` | 0 | `Ok` | - | Success |
| `STDIO_BUS_ERR` | -1 | `Error` | No | Generic error |
| `STDIO_BUS_EAGAIN` | -2 | `Again` | Yes | Try again |
| `STDIO_BUS_EOF` | -3 | `Eof` | Maybe | End of stream |
| `STDIO_BUS_EFULL` | -4 | `Full` | Yes | Buffer full |
| `STDIO_BUS_ENOTFOUND` | -5 | `NotFound` | No | Not found |
| `STDIO_BUS_EINVAL` | -6 | `Invalid` | No | Invalid argument |
| `STDIO_BUS_ERR_CONFIG` | -10 | `Config` | No | Config error |
| `STDIO_BUS_ERR_WORKER` | -11 | `Worker` | No | Worker error |
| `STDIO_BUS_ERR_ROUTING` | -12 | `Routing` | No | Routing error |
| `STDIO_BUS_ERR_BUFFER` | -13 | `Buffer` | No | Buffer error |
| `STDIO_BUS_ERR_STATE` | -15 | `State` | No | Invalid state |
| - | -20 | `Timeout` | Yes | Timeout |
| - | -21 | `PolicyDenied` | No | Policy denied |

## Status Mode (Default)

```cpp
#include <stdiobus.hpp>

stdiobus::Bus bus("config.json");

// Check error with if
if (auto err = bus.start(); err) {
    std::cerr << "Error: " << err.message() << std::endl;
    std::cerr << "Code: " << static_cast<int>(err.code()) << std::endl;
    
    if (err.is_retryable()) {
        // Safe to retry
    }
    return 1;
}

// Check send result
auto err = bus.send(message);
if (err) {
    switch (err.code()) {
        case stdiobus::ErrorCode::Full:
            // Backpressure - retry later
            break;
        case stdiobus::ErrorCode::State:
            // Bus not running
            break;
        default:
            // Other error
            break;
    }
}
```

## Exception Mode

```cpp
// Compile with: -DSTDIOBUS_CPP_EXCEPTIONS=1

#include <stdiobus.hpp>

try {
    stdiobus::Bus bus("config.json");
    stdiobus::throw_if_error(bus.start());
    
    while (bus.is_running()) {
        bus.step(100ms);
        stdiobus::throw_if_error(bus.send(message));
    }
    
} catch (const stdiobus::Exception& e) {
    std::cerr << "Exception: " << e.what() << std::endl;
    std::cerr << "Code: " << static_cast<int>(e.code()) << std::endl;
    
    if (e.error().is_retryable()) {
        // Retry logic
    }
}
```

## Error Context

Each error includes:

| Field | Description |
|-------|-------------|
| `code()` | ErrorCode enum value |
| `message()` | Human-readable description |
| `is_retryable()` | Whether retry is safe |

## Retriability Policy

### Safe to Retry

- `Again` - Resource temporarily busy
- `Full` - Queue/buffer full (apply backoff)
- `Timeout` - Operation timed out

### Do NOT Retry

- `Invalid` - Fix the argument
- `State` - Fix the lifecycle
- `Config` - Fix configuration
- `NotFound` - Session doesn't exist
- `PolicyDenied` - Permission issue

### Conditional

- `Eof` - Depends on reconnect policy
- `Worker` - May recover after restart

## Logging Rules

| Level | When |
|-------|------|
| DEBUG | Retryable errors (Again, Full) |
| WARN | Recoverable errors (Timeout, Eof) |
| ERROR | Non-recoverable errors |

```cpp
bus.on_error([](stdiobus::ErrorCode code, std::string_view msg) {
    if (stdiobus::is_retryable(code)) {
        LOG_DEBUG("Retryable error {}: {}", static_cast<int>(code), msg);
    } else {
        LOG_ERROR("Error {}: {}", static_cast<int>(code), msg);
    }
});
```

## Converting Between Modes

```cpp
// Status to exception
stdiobus::Error err = bus.start();
if (err) {
    throw stdiobus::Exception(err);
}

// Or use helper
stdiobus::throw_if_error(bus.start());

// Exception to status
try {
    do_something();
} catch (const stdiobus::Exception& e) {
    return e.error();  // Returns Error object
}
```

## Testing Matrix

| Scenario | Status Mode | Exception Mode |
|----------|-------------|----------------|
| Success | `!err` is true | No exception |
| Retryable | `err.is_retryable()` | Catch, check `is_retryable()` |
| Fatal | `err` is true | Exception thrown |
| Same outcome | ✅ | ✅ |
