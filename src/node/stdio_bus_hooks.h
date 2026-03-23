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
// Phase 4: Mempool Redesign Preparation Events (#27677)
// ============================================================================

/** Source of transaction admission */
enum class TxAdmissionSource : uint8_t {
    P2P = 0,      // Received from peer
    RPC = 1,      // Submitted via RPC
    Reorg = 2,    // Re-added after reorg
    Package = 3,  // Part of package submission
    Wallet = 4    // From wallet
};

/** Result of mempool admission attempt */
enum class MempoolAdmissionResult : uint8_t {
    Accepted = 0,           // Successfully added to mempool
    Rejected = 1,           // Rejected (policy or consensus)
    MempoolEntry = 2,       // Already in mempool
    DifferentWitness = 3,   // Same txid, different witness
    PackageRejected = 4     // Rejected as part of package
};

/** Mempool batch operation type */
enum class MempoolBatchType : uint8_t {
    ChangesetApply = 0,   // Apply changeset from validation
    ReorgUpdate = 1,      // Update after reorg
    Trim = 2,             // Size limit trim
    Expire = 3,           // Expiry cleanup
    BlockConnect = 4      // Block connected, remove confirmed
};

/** Mempool ordering phase */
enum class MempoolOrderingPhase : uint8_t {
    TxGraphDoWork = 0,        // TxGraph work processing
    TrimWorstChunk = 1,       // Trim worst feerate chunk
    ClusterLinearization = 2  // Cluster linearization
};

/** Mempool eviction reason */
enum class MempoolEvictionReason : uint8_t {
    SizeLimit = 0,    // Mempool size limit
    Expiry = 1,       // Transaction expired
    Reorg = 2,        // Removed during reorg
    Replaced = 3,     // Replaced by RBF
    Conflict = 4,     // Conflicting transaction
    BlockConfirm = 5  // Confirmed in block
};

/** Package ordering strategy for comparison */
enum class PackageOrderingStrategy : uint8_t {
    Arrival = 0,        // Process in arrival order
    AncestorFirst = 1,  // Process ancestors before descendants
    FeerateFirst = 2,   // Process by feerate descending
    ClusterAware = 3    // Cluster-aware ordering
};

/** Mempool admission attempt event - fired at entry to AcceptToMemoryPool */
struct MempoolAdmissionAttemptEvent {
    uint256 txid;
    uint256 wtxid;
    TxAdmissionSource source;
    int32_t vsize;
    int64_t fee_sat;
    int64_t timestamp_us;
};

/** Mempool admission result event - fired at exit from AcceptToMemoryPool */
struct MempoolAdmissionResultEvent {
    uint256 txid;
    uint256 wtxid;
    MempoolAdmissionResult result;
    int32_t reject_code;              // 0 if accepted
    std::string reject_reason;        // Empty if accepted
    int32_t replaced_count;           // Number of replaced transactions
    int64_t effective_feerate_sat_vb; // Effective feerate in sat/vB * 1000
    int64_t start_us;
    int64_t end_us;
};

/** Package admission event - for ProcessNewPackage */
struct PackageAdmissionEvent {
    uint256 package_hash;             // Hash of sorted txids
    PackageOrderingStrategy strategy;
    int32_t tx_count;
    int32_t total_vsize;
    int64_t total_fees_sat;
    int32_t accepted_count;
    int32_t rejected_count;
    int64_t start_us;
    int64_t end_us;
};

/** Mempool batch operation event */
struct MempoolBatchEvent {
    MempoolBatchType batch_type;
    int32_t tx_count_in;
    int32_t tx_count_out;
    int64_t bytes_affected;
    int64_t start_us;
    int64_t end_us;
};

/** Mempool ordering/work event */
struct MempoolOrderingEvent {
    MempoolOrderingPhase phase;
    int32_t candidate_count;
    int32_t cluster_count;
    int64_t work_budget;
    int64_t work_used;
    int64_t start_us;
    int64_t end_us;
};

/** Mempool lock contention event */
struct MempoolLockContentionEvent {
    std::string lock_name;            // "mempool.cs", "cs_main"
    std::string context;              // "atmp", "package", "trim", "reorg"
    int64_t wait_us;                  // Time waiting for lock
    int64_t hold_us;                  // Time holding lock
    int64_t timestamp_us;
};

/** Mempool eviction event */
struct MempoolEvictionEvent {
    MempoolEvictionReason reason;
    int32_t tx_count;
    int64_t bytes_removed;
    int64_t fees_removed_sat;
    int64_t timestamp_us;
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

    // ========== Phase 4: Mempool Events (#27677) ==========

    /** Called at entry to AcceptToMemoryPool */
    virtual void OnMempoolAdmissionAttempt(const MempoolAdmissionAttemptEvent& event) = 0;

    /** Called at exit from AcceptToMemoryPool */
    virtual void OnMempoolAdmissionResult(const MempoolAdmissionResultEvent& event) = 0;

    /** Called for package admission (ProcessNewPackage) */
    virtual void OnPackageAdmission(const PackageAdmissionEvent& event) = 0;

    /** Called for mempool batch operations */
    virtual void OnMempoolBatch(const MempoolBatchEvent& event) = 0;

    /** Called for mempool ordering/work operations */
    virtual void OnMempoolOrdering(const MempoolOrderingEvent& event) = 0;

    /** Called when lock contention is detected */
    virtual void OnMempoolLockContention(const MempoolLockContentionEvent& event) = 0;

    /** Called when transactions are evicted from mempool */
    virtual void OnMempoolEviction(const MempoolEvictionEvent& event) = 0;
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
    
    // Phase 4: Mempool Events
    void OnMempoolAdmissionAttempt(const MempoolAdmissionAttemptEvent&) override {}
    void OnMempoolAdmissionResult(const MempoolAdmissionResultEvent&) override {}
    void OnPackageAdmission(const PackageAdmissionEvent&) override {}
    void OnMempoolBatch(const MempoolBatchEvent&) override {}
    void OnMempoolOrdering(const MempoolOrderingEvent&) override {}
    void OnMempoolLockContention(const MempoolLockContentionEvent&) override {}
    void OnMempoolEviction(const MempoolEvictionEvent&) override {}
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
