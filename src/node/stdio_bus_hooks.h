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
 * @brief RPC method priority for QoS decisions
 */
enum class RpcMethodPriority {
    High = 0,    ///< Critical methods (stop, getblockchaininfo)
    Medium = 1,  ///< Normal methods (getblock, getrawtransaction)
    Low = 2      ///< Heavy methods (scantxoutset, rescanblockchain)
};

/**
 * @brief Backpressure decision type
 */
enum class RpcBackpressureDecision {
    Admit = 0,      ///< Request admitted to queue
    Reject = 1,     ///< Request rejected (503)
    Throttle = 2,   ///< Request delayed/throttled
    Prioritize = 3  ///< Request prioritized (jumped queue)
};

/**
 * @brief Reason for backpressure decision
 */
enum class RpcBackpressureReason {
    None = 0,           ///< No backpressure applied
    QueueFull = 1,      ///< HTTP work queue at capacity
    P2PLoad = 2,        ///< High P2P processing load
    MethodThrottle = 3, ///< Method-specific rate limit
    LowPriority = 4,    ///< Low priority during congestion
    SystemLoad = 5      ///< General system overload
};

/**
 * @brief HTTP request enqueue event
 * 
 * Fired when an HTTP request is received and queued for processing.
 * Captures queue admission decisions and queue state.
 */
struct RpcHttpEnqueueEvent {
    int64_t request_id;       ///< Unique request identifier
    std::string uri;          ///< Request URI (e.g., "/", "/wallet/")
    std::string peer_addr;    ///< Client address
    int64_t received_us;      ///< When request was received
    int queue_depth;          ///< Queue depth at admission time
    int max_queue_depth;      ///< Maximum queue capacity
    bool admitted;            ///< Whether request was admitted
    RpcBackpressureReason reject_reason;  ///< Reason if rejected
};

/**
 * @brief HTTP request dispatch event
 * 
 * Fired when an HTTP request is dispatched to a worker thread.
 * Captures queue wait time and worker assignment.
 */
struct RpcHttpDispatchEvent {
    int64_t request_id;       ///< Unique request identifier
    int64_t enqueued_us;      ///< When request was enqueued
    int64_t dispatched_us;    ///< When request was dispatched
    int worker_id;            ///< Worker thread ID (0-based)
    int active_workers;       ///< Number of active workers
    int total_workers;        ///< Total worker pool size
};

/**
 * @brief Full RPC call lifecycle event
 * 
 * Comprehensive event capturing the entire RPC call lifecycle
 * from HTTP receive to response send.
 */
struct RpcCallLifecycleEvent {
    int64_t request_id;       ///< Unique request identifier
    std::string method;       ///< RPC method name
    std::string peer_addr;    ///< Client address
    RpcMethodPriority priority;  ///< Method priority classification
    
    // Timing breakdown (all monotonic microseconds)
    int64_t http_received_us;    ///< HTTP request received
    int64_t queue_entered_us;    ///< Entered work queue
    int64_t dispatch_us;         ///< Dispatched to worker
    int64_t parse_start_us;      ///< JSON parsing started
    int64_t exec_start_us;       ///< RPC execution started
    int64_t exec_end_us;         ///< RPC execution completed
    int64_t response_sent_us;    ///< HTTP response sent
    
    // Result
    bool success;             ///< Whether call succeeded
    int http_status;          ///< HTTP status code
    size_t response_size;     ///< Response size in bytes
};

/**
 * @brief RPC backpressure event
 * 
 * Fired when a QoS/backpressure decision is made for an RPC request.
 */
struct RpcBackpressureEvent {
    int64_t request_id;       ///< Unique request identifier
    std::string method;       ///< RPC method (if known)
    int64_t timestamp_us;     ///< When decision was made
    
    RpcBackpressureDecision decision;  ///< What action was taken
    RpcBackpressureReason reason;      ///< Why this decision
    
    // Context for decision
    int queue_depth;          ///< Current queue depth
    int active_rpc_calls;     ///< Active RPC calls
    double p2p_load_score;    ///< P2P subsystem load (0.0-1.0)
    int64_t method_calls_last_sec;  ///< Calls to this method in last second
};

/**
 * @brief P2P/RPC interference snapshot
 * 
 * Periodic snapshot of P2P and RPC subsystem metrics for
 * correlation analysis of interference patterns.
 */
struct P2PRpcInterferenceSnapshotEvent {
    int64_t timestamp_us;     ///< Snapshot timestamp
    int64_t snapshot_interval_us;  ///< Time since last snapshot
    
