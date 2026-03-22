# Callbacks Contract

## Purpose

Defines when callbacks are invoked, execution context, ordering guarantees, and what is forbidden inside callbacks.

## Callback Types

| Callback | Signature | When Invoked |
|----------|-----------|--------------|
| `on_message` | `void(std::string_view msg)` | Response/notification from worker |
| `on_error` | `void(ErrorCode, std::string_view)` | Error occurred |
| `on_log` | `void(int level, std::string_view)` | Log message |
| `on_worker` | `void(int id, std::string_view event)` | Worker lifecycle event |
| `on_client_connect` | `void(int id, std::string_view peer)` | Client connected (TCP/Unix) |
| `on_client_disconnect` | `void(int id, std::string_view reason)` | Client disconnected |

## Execution Context

| Property | Value |
|----------|-------|
| **Thread** | Same thread that calls `step()` |
| **Timing** | Synchronously during `step()` |
| **Reentrancy** | NOT allowed - do not call `step()` from callback |
| **Blocking** | Avoid - blocks entire event loop |
| **Exceptions** | Caught and logged, do not propagate |

## Registration

```cpp
// During construction
auto bus = stdiobus::BusBuilder()
    .config_path("config.json")
    .on_message([](std::string_view msg) { /* ... */ })
    .on_error([](auto code, auto msg) { /* ... */ })
    .build();

// After construction
bus.on_message([](std::string_view msg) { /* ... */ });
bus.on_worker([](int id, std::string_view event) { /* ... */ });
```

## Callback Lifetime

```cpp
// WRONG: Dangling reference
{
    std::string context = "important";
    bus.on_message([&context](auto msg) {
        std::cout << context << ": " << msg << std::endl;
    });
}  // context destroyed, callback has dangling reference!

// CORRECT: Capture by value or use shared_ptr
auto context = std::make_shared<std::string>("important");
bus.on_message([context](auto msg) {
    std::cout << *context << ": " << msg << std::endl;
});
```

## Ordering Guarantees

| Guarantee | Description |
|-----------|-------------|
| **Per-session order** | Messages for same session delivered in order |
| **Cross-session** | No ordering guarantee |
| **Callbacks vs data** | Worker events may interleave with messages |

## Forbidden Actions Inside Callbacks

| Action | Why Forbidden |
|--------|---------------|
| `bus.step()` | Reentrancy causes undefined behavior |
| Long blocking I/O | Blocks entire event loop |
| Throwing exceptions | Caught but disrupts processing |
| Modifying callback | Race condition |

## Safe Callback Patterns

### Minimal Work Pattern

```cpp
std::queue<std::string> message_queue;
std::mutex queue_mutex;

bus.on_message([&](std::string_view msg) {
    // Minimal work: just enqueue
    std::lock_guard lock(queue_mutex);
    message_queue.push(std::string(msg));
});

// Process in main loop
while (bus.is_running()) {
    bus.step(100ms);
    
    // Process queued messages outside callback
    std::lock_guard lock(queue_mutex);
    while (!message_queue.empty()) {
        process_message(message_queue.front());
        message_queue.pop();
    }
}
```

### Async Dispatch Pattern

```cpp
std::function<void(std::string)> async_handler;

bus.on_message([&](std::string_view msg) {
    // Dispatch to async handler
    if (async_handler) {
        async_handler(std::string(msg));
    }
});

// Set up async processing
async_handler = [](std::string msg) {
    std::thread([msg = std::move(msg)]() {
        heavy_processing(msg);
    }).detach();
};
```

### Error Logging Pattern

```cpp
bus.on_error([](stdiobus::ErrorCode code, std::string_view msg) {
    // Safe: just logging
    std::cerr << "[ERROR " << static_cast<int>(code) << "] " << msg << std::endl;
    
    // Safe: set flag for main loop
    if (code == stdiobus::ErrorCode::Worker) {
        g_worker_error = true;
    }
});
```

## Worker Event Callbacks

```cpp
bus.on_worker([](int worker_id, std::string_view event) {
    // Events: "started", "stopped", "restarting", "failed"
    std::cout << "Worker " << worker_id << ": " << event << std::endl;
    
    if (event == "failed") {
        // Log for alerting
        alert_ops_team(worker_id);
    }
});
```

## Client Connection Callbacks (TCP/Unix)

```cpp
std::unordered_set<int> connected_clients;

bus.on_client_connect([&](int client_id, std::string_view peer) {
    connected_clients.insert(client_id);
    std::cout << "Client " << client_id << " connected from " << peer << std::endl;
});

bus.on_client_disconnect([&](int client_id, std::string_view reason) {
    connected_clients.erase(client_id);
    std::cout << "Client " << client_id << " disconnected: " << reason << std::endl;
});
```

## Testing Callbacks

```cpp
// Test that callback is invoked
bool message_received = false;
std::string received_content;

bus.on_message([&](std::string_view msg) {
    message_received = true;
    received_content = std::string(msg);
});

bus.start();
bus.send(R"({"jsonrpc":"2.0","method":"echo","id":1})");

// Pump until response
for (int i = 0; i < 100 && !message_received; ++i) {
    bus.step(10ms);
}

ASSERT_TRUE(message_received);
ASSERT_FALSE(received_content.empty());
```

## Anti-Patterns

```cpp
// ❌ WRONG: Blocking in callback
bus.on_message([](auto msg) {
    std::this_thread::sleep_for(1s);  // Blocks event loop!
});

// ❌ WRONG: Reentrancy
bus.on_message([&bus](auto msg) {
    bus.step(100ms);  // Undefined behavior!
});

// ❌ WRONG: Throwing
bus.on_message([](auto msg) {
    throw std::runtime_error("oops");  // Caught but bad practice
});

// ❌ WRONG: Heavy computation
bus.on_message([](auto msg) {
    auto result = expensive_ml_inference(msg);  // Blocks everything
});
```
