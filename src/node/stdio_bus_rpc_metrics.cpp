// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <node/stdio_bus_rpc_metrics.h>

#include <algorithm>

namespace node {

// Global instance
std::unique_ptr<StdioBusRpcMetrics> g_stdio_bus_rpc_metrics;

void InitStdioBusRpcMetrics()
{
    g_stdio_bus_rpc_metrics = std::make_unique<StdioBusRpcMetrics>();
}

void ShutdownStdioBusRpcMetrics()
{
    g_stdio_bus_rpc_metrics.reset();
}

void StdioBusRpcMetrics::RecordHttpEnqueue(bool admitted, int queue_depth, int max_queue_depth)
{
    m_queue_depth.store(queue_depth, std::memory_order_relaxed);
    if (!admitted) {
        m_rejected_interval.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusRpcMetrics::RecordHttpDispatch(int64_t queue_wait_us)
{
    // Queue wait time is part of total latency, tracked separately if needed
    (void)queue_wait_us;
}

void StdioBusRpcMetrics::RecordRpcCall(int64_t latency_us, bool success)
{
    m_rpc_calls_interval.fetch_add(1, std::memory_order_relaxed);
    m_total_latency_interval.fetch_add(latency_us, std::memory_order_relaxed);

    // Add to samples for percentile calculation
    {
        std::lock_guard<std::mutex> lock(m_samples_mutex);
        if (m_latency_samples.size() >= MAX_SAMPLES) {
            // Simple rotation: remove oldest samples
            m_latency_samples.erase(m_latency_samples.begin(), 
                                     m_latency_samples.begin() + MAX_SAMPLES / 4);
        }
        m_latency_samples.push_back(latency_us);
    }

    (void)success; // Could track success rate if needed
}

StdioBusRpcMetrics::LatencyPercentiles StdioBusRpcMetrics::GetLatencyPercentiles() const
{
    LatencyPercentiles result;
    
    std::vector<int64_t> sorted_samples;
    {
        std::lock_guard<std::mutex> lock(m_samples_mutex);
        if (m_latency_samples.empty()) {
            return result;
        }
        sorted_samples = m_latency_samples;
    }
    
    std::sort(sorted_samples.begin(), sorted_samples.end());
    
    size_t n = sorted_samples.size();
    if (n > 0) {
        result.p50_us = sorted_samples[n * 50 / 100];
        result.p95_us = sorted_samples[std::min(n * 95 / 100, n - 1)];
        result.p99_us = sorted_samples[std::min(n * 99 / 100, n - 1)];
    }
    
    return result;
}

void StdioBusRpcMetrics::ResetInterval()
{
    m_rpc_calls_interval.store(0, std::memory_order_relaxed);
    m_total_latency_interval.store(0, std::memory_order_relaxed);
    m_rejected_interval.store(0, std::memory_order_relaxed);
    
    // Don't clear samples - they're used for rolling percentiles
}

} // namespace node
