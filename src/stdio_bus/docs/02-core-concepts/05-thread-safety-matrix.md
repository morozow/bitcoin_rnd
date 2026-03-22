# Thread Safety Matrix

## Purpose

Explicitly documents thread-safety, valid call context, and reentrancy for every public method.

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ Safe | Can call concurrently from multiple threads |
| 🔒 Single-thread | Call only from owner/event-loop thread |
| 🔄 Ext. sync | Safe if caller provides synchronization |
| ❌ Forbidden | Not allowed by contract |
| ⚠️ Callback | Only from callback context |

## Bus Class Matrix

| Method | Thread Safety | From Callback | Valid States | Notes |
|--------|---------------|---------------|--------------|-------|
| `Bus(config)` | 🔒 Single | N/A | - | Construction |
| `~Bus()` | 🔒 Single | ❌ | Any | Calls stop() |
| `start()` | 🔄 Ext. sync | ❌ | Created | Once only |
| `step(timeout)` | 🔒 Single | ❌ | Running | Event loop driver |
| `send(msg)` | 🔒 Single | ⚠️ Careful | Running | See notes |
| `stop(timeout)` | 🔄 Ext. sync | ❌ | Any | Idempotent |
| `state()` | ✅ Safe | ✅ | Any | Read-only |
| `is_running()` | ✅ Safe | ✅ | Any | Read-only |
| `is_created()` | ✅ Safe | ✅ | Any | Read-only |
| `is_stopped()` | ✅ Safe | ✅ | Any | Read-only |
| `stats()` | ✅ Safe | ✅ | Any | Snapshot |
| `worker_count()` | ✅ Safe | ✅ | Any | Read-only |
| `session_count()` | ✅ Safe | ✅ | Any | Read-only |
| `pending_count()` | ✅ Safe | ✅ | Any | Read-only |
| `client_count()` | ✅ Safe | ✅ | Any | Read-only |
| `poll_fd()` | ✅ Safe | ✅ | Any | Read-only |
| `on_message(cb)` | 🔄 Ext. sync | ❌ | Created/Running | Before start preferred |
| `on_error(cb)` | 🔄 Ext. sync | ❌ | Created/Running | Before start preferred |
| `on_log(cb)` | 🔄 Ext. sync | ❌ | Created/Running | Before start preferred |
| `on_worker(cb)` | 🔄 Ext. sync | ❌ | Created/Running | Before start preferred |
| `raw_handle()` | ✅ Safe | ✅ | Any | Read-only |

## BusBuilder Matrix

| Method | Thread Safety | Notes |
|--------|---------------|-------|
| `BusBuilder()` | 🔒 Single | Construction |
| `config_path()` | 🔒 Single | Mutates builder |
| `config_json()` | 🔒 Single | Mutates builder |
| `log_level()` | 🔒 Single | Mutates builder |
| `listen_tcp()` | 🔒 Single | Mutates builder |
| `listen_unix()` | 🔒 Single | Mutates builder |
| `on_message()` | 🔒 Single | Mutates builder |
| `on_error()` | 🔒 Single | Mutates builder |
| `on_log()` | 🔒 Single | Mutates builder |
| `on_worker()` | 🔒 Single | Mutates builder |
| `build()` | 🔒 Single | Consumes builder |

## AsyncBus Matrix

| Method | Thread Safety | From Callback | Notes |
|--------|---------------|---------------|-------|
| `AsyncBus(config)` | 🔒 Single | N/A | Construction |
| `start()` | 🔄 Ext. sync | ❌ | Once only |
| `stop(timeout)` | 🔄 Ext. sync | ❌ | Idempotent |
| `pump(timeout)` | 🔒 Single | ❌ | Event loop driver |
| `request_async()` | 🔒 Single | ⚠️ Careful | Returns future |
| `notify()` | 🔒 Single | ⚠️ Careful | Fire-and-forget |
| `check_timeouts()` | 🔒 Single | ❌ | Resolve expired |
| `bus()` | ✅ Safe | ✅ | Returns reference |

## Callback Context Rules

| Callback | Thread | Can call `send()` | Can call `step()` | Can call `stop()` | Can block |
|----------|--------|-------------------|-------------------|-------------------|-----------|
| `on_message` | step() thread | ⚠️ Yes, carefully | ❌ No | ❌ No | ❌ No |
| `on_error` | step() thread | ⚠️ Yes, carefully | ❌ No | ❌ No | ❌ No |
| `on_log` | step() thread | ❌ No | ❌ No | ❌ No | ❌ No |
| `on_worker` | step() thread | ⚠️ Yes, carefully | ❌ No | ❌ No | ❌ No |
| `on_client_connect` | step() thread | ⚠️ Yes, carefully | ❌ No | ❌ No | ❌ No |
| `on_client_disconnect` | step() thread | ⚠️ Yes, carefully | ❌ No | ❌ No | ❌ No |

### Notes on `send()` from Callback

Calling `send()` from a callback is technically allowed but requires care:
- May cause recursive message processing
- May trigger backpressure
- Keep callback fast to avoid blocking event loop

## Safe Patterns

### Single-Owner Thread (Recommended)

```cpp
// Owner thread drives everything
std::thread owner([&bus]() {
    bus.start();
    while (running.load()) {
        bus.step(100ms);
    }
    bus.stop();
});

// Other threads communicate via queue
std::queue<std::string> outgoing;
std::mutex queue_mutex;

// Producer thread
{
    std::lock_guard lock(queue_mutex);
    outgoing.push(message);
}

// Owner thread processes queue
while (!outgoing.empty()) {
    std::lock_guard lock(queue_mutex);
    bus.send(outgoing.front());
    outgoing.pop();
}
```

### Read-Only Access from Other Threads

```cpp
// Safe: read-only methods
void monitor_thread(const stdiobus::Bus& bus) {
    while (running) {
        std::cout << "Workers: " << bus.worker_count() << std::endl;
        std::cout << "Sessions: " << bus.session_count() << std::endl;
        std::this_thread::sleep_for(1s);
    }
}
```

## Known Hazards

| Hazard | Consequence | Prevention |
|--------|-------------|------------|
| `stop()` + `step()` race | Undefined behavior | External synchronization |
| Reentrant `step()` | Stack overflow / corruption | Never call from callback |
| Callback registration after `start()` | May miss events | Register before start |
| Long-running callback | Event loop starvation | Offload to queue |
| Mutex in callback | Deadlock risk | Avoid or use try_lock |

## Verification Checklist

- [ ] TSAN/Helgrind clean under concurrent access
- [ ] Concurrent `send()` stress test (if supported)
- [ ] `stop()` vs `step()` race test
- [ ] Callback reentrancy test
- [ ] Post-stop API misuse test
- [ ] Callback exception safety test
