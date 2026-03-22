# Failure Taxonomy

## Purpose

Classifies failure types for stdio_bus/C++ SDK and defines expected recovery behavior.

## Classification Axes

| Axis | Values |
|------|--------|
| Layer | Transport / Routing / Process / Host / Config |
| Duration | Transient / Intermittent / Permanent |
| Impact | Single session / Single connection / Global |
| Recovery | Auto-recoverable / Manual intervention |

## Failure Classes

### 1. Transport Failures

| Failure | Error Code | Impact | Recovery |
|---------|------------|--------|----------|
| TCP connection drop | Eof | Single connection | Reconnect |
| Unix socket disconnect | Eof | Single connection | Reconnect |
| Broken stdio pipe | Eof | Worker | Worker restart |
| Partial write | Again | Transient | Automatic retry |
| Socket bind failure | Config | Global | Fix config |

**Expected Handling:**
```cpp
bus.on_error([](auto code, auto msg) {
    if (code == stdiobus::ErrorCode::Eof) {
        // Connection closed - may reconnect
        log_warn("Connection closed: {}", msg);
    }
});
```

### 2. Backpressure Failures

| Failure | Error Code | Impact | Recovery |
|---------|------------|--------|----------|
| Output queue full | Full | Single message | Retry with backoff |
| Input buffer limit | Full | Single connection | Slow down producer |
| Worker unresponsive | Timeout | Single session | Timeout + retry |

**Expected Handling:**
```cpp
auto err = bus.send(message);
if (err.code() == stdiobus::ErrorCode::Full) {
    // Backpressure - retry with exponential backoff
    schedule_retry(message, backoff_delay);
}
```

### 3. Protocol/Message Failures

| Failure | Error Code | Impact | Recovery |
|---------|------------|--------|----------|
| Invalid NDJSON frame | Invalid | Single message | Reject, log |
| Malformed JSON-RPC | Invalid | Single message | Reject, log |
| Missing routing fields | Routing | Single message | Reject, log |

**Expected Handling:**
```cpp
// These are logged via on_error callback
// Bus continues processing other messages
```

### 4. Routing Failures

| Failure | Error Code | Impact | Recovery |
|---------|------------|--------|----------|
| Unknown session | NotFound | Single message | Create new session |
| Missing correlation | Routing | Single response | Log, continue |
| Worker mismatch | Routing | Single message | Re-route |

**Expected Handling:**
```cpp
bus.on_error([](auto code, auto msg) {
    if (code == stdiobus::ErrorCode::Routing) {
        log_warn("Routing error: {}", msg);
        // Message may be lost - implement idempotency
    }
});
```

### 5. Worker/Process Failures

| Failure | Error Code | Impact | Recovery |
|---------|------------|--------|----------|
| Worker crash | Worker | Worker sessions | Auto-restart |
| Restart storm | Worker | Pool | Backoff, circuit break |
| Startup timeout | Worker | Worker | Retry with backoff |

**Expected Handling:**
```cpp
bus.on_worker([](int id, std::string_view event) {
    if (event == "failed") {
        log_error("Worker {} failed", id);
        metrics.worker_failures++;
    } else if (event == "restarting") {
        log_warn("Worker {} restarting", id);
    }
});
```

### 6. Lifecycle/API Misuse

| Failure | Error Code | Impact | Recovery |
|---------|------------|--------|----------|
| `send()` before `start()` | State | Single call | Fix code |
| `start()` called twice | State | Single call | Idempotent/error |
| `step()` after `stop()` | State | Single call | Fix code |

**Expected Handling:**
```cpp
// These indicate bugs in calling code
if (auto err = bus.send(msg); err.code() == stdiobus::ErrorCode::State) {
    log_error("BUG: send() called in wrong state");
}
```

### 7. Configuration Failures

| Failure | Error Code | Impact | Recovery |
|---------|------------|--------|----------|
| Invalid JSON config | Config | Global | Fix config file |
| Invalid limits | Config | Global | Fix config |
| Missing required field | Config | Global | Fix config |

**Expected Handling:**
```cpp
stdiobus::Bus bus("config.json");
if (!bus) {
    log_error("Failed to create bus - check configuration");
    exit(1);
}
```

### 8. Host Integration Failures

| Failure | Impact | Recovery |
|---------|--------|----------|
| Callback throws | Single event | Caught, logged |
| Callback blocks | Global latency | Fix callback code |
| Reentrancy misuse | Undefined | Fix callback code |

**Expected Handling:**
```cpp
// Keep callbacks fast and exception-free
bus.on_message([](auto msg) {
    try {
        enqueue_fast(msg);  // Don't block
    } catch (...) {
        // Logged by SDK, but avoid this
    }
});
```

## Severity Model

| Level | Description | Example |
|-------|-------------|---------|
| S0 | Data corruption / invariant violation | Message delivered to wrong session |
| S1 | Global outage | All workers dead, no restart |
| S2 | Partial outage | Some sessions affected |
| S3 | Degraded performance | High latency, retries |
| S4 | Recoverable noise | Transient backpressure |

## Recovery Strategy Matrix

| Failure Class | Default Strategy | Escalation |
|---------------|------------------|------------|
| Transport drop | Reconnect + backoff | Circuit breaker |
| Backpressure | Throttle + retry | Drop policy |
| Protocol invalid | Reject + log | Block sender |
| Routing error | Log + continue | Alert |
| Worker crash | Supervised restart | Disable pool |
| Config invalid | Fail fast | Rollback config |
| API misuse | Return error | Fix code |

## Failure Injection Checklist

For testing resilience:

- [ ] Simulate disconnect during in-flight request
- [ ] Force queue full under load
- [ ] Inject malformed NDJSON/JSON
- [ ] Kill worker process repeatedly
- [ ] Throw from callback
- [ ] Delay consumer to trigger timeout
- [ ] Concurrent stop() during step()
- [ ] Send after stop()

## Metrics per Failure Class

| Metric | Description |
|--------|-------------|
| `failure_count{class}` | Count by failure class |
| `mttr_seconds` | Mean time to recovery |
| `retry_success_rate` | Successful retries / total retries |
| `worker_restart_count` | Worker restarts |
| `dropped_message_count` | Messages that couldn't be delivered |
| `circuit_breaker_state` | Open/closed/half-open |
