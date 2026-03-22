# Event Loop Step Model

## Purpose

Defines the contract for `step()` / event-loop integration: blocking behavior, work quota, fairness, progress guarantees, and idle/load behavior.

## API Contract

```cpp
// Non-blocking step with timeout
int Bus::step(Duration timeout = Duration::zero());

// Returns:
// - Positive: number of events processed
// - Zero: no events (idle)
// - Negative: error code
```

## Step Semantics

| Property | Value |
|----------|-------|
| Blocking mode | Non-blocking by default, blocks up to `timeout` |
| Timeout semantics | Maximum wait time for events (0 = poll, return immediately) |
| Max work per step | Unbounded (processes all ready events) |
| Progress guarantee | Lock-free progress on ready I/O |
| Idle behavior | Returns 0 when no events |

## Timeout Behavior

```cpp
// Non-blocking poll (immediate return)
bus.step(std::chrono::milliseconds(0));

// Wait up to 100ms for events
bus.step(std::chrono::milliseconds(100));

// Block indefinitely (not recommended for embedding)
bus.step(std::chrono::milliseconds(-1));
```

## Fairness Policy

| Dimension | Policy |
|-----------|--------|
| Between connections | Readiness-based (epoll/kqueue level-triggered) |
| Between sessions | No explicit fairness (depends on worker response order) |
| Input vs output | Output prioritized to prevent backpressure |
| Starvation prevention | None (caller controls via timeout) |

## Queue Interaction

| Queue | Policy |
|-------|--------|
| Input queue | Read all available data per connection |
| Output queue | Flush as much as socket accepts |
| Backpressure | Returns EAGAIN/Full, does not block |
| Partial read/write | Handled internally, transparent to caller |

## Callback Interaction

| Property | Value |
|----------|-------|
| Callback thread | Same thread that calls `step()` |
| Callback timing | Synchronously during `step()` |
| Reentrancy | **FORBIDDEN** - do not call `step()` from callback |
| Blocking in callback | **DISCOURAGED** - blocks entire event loop |

```cpp
// CORRECT
bus.on_message([](auto msg) {
    enqueue_for_processing(msg);  // Fast, non-blocking
});

// WRONG
bus.on_message([&bus](auto msg) {
    bus.step(100ms);  // ❌ Reentrancy - undefined behavior
});
```

## Return/Status Semantics

| Return | Meaning |
|--------|---------|
| > 0 | Number of events processed |
| 0 | No events (idle tick) |
| -1 (Error) | Generic error |
| -2 (Again) | Would block (with timeout=0) |
| -6 (Invalid) | Invalid state (not started) |
| -15 (State) | Bus not in Running state |

## Host Integration Patterns

### Tight Loop (CPU-intensive)

```cpp
while (running) {
    int events = bus.step(std::chrono::milliseconds(0));
    if (events == 0) {
        std::this_thread::sleep_for(std::chrono::microseconds(100));
    } else if (events < 0) {
        handle_error(events);
    }
}
```

### Timeout-driven Loop (Recommended)

```cpp
while (running && bus.is_running()) {
    int events = bus.step(std::chrono::milliseconds(100));
    if (events < 0 && events != static_cast<int>(stdiobus::ErrorCode::Again)) {
        handle_error(events);
    }
    // Do other periodic work here
}
```

### External Event Loop Integration

```cpp
// Get poll fd for epoll/kqueue/libuv
int fd = bus.poll_fd();

// Add to your event loop
add_to_event_loop(fd, POLLIN, [&bus]() {
    bus.step(std::chrono::milliseconds(0));  // Non-blocking
});
```

## Performance Considerations

| Parameter | Recommendation |
|-----------|----------------|
| Step timeout | 10-100ms for responsive apps |
| Events per tick | No limit (process all ready) |
| CPU burn prevention | Use non-zero timeout |
| Latency-sensitive | Use 0-10ms timeout |

## Determinism Notes

| Property | Guarantee |
|----------|-----------|
| Event processing order | Deterministic for same input sequence |
| Callback invocation order | Same as event arrival order |
| Reproducibility | Yes, given same input trace |

## Test Checklist

- [ ] Idle loop without busy spin (CPU usage)
- [ ] High load fairness across sessions
- [ ] Partial writes under backpressure
- [ ] Callback latency impact on loop
- [ ] Deterministic replay for same input trace
- [ ] Timeout accuracy under load
