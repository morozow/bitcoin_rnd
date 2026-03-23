// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_NODE_STDIO_BUS_HOOKS_H
#define BITCOIN_NODE_STDIO_BUS_HOOKS_H

#include <atomic>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <string_view>

#include <uint256.h>

namespace node {

/**
 * @brief Event types for stdio_bus hooks
 * 
 * These events are fired at key points in the P2P message processing
 * and validation pipeline. All hooks are read-only observers and
 * MUST NOT modify any state or affect consensus decisions.
 */

/** Message received event */
struct MessageEvent {
    int64_t peer_id;
    std::string msg_type;  // Owning copy for async safety
    size_t size_bytes;
    int64_t received_us;  // Monotonic timestamp in microseconds
};

/** Headers received event */
struct HeadersEvent {
    int64_t peer_id;
    size_t count;
    uint256 first_prev_hash;  // Owning copy for async safety
    int64_t received_us;
};

/** Block received event */
struct BlockReceivedEvent {
    int64_t peer_id;
    uint256 hash;  // Owning copy for async safety
    int height;  // -1 if unknown
    size_t size_bytes;
    size_t tx_count;
    int64_t received_us;
};

/** Block validated event */
struct BlockValidatedEvent {
    uint256 hash;  // Owning copy for async safety
    int height;
    size_t tx_count;
    int64_t received_us;
    int64_t validated_us;
    bool accepted;
    std::string reject_reason;  // Owning copy, empty if accepted
};

/** Transaction admission event */
struct TxAdmissionEvent {
    uint256 txid;   // Owning copy for async safety
    uint256 wtxid;  // Owning copy for async safety
    size_t size_bytes;
    int64_t received_us;
    int64_t processed_us;
    bool accepted;
    std::string reject_reason;  // Owning copy, empty if accepted
};

/** Message handler loop event */
struct MsgHandlerLoopEvent {
    int64_t iteration;
    int64_t start_us;
    int64_t end_us;
    int messages_processed;
    bool had_work;
};

/** RPC call event */
struct RpcCallEvent {
    std::string method;  // Owning copy for async safety
    int64_t start_us;
    int64_t end_us;
    bool success;
};

// ============================================================================
// Phase 5: P2P/RPC Degradation Events (#18678)
// ============================================================================

/**
 * @brief HTTP request enqueue event
 * 
 * Fired when an HTTP request is received and queued (or rejected).
 * Captures queue admission decisions and queue state.
 */
struct RpcHttpEnqueueEvent {
    int64_t request_id;       ///< Unique request identifier (propagated to dispatch/lifecycle)
    std::string uri;          ///< Request URI (e.g., "/", "/wallet/")
    std::string peer_addr;    ///< Client address
    int64_t received_us;      ///< When request was received
    int queue_depth;          ///< Queue depth at admission time
    int max_queue_depth;      ///< Maximum queue capacity
    bool admitted;            ///< Whether request was admitted (false = rejected)
};

/**
 * @brief HTTP request dispatch event
 * 
 * Fired when an HTTP request is dispatched to a worker thread.
 * Captures queue wait time.
 */
struct RpcHttpDispatchEvent {
    int64_t request_id;       ///< Same request_id from enqueue event
    int64_t enqueued_us;      ///< When request was enqueued
    int64_t dispatched_us;    ///< When request was dispatched to worker
};

/**
 * @brief RPC call lifecycle event
 * 
 * Fired after RPC call completes. Captures execution timing and result.
 */
struct RpcCallLifecycleEvent {
    int64_t request_id;       ///< Same request_id from enqueue/dispatch events
    std::string method;       ///< RPC method name
    std::string peer_addr;    ///< Client address
    
    // Timing (all monotonic microseconds)
    int64_t exec_start_us;    ///< RPC execution started
    int64_t exec_end_us;      ///< RPC execution completed
    