    // P2P metrics
    int p2p_messages_processed;   ///< Messages processed in interval
    int64_t p2p_processing_us;    ///< Total P2P processing time
    int p2p_queue_depth;          ///< Current P2P message queue depth
    int connected_peers;          ///< Number of connected peers
    
    // RPC metrics
    int rpc_calls_completed;      ///< RPC calls completed in interval
    int64_t rpc_total_latency_us; ///< Total RPC latency in interval
    int rpc_queue_depth;          ///< Current RPC queue depth
    int active_rpc_calls;         ///< Currently executing RPC calls
    
    // Latency percentiles (microseconds)
    int64_t rpc_latency_p50_us;
    int64_t rpc_latency_p95_us;
    int64_t rpc_latency_p99_us;
    
    // Interference indicators
    double p2p_load_score;        ///< P2P load (0.0-1.0)
    double rpc_degradation_score; ///< RPC degradation vs baseline (0.0-1.0)
    double interference_correlation;  ///< Correlation coefficient
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

    /** Called with full RPC call lifecycle data */
    virtual void OnRpcCallLifecycle(const RpcCallLifecycleEvent& event) = 0;

    /** Called when backpressure decision is made */
    virtual void OnRpcBackpressure(const RpcBackpressureEvent& event) = 0;

    /** Called periodically with P2P/RPC interference snapshot */
    virtual void OnP2PRpcInterferenceSnapshot(const P2PRpcInterferenceSnapshotEvent& event) = 0;
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
    void OnRpcBackpressure(const RpcBackpressureEvent&) override {}
    void OnP2PRpcInterferenceSnapshot(const P2PRpcInterferenceSnapshotEvent&) override {}
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
 * @brief Convert RpcMethodPriority to string
 */
inline std::string_view RpcMethodPriorityToString(RpcMethodPriority priority) {
    switch (priority) {
        case RpcMethodPriority::High: return "high";
        case RpcMethodPriority::Medium: return "medium";
        case RpcMethodPriority::Low: return "low";
        default: return "unknown";
    }
}

/**
 * @brief Convert RpcBackpressureDecision to string
 */
inline std::string_view RpcBackpressureDecisionToString(RpcBackpressureDecision decision) {
    switch (decision) {
        case RpcBackpressureDecision::Admit: return "admit";
        case RpcBackpressureDecision::Reject: return "reject";
        case RpcBackpressureDecision::Throttle: return "throttle";
        case RpcBackpressureDecision::Prioritize: return "prioritize";
        default: return "unknown";
    }
}

/**
 * @brief Convert RpcBackpressureReason to string
 */
inline std::string_view RpcBackpressureReasonToString(RpcBackpressureReason reason) {
    switch (reason) {
        case RpcBackpressureReason::None: return "none";
        case RpcBackpressureReason::QueueFull: return "queue_full";
        case RpcBackpressureReason::P2PLoad: return "p2p_load";
        case RpcBackpressureReason::MethodThrottle: return "method_throttle";
        case RpcBackpressureReason::LowPriority: return "low_priority";
        case RpcBackpressureReason::SystemLoad: return "system_load";
        default: return "unknown";
    }
}

/**
 * @brief Classify RPC method priority
 * 
 * Returns priority classification for QoS decisions.
 * High: Critical control methods
 * Medium: Normal query methods
 * Low: Heavy/long-running methods
 */
inline RpcMethodPriority ClassifyRpcMethodPriority(std::string_view method) {
    // High priority: critical control and status methods
    if (method == "stop" || method == "getblockchaininfo" || 
        method == "getnetworkinfo" || method == "getpeerinfo" ||
        method == "ping" || method == "uptime" || method == "help" ||
        method == "getmempoolinfo" || method == "getconnectioncount") {
        return RpcMethodPriority::High;
    }
    
    // Low priority: heavy/long-running methods
    if (method == "scantxoutset" || method == "rescanblockchain" ||
        method == "importwallet" || method == "importprivkey" ||
        method == "importaddress" || method == "importpubkey" ||
        method == "importmulti" || method == "importdescriptors" ||
        method == "dumpprivkey" || method == "dumpwallet" ||
        method == "listunspent" || method == "listtransactions" ||
        method == "getblock" || method == "getrawtransaction") {
        return RpcMethodPriority::Low;
    }
    
    // Default: medium priority
    return RpcMethodPriority::Medium;
}

/**
 * @brief Generate unique request ID
 * 
 * Thread-safe atomic counter for request identification.
 */
inline int64_t GenerateRequestId() {
    static std::atomic<int64_t> s_request_counter{0};
    return s_request_counter.fetch_add(1, std::memory_order_relaxed);
}

} // namespace node

#endif // BITCOIN_NODE_STDIO_BUS_HOOKS_H
