// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_NODE_STDIO_BUS_HOOKS_H
#define BITCOIN_NODE_STDIO_BUS_HOOKS_H

#include <cstdint>
#include <string>
#include <string_view>
#include <chrono>
#include <functional>
#include <memory>

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
// Phase 3: Message Handler Saturation Diagnostic Events (#27623)
// ============================================================================

/** Message priority for backpressure scheduling */
enum class MsgPriority : uint8_t {
    High = 0,    // Consensus-critical: BLOCK, HEADERS, TX, etc.
    Medium = 1,  // Control-plane: VERSION, PING, PONG, etc.
    Low = 2      // Gossip/deferrable: ADDR, INV, etc.
};

/** Backpressure decision */
enum class BackpressureDecision : uint8_t {
    Admit = 0,      // Process normally
    Defer = 1,      // Keep queued, revisit later
    DropLowPri = 2  // Drop (only for Low priority)
};

/** Processing stage for timing */
enum class MsgProcStage : uint8_t {
    Precheck = 0,  // Initial validation before heavy parsing
    Parse = 1,     // Deserialization
    Process = 2    // Business logic
};

/** Message poll event - what was retrieved from peer's receive queue */
struct MsgProcPollEvent {
    int64_t peer_id;
    std::string msg_type;       // Owning copy for async safety
    size_t msg_size_bytes;
    bool poll_more_work;        // More messages available
    size_t recv_queue_msgs;     // Messages remaining in queue
    size_t recv_queue_bytes;    // Bytes remaining in queue
    int64_t timestamp_us;
};

/** Message processing stage timing event */
struct MsgProcStageEvent {
    int64_t peer_id;
    std::string msg_type;       // Owning copy for async safety
    MsgProcStage stage;
    int64_t start_us;
    int64_t end_us;
    bool success;
};

/** Backpressure decision event */
struct MsgProcBackpressureEvent {
    int64_t peer_id;
    std::string msg_type;       // Owning copy for async safety
    MsgPriority priority;
    BackpressureDecision decision;
    std::string reason;         // Owning copy: "budget_exhausted", "queue_high_watermark", etc.
    int64_t timestamp_us;
    
    // Load snapshots
    size_t recv_queue_msgs;
    size_t recv_queue_bytes;
    size_t global_inflight_blocks;
    
    // Budget snapshot
    int64_t loop_budget_parse_us_left;
    int32_t loop_budget_heavy_msgs_left;
    int32_t peer_heavy_msgs_processed;
    int32_t max_peer_heavy_msgs_per_loop;
};

/** Message drop event (only for low-priority under pressure) */
struct MsgProcDropEvent {
    int64_t peer_id;
    std::string msg_type;       // Owning copy for async safety
    std::string reason;         // Owning copy
    size_t dropped_count;       // Cumulative drops this loop
    int64_t timestamp_us;
};

/** Extended message handler loop event with saturation metrics */
struct MsgProcLoopEvent {
    int64_t iteration;
    int64_t start_us;
    int64_t end_us;
    int32_t peers_scanned;
    int32_t msgs_processed;
    int32_t msgs_deferred;
    int32_t msgs_dropped;
    bool had_work;
    
    // Budget consumption
    int64_t parse_us_consumed;
    int32_t heavy_msgs_consumed;
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

    // ========== Phase 3: Message Handler Saturation Events (#27623) ==========

    /** Called when a message is polled from peer's receive queue */
    virtual void OnMsgProcPoll(const MsgProcPollEvent& event) = 0;

    /** Called for each processing stage of a message */
    virtual void OnMsgProcStage(const MsgProcStageEvent& event) = 0;

    /** Called when backpressure decision is made */
    virtual void OnMsgProcBackpressure(const MsgProcBackpressureEvent& event) = 0;

    /** Called when a low-priority message is dropped */
    virtual void OnMsgProcDrop(const MsgProcDropEvent& event) = 0;

    /** Called at end of message processing loop with extended metrics */
    virtual void OnMsgProcLoop(const MsgProcLoopEvent& event) = 0;
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
    
    // Phase 3: Message Handler Saturation Events
    void OnMsgProcPoll(const MsgProcPollEvent&) override {}
    void OnMsgProcStage(const MsgProcStageEvent&) override {}
    void OnMsgProcBackpressure(const MsgProcBackpressureEvent&) override {}
    void OnMsgProcDrop(const MsgProcDropEvent&) override {}
    void OnMsgProcLoop(const MsgProcLoopEvent&) override {}
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

} // namespace node

#endif // BITCOIN_NODE_STDIO_BUS_HOOKS_H