    // Result
    bool success;             ///< Whether call succeeded
    int http_status;          ///< HTTP status code
    size_t response_size;     ///< Response size in bytes
};

/**
 * @brief stdio_bus mode enum
 */
enum class StdioBusMode {
    Off = 0,     ///< Disabled (default)
    Shadow = 1,  ///< Observe only, no behavior change
    Active = 2   ///< Enable optimizations (future)
};

/**
 * @brief Parse stdio_bus mode from string
 * @param str Mode string ("off", "shadow", "active")
 * @return Parsed mode, or Off if invalid
 */
inline StdioBusMode ParseStdioBusMode(std::string_view str) {
    if (str == "shadow") return StdioBusMode::Shadow;
    if (str == "active") return StdioBusMode::Active;
    return StdioBusMode::Off;
}

/**
 * @brief Convert stdio_bus mode to string
 */
inline std::string_view StdioBusModeToString(StdioBusMode mode) {
    switch (mode) {
        case StdioBusMode::Shadow: return "shadow";
        case StdioBusMode::Active: return "active";
        default: return "off";
    }
}

/**
 * @brief Abstract interface for stdio_bus hooks
 * 
 * This interface allows external observers to receive events from
 * the Bitcoin Core P2P and validation subsystems without modifying
 * their behavior.
 * 
 * CRITICAL REQUIREMENTS:
 * 1. All callbacks MUST be non-blocking (use bounded queue internally)
 * 2. All callbacks MUST NOT throw exceptions
 * 3. All callbacks MUST NOT modify any Bitcoin Core state
 * 4. All callbacks MUST NOT affect consensus decisions
 * 5. On any error, fail silently (fail-open)
 * 
 * Thread safety: Callbacks may be invoked from multiple threads.
 * Implementations must be thread-safe.
 */
class StdioBusHooks {
public:
    virtual ~StdioBusHooks() = default;

    /** Check if hooks are enabled */
    virtual bool Enabled() const = 0;

    /** Check if shadow mode (observe-only) is active */
    virtual bool ShadowMode() const { return true; }

    // ========== P2P Events ==========

    /** Called when any P2P message is received (before processing) */
    virtual void OnMessage(const MessageEvent& event) = 0;

    /** Called when HEADERS message is received */
    virtual void OnHeaders(const HeadersEvent& event) = 0;

    /** Called when block data is received (BLOCK or reconstructed from CMPCTBLOCK) */
    virtual void OnBlockReceived(const BlockReceivedEvent& event) = 0;

    // ========== Validation Events ==========

    /** Called after block validation completes */
    virtual void OnBlockValidated(const BlockValidatedEvent& event) = 0;

    /** Called after transaction admission attempt */
    virtual void OnTxAdmission(const TxAdmissionEvent& event) = 0;

    // ========== Performance Events ==========

    /** Called at end of each message handler loop iteration */
    virtual void OnMsgHandlerLoop(const MsgHandlerLoopEvent& event) = 0;

    /** Called after RPC call completes */
    virtual void OnRpcCall(const RpcCallEvent& event) = 0;

    // ========== Phase 5: P2P/RPC Degradation Events (#18678) ==========

    /** Called when HTTP request is enqueued (or rejected) */
    virtual void OnRpcHttpEnqueue(const RpcHttpEnqueueEvent& event) = 0;

    /** Called when HTTP request is dispatched to worker */
    virtual void OnRpcHttpDispatch(const RpcHttpDispatchEvent& event) = 0;

    /** Called after RPC call completes */
    virtual void OnRpcCallLifecycle(const RpcCallLifecycleEvent& event) = 0;
};

/**
 * @brief No-op implementation of StdioBusHooks
 * 
 * Used when stdio_bus is disabled. All methods are empty and inline.
 */
class NoOpStdioBusHooks final : public StdioBusHooks {
public:
    bool Enabled() const override { return false; }
    bool ShadowMode() const override { return true; }
    
    void OnMessage(const MessageEvent&) override {}
    void OnHeaders(const HeadersEvent&) override {}
    void OnBlockReceived(const BlockReceivedEvent&) override {}
    void OnBlockValidated(const BlockValidatedEvent&) override {}
    void OnTxAdmission(const TxAdmissionEvent&) override {}
    void OnMsgHandlerLoop(const MsgHandlerLoopEvent&) override {}
    void OnRpcCall(const RpcCallEvent&) override {}
    
    // Phase 5: P2P/RPC Degradation
    void OnRpcHttpEnqueue(const RpcHttpEnqueueEvent&) override {}
    void OnRpcHttpDispatch(const RpcHttpDispatchEvent&) override {}
    void OnRpcCallLifecycle(const RpcCallLifecycleEvent&) override {}
};

/**
 * @brief Get current monotonic time in microseconds
 * 
 * Uses std::chrono::steady_clock for monotonic timestamps.
 */
inline int64_t GetMonotonicTimeUs() {
    return std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now().time_since_epoch()
    ).count();
}

/**
 * @brief Generate unique request ID
 * 
 * Thread-safe atomic counter for request identification.
 * Used to correlate HTTP enqueue → dispatch → RPC lifecycle events.
 */
inline int64_t GenerateRequestId() {
    static std::atomic<int64_t> s_request_counter{0};
    return s_request_counter.fetch_add(1, std::memory_order_relaxed);
}

} // namespace node

#endif // BITCOIN_NODE_STDIO_BUS_HOOKS_H
