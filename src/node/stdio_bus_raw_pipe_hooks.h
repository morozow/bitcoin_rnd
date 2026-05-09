// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_NODE_STDIO_BUS_RAW_PIPE_HOOKS_H
#define BITCOIN_NODE_STDIO_BUS_RAW_PIPE_HOOKS_H

#include <node/stdio_bus_hooks.h>

#include <atomic>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <variant>
#include <vector>

namespace node {

/**
 * @brief Raw Unix pipe IPC implementation of StdioBusHooks
 *
 * Provides the same functionality as StdioBusSdkHooks but uses raw
 * Unix pipes (pipe() + fork() + exec()) without the stdio_bus library.
 * This isolates the pure IPC overhead from any protocol library cost.
 *
 * Architecture:
 *   - Same bounded async queue as StdioBusSdkHooks
 *   - Same JSON serialization (SerializeEvent)
 *   - Same worker scripts (contrib/tracing/ipc/*)
 *   - Transport: direct pipe write (no framing, no routing, no bus runtime)
 *
 * Each worker is spawned via fork()/exec() with stdin connected to a
 * pipe. Events are written as newline-delimited JSON directly to the
 * pipe fd. Worker stderr is inherited from the parent process.
 *
 * This allows benchmarking the pure cost of:
 *   1. Event struct construction
 *   2. JSON serialization (ostringstream)
 *   3. pipe write() syscall
 *   4. Worker process read + parse + process
 *
 * Without:
 *   - stdio_bus framing protocol
 *   - stdio_bus routing/multiplexing
 *   - stdio_bus event loop overhead
 *   - stdio_bus worker lifecycle management
 */
class StdioBusRawPipeHooks final : public StdioBusHooks {
public:
    /**
     * @brief Worker configuration (mirrors stdiobus_trace.json format)
     */
    struct WorkerConfig {
        std::string id;
        std::string command;
        std::vector<std::string> args;
    };

    /**
     * @brief Configuration for raw pipe hooks
     */
    struct Config {
        std::vector<WorkerConfig> workers;  ///< Workers to spawn
        size_t queue_capacity{4096};        ///< Max events in queue before dropping
        bool shadow_mode{true};             ///< Shadow mode (observe only)
    };

    explicit StdioBusRawPipeHooks(Config config);
    ~StdioBusRawPipeHooks() override;

    // Non-copyable, non-movable
    StdioBusRawPipeHooks(const StdioBusRawPipeHooks&) = delete;
    StdioBusRawPipeHooks& operator=(const StdioBusRawPipeHooks&) = delete;

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

    // Phase 2: Block Processing Delay Events
    void OnBlockAnnounce(const BlockAnnounceEvent& ev) override;
    void OnBlockRequestDecision(const BlockRequestDecisionEvent& ev) override;
    void OnBlockInFlight(const BlockInFlightEvent& ev) override;
    void OnStallerDetected(const StallerDetectedEvent& ev) override;
    void OnCompactBlockDecision(const CompactBlockDecisionEvent& ev) override;
    void OnBlockSourceResolved(const BlockSourceResolvedEvent& ev) override;
    void OnTxRemoved(const TxRemovedEvent& ev) override;
    void OnTxReplaced(const TxReplacedEvent& ev) override;
    void OnTxRejected(const TxRejectedEvent& ev) override;
    void OnUTXOCacheFlush(const UTXOCacheFlushEvent& ev) override;
    void OnPeerConnection(const PeerConnectionEvent& ev) override;

    // Full USDT tracepoint parity
    void OnPeerClosed(const PeerClosedEvent& ev) override;
    void OnPeerEvicted(const PeerEvictedEvent& ev) override;
    void OnPeerMisbehaving(const PeerMisbehavingEvent& ev) override;
    void OnOutboundMessage(const OutboundMessageEvent& ev) override;
    void OnMempoolAdded(const MempoolAddedEvent& ev) override;
    void OnBlockConnected(const BlockConnectedEvent& ev) override;
    void OnUTXOCacheAdd(const UTXOCacheAddEvent& ev) override;
    void OnUTXOCacheSpent(const UTXOCacheSpentEvent& ev) override;
    void OnUTXOCacheUncache(const UTXOCacheUncacheEvent& ev) override;
    void OnCoinSelectionSelectedCoins(const CoinSelectionSelectedCoinsEvent& ev) override;
    void OnCoinSelectionNormalCreateTx(const CoinSelectionNormalCreateTxEvent& ev) override;
    void OnCoinSelectionAttemptingAps(const CoinSelectionAttemptingApsEvent& ev) override;
    void OnCoinSelectionApsCreateTx(const CoinSelectionApsCreateTxEvent& ev) override;

