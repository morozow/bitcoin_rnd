// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_NODE_STDIO_BUS_SDK_HOOKS_H
#define BITCOIN_NODE_STDIO_BUS_SDK_HOOKS_H

#include <node/stdio_bus_hooks.h>

#include <atomic>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <variant>

namespace node {

/**
 * @brief Statistics for StdioBusSdkHooks
 */
struct StdioBusStats {
    std::atomic<uint64_t> events_total{0};
    std::atomic<uint64_t> events_dropped{0};
    std::atomic<uint64_t> events_sent{0};
    std::atomic<uint64_t> errors{0};
    std::atomic<int64_t> last_hook_latency_us{0};
    std::atomic<size_t> queue_depth{0};
};

/**
 * @brief Real implementation of StdioBusHooks using stdio_bus SDK
 * 
 * This implementation:
 * - Uses a bounded async queue to avoid blocking the hot path
 * - Drops events when queue is full (fail-open)
 * - Runs a background worker thread for SDK I/O
 * - Serializes events to JSON-RPC format
 * - Tracks statistics for monitoring
 * 
 * Thread safety: All public methods are thread-safe.
 */
class StdioBusSdkHooks final : public StdioBusHooks {
public:
    /**
     * @brief Configuration for StdioBusSdkHooks
     */
    struct Config {
        std::string config_path;      ///< Path to stdio_bus config file
        size_t queue_capacity{4096};  ///< Max events in queue before dropping
        bool shadow_mode{true};       ///< Shadow mode (observe only)
    };

    explicit StdioBusSdkHooks(Config config);
    ~StdioBusSdkHooks() override;

    // Non-copyable, non-movable
    StdioBusSdkHooks(const StdioBusSdkHooks&) = delete;
    StdioBusSdkHooks& operator=(const StdioBusSdkHooks&) = delete;

    // ========== StdioBusHooks interface ==========
    
    bool Enabled() const override { return m_enabled.load(std::memory_order_relaxed); }
    bool ShadowMode() const override { return m_shadow_mode; }

    void OnMessage(const MessageEvent& ev) override;
    void OnHeaders(const HeadersEvent& ev) override;
    void OnBlockReceived(const BlockReceivedEvent& ev) override;
    void OnBlockValidated(const BlockValidatedEvent& ev) override;
    void OnTxAdmission(const TxAdmissionEvent& ev) override;
    void OnMsgHandlerLoop(const MsgHandlerLoopEvent& ev) override;
    void OnRpcCall(const RpcCallEvent& ev) override;

    // Phase 4: Mempool Events
    void OnMempoolAdmissionAttempt(const MempoolAdmissionAttemptEvent& ev) override;
    void OnMempoolAdmissionResult(const MempoolAdmissionResultEvent& ev) override;
    void OnPackageAdmission(const PackageAdmissionEvent& ev) override;
    void OnMempoolBatch(const MempoolBatchEvent& ev) override;
    void OnMempoolOrdering(const MempoolOrderingEvent& ev) override;
    void OnMempoolLockContention(const MempoolLockContentionEvent& ev) override;
    void OnMempoolEviction(const MempoolEvictionEvent& ev) override;

    // ========== Lifecycle ==========

    /** Start the background worker and SDK connection */
    bool Start();

    /** Stop the background worker gracefully */
    void Stop();

    /** Check if running */
    bool IsRunning() const { return m_running.load(std::memory_order_relaxed); }

    // ========== Statistics ==========

    /** Get current statistics (thread-safe snapshot) */
    StdioBusStats GetStats() const;

    /** Reset statistics counters */
    void ResetStats();

private:
    // Event variant for queue
    using Event = std::variant<
        MessageEvent,
        HeadersEvent,
        BlockReceivedEvent,
        BlockValidatedEvent,
        TxAdmissionEvent,
        MsgHandlerLoopEvent,
        RpcCallEvent,
        // Phase 4: Mempool Events
        MempoolAdmissionAttemptEvent,
        MempoolAdmissionResultEvent,
        PackageAdmissionEvent,
        MempoolBatchEvent,
        MempoolOrderingEvent,
        MempoolLockContentionEvent,
        MempoolEvictionEvent
    >;

    /** Try to enqueue an event (non-blocking) */
    bool TryEnqueue(Event ev);

    /** Background worker thread function */
    void WorkerLoop();

    /** Serialize event to JSON string */
    std::string SerializeEvent(const Event& ev) const;

    /** Send serialized event via SDK */
    bool SendToSdk(const std::string& json);

    // Configuration
    Config m_config;
    bool m_shadow_mode;

    // State
    std::atomic<bool> m_enabled{false};
    std::atomic<bool> m_running{false};
    std::atomic<bool> m_stop_requested{false};

    // Bounded queue with mutex (simple implementation)
    // For production, consider lock-free SPSC/MPSC queue
    mutable std::mutex m_queue_mutex;
    std::condition_variable m_queue_cv;
    std::queue<Event> m_queue;
    size_t m_queue_capacity;

    // Background worker
    std::thread m_worker_thread;

    // Statistics
    mutable StdioBusStats m_stats;

    // SDK handle (opaque, managed by implementation)
    struct SdkImpl;
    std::unique_ptr<SdkImpl> m_sdk;
};

/**
 * @brief Factory function to create StdioBusSdkHooks
 * 
 * Returns nullptr if SDK initialization fails.
 */
std::shared_ptr<StdioBusSdkHooks> MakeStdioBusSdkHooks(
    const std::string& config_path,
    bool shadow_mode = true);

} // namespace node

#endif // BITCOIN_NODE_STDIO_BUS_SDK_HOOKS_H
