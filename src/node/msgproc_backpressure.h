// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_NODE_MSGPROC_BACKPRESSURE_H
#define BITCOIN_NODE_MSGPROC_BACKPRESSURE_H

#include <node/stdio_bus_hooks.h>
#include <protocol.h>

#include <algorithm>
#include <cstdint>
#include <string_view>

namespace node {

/**
 * @brief Per-loop budget for message processing
 * 
 * Reset at the start of each ThreadMessageHandler loop iteration.
 * Used to prevent any single loop from consuming too much CPU.
 */
struct MsgProcLoopBudget {
    int64_t parse_us_left{2'000};           // Total parse-time budget per loop (2ms)
    int32_t heavy_msgs_left{8};             // Total heavy messages per loop
    int32_t max_peer_heavy_per_loop{2};     // Fairness cap per peer
    size_t queue_high_watermark_msgs{256};  // Soft pressure threshold (messages)
    size_t queue_high_watermark_bytes{8 * 1024 * 1024}; // Soft pressure threshold (8 MiB)
    
    // Consumption tracking
    int64_t parse_us_consumed{0};
    int32_t heavy_msgs_consumed{0};
    int32_t msgs_deferred{0};
    int32_t msgs_dropped{0};
    
    void Reset() {
        parse_us_left = 2'000;
        heavy_msgs_left = 8;
        parse_us_consumed = 0;
        heavy_msgs_consumed = 0;
        msgs_deferred = 0;
        msgs_dropped = 0;
    }
    
    void ConsumeHeavyMsg(int64_t parse_us) {
        parse_us_consumed += parse_us;
        parse_us_left = std::max<int64_t>(0, parse_us_left - parse_us);
        heavy_msgs_consumed++;
        heavy_msgs_left = std::max<int32_t>(0, heavy_msgs_left - 1);
    }
};

/**
 * @brief Per-peer counters for current loop iteration
 * 
 * Used to enforce fairness - no single peer should monopolize the loop.
 */
struct MsgProcPeerLoopState {
    int32_t heavy_msgs_processed{0};
    
