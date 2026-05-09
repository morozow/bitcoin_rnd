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

/** Message received event (1:1 with net:inbound_message USDT tracepoint) */
struct MessageEvent {
    int64_t peer_id;
    std::string addr;       // peer m_addr_name (matches USDT arg2)
    std::string conn_type;  // peer ConnectionTypeAsString (matches USDT arg3)
    std::string msg_type;   // Owning copy for async safety (USDT arg4)
    size_t size_bytes;      // USDT arg5
    int64_t received_us;    // Monotonic timestamp in microseconds
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
// Phase 2: Block Processing Delay Diagnostic Events (#21803)
// ============================================================================

/** Block announcement source */
enum class BlockAnnounceVia {
    Headers = 0,
    CompactBlock = 1,
    Inv = 2
};

/** Block announce event - when we learn about a new block */
struct BlockAnnounceEvent {
    uint256 hash;
    int64_t peer_id;
    BlockAnnounceVia via;
    int64_t chainwork_delta;  // Relative to our tip
    int height;
    int64_t timestamp_us;
};

/** Block request decision reason */
enum class BlockRequestReason {
    NewBlock = 0,           // First request for this block
    Retry = 1,              // Retry after timeout
    Hedge = 2,              // Hedging request to additional peer
    CompactFallback = 3,    // Fallback from compact block
    ParallelDownload = 4    // Parallel download slot
};

/** Block request decision event - when we decide to request a block */
struct BlockRequestDecisionEvent {
    uint256 hash;
    int64_t peer_id;
    BlockRequestReason reason;
    bool is_preferred_peer;
    bool first_in_flight;
    size_t already_in_flight;
    bool can_direct_fetch;
    bool is_limited_peer;
    int64_t timestamp_us;
};

/** Block in-flight change action */
enum class InFlightAction {
    Add = 0,
    Remove = 1,
    Timeout = 2
};

/** Block in-flight state change event */
struct BlockInFlightEvent {
    uint256 hash;
    int64_t peer_id;
    InFlightAction action;
    size_t inflight_count;      // Total in-flight for this block
    size_t peer_inflight_count; // In-flight for this peer
    int64_t timestamp_us;
};

/** Staller detected event - when download window is blocked */
struct StallerDetectedEvent {
    uint256 hash;
    int64_t staller_peer_id;
    int64_t waiting_peer_id;
    int window_end_height;
    int64_t stall_duration_us;
    int64_t timestamp_us;
};

/** Compact block decision action */
enum class CompactBlockAction {
    Reconstruct = 0,    // Successfully reconstructed from mempool
    GetBlockTxn = 1,    // Requesting missing transactions
    GetData = 2,        // Falling back to full block
    Wait = 3,           // Waiting for other peer
    Drop = 4            // Dropping (already have or invalid)
};

/** Compact block decision event */
struct CompactBlockDecisionEvent {
    uint256 hash;
    int64_t peer_id;
    CompactBlockAction action;
    size_t missing_tx_count;    // Transactions not in mempool
    bool first_in_flight;
    bool is_highbandwidth;
    int64_t timestamp_us;
};

/** Block source resolved event - when we finally get the block */
struct BlockSourceResolvedEvent {
    uint256 hash;
    int64_t source_peer_id;     // Peer that provided the block
    int64_t first_requested_peer_id;  // First peer we requested from
    int64_t announce_to_receive_us;   // Time from first announce to receive
    int64_t request_to_receive_us;    // Time from first request to receive
    size_t total_requests;      // Total requests made for this block
    int64_t timestamp_us;
};

// ============================================================================
// Additional events for full eBPF tracepoint coverage
// ============================================================================

/** Transaction removed from mempool (mempool:removed tracepoint equivalent) */
struct TxRemovedEvent {
    uint256 txid;
    std::string reason;
    size_t vsize;
    int64_t fee;
    int64_t entry_time;
    int64_t timestamp_us;
};

/** Transaction replaced in mempool (mempool:replaced tracepoint equivalent) */
struct TxReplacedEvent {
    uint256 replaced_txid;
    size_t replaced_vsize;
    int64_t replaced_fee;
    int64_t replaced_entry_time;
    uint256 replacement_txid;
    size_t replacement_vsize;
    int64_t replacement_fee;
    int64_t timestamp_us;
};

/** Transaction rejected from mempool (mempool:rejected tracepoint equivalent) */
struct TxRejectedEvent {
    uint256 txid;
    std::string reason;
    int64_t timestamp_us;
};

/** UTXO cache flush event (utxocache:flush tracepoint equivalent) */
struct UTXOCacheFlushEvent {
    int64_t duration_us;
    int mode;
    int64_t coins_count;
    int64_t coins_mem_usage;
    bool is_flush_for_prune;
    int64_t timestamp_us;
};

/** P2P connection event (net:inbound_connection / net:outbound_connection equivalent) */
struct PeerConnectionEvent {
    int64_t peer_id;
    std::string addr;
    std::string conn_type;
    int network;
    bool inbound;
    uint64_t existing_connections;  // total_in or total_out as appropriate
    int64_t timestamp_us;
};

/** P2P closed connection event (net:closed_connection tracepoint equivalent) */
struct PeerClosedEvent {
    int64_t peer_id;
    std::string addr;
    std::string conn_type;
    int network;
    int64_t time_established; // seconds (from std::chrono::seconds)
    int64_t timestamp_us;
};

/** P2P evicted inbound connection event (net:evicted_inbound_connection tracepoint equivalent) */
struct PeerEvictedEvent {
    int64_t peer_id;
    std::string addr;
    std::string conn_type;
    int network;
    int64_t time_established; // seconds
    int64_t timestamp_us;
};

/** P2P misbehaving connection event (net:misbehaving_connection tracepoint equivalent) */
struct PeerMisbehavingEvent {
    int64_t peer_id;
    std::string message;
    int64_t timestamp_us;
};

/** P2P outbound message event (net:outbound_message tracepoint equivalent) */
struct OutboundMessageEvent {
    int64_t peer_id;
    std::string addr;
    std::string conn_type;
    std::string msg_type;
    size_t size_bytes;
    int64_t timestamp_us;
};

/** Mempool added event (mempool:added tracepoint equivalent).
 *  Separate from TxAdmissionEvent so the USDT-mirror path is 1:1 with USDT. */
struct MempoolAddedEvent {
    uint256 txid;
    size_t vsize;
    int64_t fee;
    int64_t timestamp_us;
};

/** Block connected event (validation:block_connected tracepoint equivalent). */
struct BlockConnectedEvent {
    uint256 hash;
    int height;
    size_t tx_count;
    int64_t inputs_count;
    int64_t sigops_cost;
    int64_t duration_ns;
    int64_t timestamp_us;
};

/** UTXO cache add event (utxocache:add tracepoint equivalent) */
struct UTXOCacheAddEvent {
    uint256 txid;
    uint32_t vout;
    uint32_t height;
    int64_t value;
    bool is_coinbase;
    int64_t timestamp_us;
};

/** UTXO cache spent event (utxocache:spent tracepoint equivalent) */
struct UTXOCacheSpentEvent {
    uint256 txid;
    uint32_t vout;
    uint32_t height;
    int64_t value;
    bool is_coinbase;
    int64_t timestamp_us;
};

/** UTXO cache uncache event (utxocache:uncache tracepoint equivalent) */
struct UTXOCacheUncacheEvent {
    uint256 txid;
    uint32_t vout;
    uint32_t height;
    int64_t value;
    bool is_coinbase;
    int64_t timestamp_us;
};

/** Coin selection: selected_coins event (coin_selection:selected_coins tracepoint) */
struct CoinSelectionSelectedCoinsEvent {
    std::string wallet_name;
    std::string algorithm;
    int64_t target;
    int64_t waste;
    int64_t selected_value;
    int64_t timestamp_us;
};

/** Coin selection: normal_create_tx_internal (coin_selection:normal_create_tx_internal tracepoint) */
struct CoinSelectionNormalCreateTxEvent {
    std::string wallet_name;
    bool success;
    int64_t fee;
    int32_t change_pos;
    int64_t timestamp_us;
};

/** Coin selection: attempting_aps_create_tx (coin_selection:attempting_aps_create_tx tracepoint) */
struct CoinSelectionAttemptingApsEvent {
    std::string wallet_name;
    int64_t timestamp_us;
};

/** Coin selection: aps_create_tx_internal (coin_selection:aps_create_tx_internal tracepoint) */
struct CoinSelectionApsCreateTxEvent {
    std::string wallet_name;
    bool use_aps;
    bool success;
    int64_t fee;
    int32_t change_pos;
    int64_t timestamp_us;
};

/**
 * @brief stdio_bus mode enum
 */
enum class StdioBusMode {
    Off = 0,      ///< Disabled (default)
    Shadow = 1,   ///< Observe only via stdio_bus protocol, no behavior change
    Active = 2,   ///< Enable optimizations (future)
    RawPipe = 3   ///< Raw Unix pipe IPC (no stdio_bus library, same workers)
};

/**
 * @brief Parse stdio_bus mode from string
 * @param str Mode string ("off", "shadow", "active", "raw_pipe")
 * @return Parsed mode, or Off if invalid
 */
inline StdioBusMode ParseStdioBusMode(std::string_view str) {
    if (str == "shadow") return StdioBusMode::Shadow;
    if (str == "active") return StdioBusMode::Active;
    if (str == "raw_pipe") return StdioBusMode::RawPipe;
    return StdioBusMode::Off;
}

/**
 * @brief Convert stdio_bus mode to string
 */
inline std::string_view StdioBusModeToString(StdioBusMode mode) {
    switch (mode) {
        case StdioBusMode::Shadow: return "shadow";
        case StdioBusMode::Active: return "active";
        case StdioBusMode::RawPipe: return "raw_pipe";
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

    // ========== Phase 2: Block Processing Delay Events (#21803) ==========

    /** Called when a new block is announced */
    virtual void OnBlockAnnounce(const BlockAnnounceEvent& event) = 0;

    /** Called when a block request decision is made */
    virtual void OnBlockRequestDecision(const BlockRequestDecisionEvent& event) = 0;

    /** Called when block in-flight state changes */
    virtual void OnBlockInFlight(const BlockInFlightEvent& event) = 0;

    /** Called when a staller is detected in download window */
    virtual void OnStallerDetected(const StallerDetectedEvent& event) = 0;

    /** Called when compact block processing decision is made */
    virtual void OnCompactBlockDecision(const CompactBlockDecisionEvent& event) = 0;

    /** Called when block source is resolved (block received) */
    virtual void OnBlockSourceResolved(const BlockSourceResolvedEvent& event) = 0;

    // Additional hooks for full eBPF tracepoint coverage
    virtual void OnTxRemoved(const TxRemovedEvent& event) = 0;
    virtual void OnTxReplaced(const TxReplacedEvent& event) = 0;
    virtual void OnTxRejected(const TxRejectedEvent& event) = 0;
    virtual void OnUTXOCacheFlush(const UTXOCacheFlushEvent& event) = 0;
    virtual void OnPeerConnection(const PeerConnectionEvent& event) = 0;

    // ========== Full USDT tracepoint parity ==========

    /** Called when peer connection is closed (net:closed_connection) */
    virtual void OnPeerClosed(const PeerClosedEvent& event) = 0;

    /** Called when inbound peer is evicted (net:evicted_inbound_connection) */
    virtual void OnPeerEvicted(const PeerEvictedEvent& event) = 0;

    /** Called when a peer is marked misbehaving (net:misbehaving_connection) */
    virtual void OnPeerMisbehaving(const PeerMisbehavingEvent& event) = 0;

    /** Called when an outbound P2P message is sent (net:outbound_message) */
    virtual void OnOutboundMessage(const OutboundMessageEvent& event) = 0;

    /** Called on successful mempool acceptance (mempool:added) */
    virtual void OnMempoolAdded(const MempoolAddedEvent& event) = 0;

    /** Called after a block is connected (validation:block_connected) */
    virtual void OnBlockConnected(const BlockConnectedEvent& event) = 0;

    /** Called when a coin is added to UTXO cache (utxocache:add) */
    virtual void OnUTXOCacheAdd(const UTXOCacheAddEvent& event) = 0;

    /** Called when a coin is spent in UTXO cache (utxocache:spent) */
    virtual void OnUTXOCacheSpent(const UTXOCacheSpentEvent& event) = 0;

    /** Called when a coin is uncached from UTXO cache (utxocache:uncache) */
    virtual void OnUTXOCacheUncache(const UTXOCacheUncacheEvent& event) = 0;

    /** Called when wallet selects coins (coin_selection:selected_coins) */
    virtual void OnCoinSelectionSelectedCoins(const CoinSelectionSelectedCoinsEvent& event) = 0;

    /** Called after normal create tx (coin_selection:normal_create_tx_internal) */
    virtual void OnCoinSelectionNormalCreateTx(const CoinSelectionNormalCreateTxEvent& event) = 0;

    /** Called when wallet attempts APS variant (coin_selection:attempting_aps_create_tx) */
    virtual void OnCoinSelectionAttemptingAps(const CoinSelectionAttemptingApsEvent& event) = 0;

    /** Called after APS create tx (coin_selection:aps_create_tx_internal) */
    virtual void OnCoinSelectionApsCreateTx(const CoinSelectionApsCreateTxEvent& event) = 0;
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
    
    // Phase 2: Block Processing Delay Events
    void OnBlockAnnounce(const BlockAnnounceEvent&) override {}
    void OnBlockRequestDecision(const BlockRequestDecisionEvent&) override {}
    void OnBlockInFlight(const BlockInFlightEvent&) override {}
    void OnStallerDetected(const StallerDetectedEvent&) override {}
    void OnCompactBlockDecision(const CompactBlockDecisionEvent&) override {}
    void OnBlockSourceResolved(const BlockSourceResolvedEvent&) override {}
    void OnTxRemoved(const TxRemovedEvent&) override {}
    void OnTxReplaced(const TxReplacedEvent&) override {}
    void OnTxRejected(const TxRejectedEvent&) override {}
    void OnUTXOCacheFlush(const UTXOCacheFlushEvent&) override {}
    void OnPeerConnection(const PeerConnectionEvent&) override {}

    // Full USDT tracepoint parity
    void OnPeerClosed(const PeerClosedEvent&) override {}
    void OnPeerEvicted(const PeerEvictedEvent&) override {}
    void OnPeerMisbehaving(const PeerMisbehavingEvent&) override {}
    void OnOutboundMessage(const OutboundMessageEvent&) override {}
    void OnMempoolAdded(const MempoolAddedEvent&) override {}
    void OnBlockConnected(const BlockConnectedEvent&) override {}
    void OnUTXOCacheAdd(const UTXOCacheAddEvent&) override {}
    void OnUTXOCacheSpent(const UTXOCacheSpentEvent&) override {}
    void OnUTXOCacheUncache(const UTXOCacheUncacheEvent&) override {}
    void OnCoinSelectionSelectedCoins(const CoinSelectionSelectedCoinsEvent&) override {}
    void OnCoinSelectionNormalCreateTx(const CoinSelectionNormalCreateTxEvent&) override {}
    void OnCoinSelectionAttemptingAps(const CoinSelectionAttemptingApsEvent&) override {}
    void OnCoinSelectionApsCreateTx(const CoinSelectionApsCreateTxEvent&) override {}
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

// ============================================================================
// Global hooks accessor
// ============================================================================
//
// For tracepoints that fire from code outside of PeerManager (net.cpp,
// validation.cpp, coins.cpp, wallet/spend.cpp, etc.), there is no natural
// dependency-injection path to pass the StdioBusHooks pointer. We therefore
// provide a tiny global accessor, following the same pattern as the USDT
// semaphores themselves (which are also global).
//
// The accessor is read-mostly and lock-free after init: the pointer is
// installed once during startup (AppInitMain) and cleared during shutdown.
//
// All callers MUST check `hooks && hooks->Enabled()` before constructing
// event structs, to keep the USDT-off code path allocation-free.

/** Install the global stdio_bus hooks instance (called once during init). */
void SetGlobalStdioBusHooks(std::shared_ptr<StdioBusHooks> hooks);

/** Get the global stdio_bus hooks instance. Returns nullptr if not installed.
 *  Safe to call from any thread; returns a snapshot shared_ptr. */
std::shared_ptr<StdioBusHooks> GetGlobalStdioBusHooks();

} // namespace node

#endif // BITCOIN_NODE_STDIO_BUS_HOOKS_H
