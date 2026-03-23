// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_NODE_STDIO_BUS_RPC_METRICS_H
#define BITCOIN_NODE_STDIO_BUS_RPC_METRICS_H

#include <node/stdio_bus_hooks.h>

#include <atomic>
#include <memory>
#include <mutex>
#include <vector>

namespace node {

/**
 * @brief Global RPC metrics collector for Phase 5 P2P/RPC degradation monitoring
 * 
 * This class collects metrics from the HTTP/RPC layer and provides
 * periodic snapshots for interference analysis.
 * 
 * Thread safety: All methods are thread-safe.
 */
class StdioBusRpcMetrics {
public:
    StdioBusRpcMetrics() = default;
    ~StdioBusRpcMetrics() = default;

    // Non-copyable
    StdioBusRpcMetrics(const StdioBusRpcMetrics&) = delete;
    StdioBusRpcMetrics& operator=(const StdioBusRpcMetrics&) = delete;

    // ========== Metric Recording ==========

    /** Record HTTP request enqueue */
    void RecordHttpEnqueue(bool admitted, int queue_depth, int max_queue_depth);

    /** Record HTTP request dispatch */
    void RecordHttpDispatch(int64_t queue_wait_us);

    /** Record RPC call completion */
    void RecordRpcCall(int64_t latency_us, bool success);

    /** Record active RPC call count change */
    void IncrementActiveRpcCalls() { m_active_rpc_calls.fetch_add(1, std::memory_order_relaxed); }
    void DecrementActiveRpcCalls() { m_active_rpc_calls.fetch_sub(1, std::memory_order_relaxed); }

    // ========== Metric Queries ==========

    /** Get current queue depth */
    int GetQueueDepth() const { return m_queue_depth.load(std::memory_order_relaxed); }

    /** Get active RPC calls */
    int GetActiveRpcCalls() const { return m_active_rpc_calls.load(std::memory_order_relaxed); }

    /** Get total RPC calls in current interval */
    int64_t GetRpcCallsInInterval() const { return m_rpc_calls_interval.load(std::memory_order_relaxed); }

    /** Get total RPC latency in current interval */
    int64_t GetTotalLatencyInInterval() const { return m_total_latency_interval.load(std::memory_order_relaxed); }

    /** Get rejected requests in current interval */
    int64_t GetRejectedInInterval() const { return m_rejected_interval.load(std::memory_order_relaxed); }

    // ========== Percentile Calculation ==========

    /** Calculate latency percentiles from recent samples */
    struct LatencyPercentiles {
        int64_t p50_us{0};
        int64_t p95_us{0};
        int64_t p99_us{0};
    };
    LatencyPercentiles GetLatencyPercentiles() const;

    // ========== Interval Management ==========

    /** Reset interval counters (called after snapshot) */
    void ResetInterval();

    /** Set current queue depth (called from HTTP server) */
    void SetQueueDepth(int depth) { m_queue_depth.store(depth, std::memory_order_relaxed); }

private:
    // Current state
    std::atomic<int> m_queue_depth{0};
    std::atomic<int> m_active_rpc_calls{0};

    // Interval counters (reset after each snapshot)
    std::atomic<int64_t> m_rpc_calls_interval{0};
    std::atomic<int64_t> m_total_latency_interval{0};
    std::atomic<int64_t> m_rejected_interval{0};

    // Latency samples for percentile calculation
    mutable std::mutex m_samples_mutex;
    std::vector<int64_t> m_latency_samples;
    static constexpr size_t MAX_SAMPLES = 1000;
};

/**
 * @brief Global RPC metrics instance
 * 
 * Initialized in init.cpp when stdio_bus is enabled.
 */
extern std::unique_ptr<StdioBusRpcMetrics> g_stdio_bus_rpc_metrics;

/**
 * @brief Initialize global RPC metrics
 */
void InitStdioBusRpcMetrics();

/**
 * @brief Shutdown global RPC metrics
 */
void ShutdownStdioBusRpcMetrics();

/**
 * @brief RAII helper for tracking active RPC calls
 */
class StdioBusRpcCallTracker {
public:
    explicit StdioBusRpcCallTracker() {
        if (g_stdio_bus_rpc_metrics) {
            g_stdio_bus_rpc_metrics->IncrementActiveRpcCalls();
            m_tracking = true;
        }
    }
    
    ~StdioBusRpcCallTracker() {
        if (m_tracking && g_stdio_bus_rpc_metrics) {
            g_stdio_bus_rpc_metrics->DecrementActiveRpcCalls();
        }
    }

    // Non-copyable, movable
    StdioBusRpcCallTracker(const StdioBusRpcCallTracker&) = delete;
    StdioBusRpcCallTracker& operator=(const StdioBusRpcCallTracker&) = delete;
    StdioBusRpcCallTracker(StdioBusRpcCallTracker&& other) noexcept : m_tracking(other.m_tracking) {
        other.m_tracking = false;
    }
    StdioBusRpcCallTracker& operator=(StdioBusRpcCallTracker&&) = delete;

private:
    bool m_tracking{false};
};

} // namespace node

#endif // BITCOIN_NODE_STDIO_BUS_RPC_METRICS_H