    void Reset() {
        heavy_msgs_processed = 0;
    }
};

/**
 * @brief Classify P2P message priority for backpressure scheduling
 * 
 * HIGH: Consensus/chain-progress critical - never drop
 * MEDIUM: Control-plane - defer under pressure
 * LOW: Gossip/deferrable - may drop under heavy pressure
 */
[[nodiscard]] inline MsgPriority ClassifyMsgPriority(std::string_view msg_type, size_t msg_size_bytes) noexcept
{
    // Consensus/chain-progress critical - HIGH priority
    if (msg_type == NetMsgType::BLOCK ||
        msg_type == NetMsgType::CMPCTBLOCK ||
        msg_type == NetMsgType::BLOCKTXN ||
        msg_type == NetMsgType::HEADERS ||
        msg_type == NetMsgType::TX ||
        msg_type == NetMsgType::GETDATA ||
        msg_type == NetMsgType::GETBLOCKS ||
        msg_type == NetMsgType::GETHEADERS) {
        return MsgPriority::High;
    }

    // Control-plane - MEDIUM priority
    if (msg_type == NetMsgType::VERSION ||
        msg_type == NetMsgType::VERACK ||
        msg_type == NetMsgType::SENDHEADERS ||
        msg_type == NetMsgType::SENDCMPCT ||
        msg_type == NetMsgType::PING ||
        msg_type == NetMsgType::PONG ||
        msg_type == NetMsgType::FEEFILTER ||
        msg_type == NetMsgType::WTXIDRELAY ||
        msg_type == NetMsgType::SENDADDRV2) {
        return MsgPriority::Medium;
    }

    // Gossip-ish / deferrable - LOW priority
    if (msg_type == NetMsgType::ADDR ||
        msg_type == NetMsgType::ADDRV2 ||
        msg_type == NetMsgType::INV ||
        msg_type == NetMsgType::GETADDR ||
        msg_type == NetMsgType::NOTFOUND ||
        msg_type == NetMsgType::MEMPOOL) {
        return MsgPriority::Low;
    }

    // Unknown / other: very large unknown payloads -> MEDIUM, else LOW
    return msg_size_bytes > 64 * 1024 ? MsgPriority::Medium : MsgPriority::Low;
}

/**
 * @brief Check if message type requires heavy parsing
 * 
 * Heavy messages consume significant CPU for deserialization.
 */
[[nodiscard]] inline bool IsHeavyMsgType(std::string_view msg_type, size_t msg_size_bytes) noexcept
{
    if (msg_type == NetMsgType::BLOCK ||
        msg_type == NetMsgType::CMPCTBLOCK ||
        msg_type == NetMsgType::BLOCKTXN) {
        return true;
    }
    // Large headers batches can be heavy too
    if (msg_type == NetMsgType::HEADERS) {
        return msg_size_bytes > 128 * 1024;
    }
    return false;
}

/**
 * @brief Result of backpressure decision
 */
struct DeferResult {
    bool defer{false};      // Keep queued, revisit later
    bool drop{false};       // Only for low-priority under pressure
    const char* reason{"admit"};
};

/**
 * @brief Backpressure decision helper
 * 
 * IMPORTANT INVARIANTS:
 * - Never drop HIGH priority messages
 * - Prefer DEFER for HIGH/MEDIUM
 * - DROP only LOW priority and only under explicit queue pressure
 * - No consensus changes - only scheduling/admission
 * 
 * @param msg_type Message type string
 * @param msg_size_bytes Message size in bytes
 * @param recv_queue_msgs Messages in peer's receive queue
 * @param recv_queue_bytes Bytes in peer's receive queue
 * @param budget Current loop budget
 * @param peer_state Current peer's loop state
 * @param backpressure_enabled Whether backpressure is enabled
 * @return DeferResult with decision
 */
[[nodiscard]] inline DeferResult ShouldDeferMessage(
    std::string_view msg_type,
    size_t msg_size_bytes,
    size_t recv_queue_msgs,
    size_t recv_queue_bytes,
    const MsgProcLoopBudget& budget,
    const MsgProcPeerLoopState& peer_state,
    bool backpressure_enabled) noexcept
{
    if (!backpressure_enabled) return {};
    
    const MsgPriority prio = ClassifyMsgPriority(msg_type, msg_size_bytes);
    const bool heavy = IsHeavyMsgType(msg_type, msg_size_bytes);
    
    // Queue pressure check
    const bool queue_pressure =
        recv_queue_msgs >= budget.queue_high_watermark_msgs ||
        recv_queue_bytes >= budget.queue_high_watermark_bytes;
    
    // Under queue pressure, drop LOW priority
    if (queue_pressure && prio == MsgPriority::Low) {
        return {.defer = false, .drop = true, .reason = "queue_high_watermark"};
    }

    // Fairness cap: one peer must not monopolize heavy parsing in a loop
    if (heavy && peer_state.heavy_msgs_processed >= budget.max_peer_heavy_per_loop) {
        // HIGH/MEDIUM -> defer; LOW already handled by queue pressure path
        return {.defer = true, .drop = false, .reason = "peer_heavy_cap"};
    }

    // Global loop budget exhaustion
    if (heavy && budget.heavy_msgs_left <= 0) {
        if (prio == MsgPriority::Low) {
            return {.defer = false, .drop = true, .reason = "heavy_budget_exhausted"};
        }
        return {.defer = true, .drop = false, .reason = "heavy_budget_exhausted"};
    }

    if (heavy && budget.parse_us_left <= 0) {
        if (prio == MsgPriority::Low) {
            return {.defer = false, .drop = true, .reason = "parse_budget_exhausted"};
        }
        return {.defer = true, .drop = false, .reason = "parse_budget_exhausted"};
    }

    return {};
}

} // namespace node

#endif // BITCOIN_NODE_MSGPROC_BACKPRESSURE_H