    // ========== Lifecycle ==========

    /** Spawn worker processes and start background writer thread */
    bool Start();

    /** Close pipes and wait for workers to exit */
    void Stop();

    /** Check if running */
    bool IsRunning() const { return m_running.load(std::memory_order_relaxed); }

    /** Get number of active workers */
    int WorkerCount() const { return m_active_workers.load(std::memory_order_relaxed); }

    // ========== Statistics ==========

    struct Stats {
        uint64_t events_total{0};
        uint64_t events_dropped{0};
        uint64_t events_written{0};
        uint64_t write_errors{0};
        int64_t last_hook_latency_us{0};
        size_t queue_depth{0};
    };

    Stats GetStats() const;

private:
    // Reuse the same Event variant as StdioBusSdkHooks for identical serialization
    using Event = std::variant<
        MessageEvent, HeadersEvent, BlockReceivedEvent, BlockValidatedEvent,
        TxAdmissionEvent, MsgHandlerLoopEvent, RpcCallEvent,
        BlockAnnounceEvent, BlockRequestDecisionEvent, BlockInFlightEvent,
        StallerDetectedEvent, CompactBlockDecisionEvent, BlockSourceResolvedEvent,
        TxRemovedEvent, TxReplacedEvent, TxRejectedEvent,
        UTXOCacheFlushEvent, PeerConnectionEvent,
        PeerClosedEvent, PeerEvictedEvent, PeerMisbehavingEvent,
        OutboundMessageEvent, MempoolAddedEvent, BlockConnectedEvent,
        UTXOCacheAddEvent, UTXOCacheSpentEvent, UTXOCacheUncacheEvent,
        CoinSelectionSelectedCoinsEvent, CoinSelectionNormalCreateTxEvent,
        CoinSelectionAttemptingApsEvent, CoinSelectionApsCreateTxEvent
    >;

    /** Worker process state */
    struct WorkerProcess {
        std::string id;
        pid_t pid{-1};
        int write_fd{-1};  // Our end of the pipe (write to worker's stdin)
    };

    /** Try to enqueue an event (non-blocking, identical to StdioBusSdkHooks) */
    bool TryEnqueue(Event ev);

    /** Background writer thread: dequeue events and write to all worker pipes */
    void WriterLoop();

    /** Serialize event to JSON (IDENTICAL to StdioBusSdkHooks::SerializeEvent) */
    std::string SerializeEvent(const Event& ev) const;

    /** Write a line to all worker pipes */
    bool WriteToWorkers(const std::string& json_line);

    /** Spawn a single worker process, return its state */
    WorkerProcess SpawnWorker(const WorkerConfig& config);

    // Configuration
    Config m_config;
    bool m_shadow_mode;

    // State
    std::atomic<bool> m_enabled{false};
    std::atomic<bool> m_running{false};
    std::atomic<bool> m_stop_requested{false};
    std::atomic<int> m_active_workers{0};

    // Worker processes
    std::vector<WorkerProcess> m_workers;

    // Bounded queue (identical to StdioBusSdkHooks)
    mutable std::mutex m_queue_mutex;
    std::condition_variable m_queue_cv;
    std::queue<Event> m_queue;
    size_t m_queue_capacity;

    // Background writer thread
    std::thread m_writer_thread;

    // Statistics
    struct StatsInternal {
        std::atomic<uint64_t> events_total{0};
        std::atomic<uint64_t> events_dropped{0};
        std::atomic<uint64_t> events_written{0};
        std::atomic<uint64_t> write_errors{0};
        std::atomic<int64_t> last_hook_latency_us{0};
        std::atomic<size_t> queue_depth{0};
    };
    mutable StatsInternal m_stats;
};

/**
 * @brief Parse worker config from JSON file (same format as stdiobus_trace.json)
 *
 * Expected format:
 * {
 *   "pools": [
 *     {"id": "worker-name", "command": "python3", "args": ["script.py"], "instances": 1}
 *   ]
 * }
 */
StdioBusRawPipeHooks::Config ParseRawPipeConfig(const std::string& config_path);

/**
 * @brief Factory function to create raw pipe hooks from config file
 */
std::shared_ptr<StdioBusRawPipeHooks> MakeRawPipeHooks(
    const std::string& config_path,
    bool shadow_mode = true);

} // namespace node

#endif // BITCOIN_NODE_STDIO_BUS_RAW_PIPE_HOOKS_H
