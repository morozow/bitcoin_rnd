// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <node/stdio_bus_sdk_hooks.h>

#include <logging.h>
#include <tinyformat.h>
#include <util/strencodings.h>

#include <chrono>
#include <sstream>

namespace node {

// ============================================================================
// SDK Implementation (placeholder for real stdio_bus SDK integration)
// ============================================================================

struct StdioBusSdkHooks::SdkImpl {
    std::string config_path;
    bool connected{false};
    
    // In real implementation, this would be:
    // std::unique_ptr<stdiobus::Bus> bus;
    
    bool Connect(const std::string& path) {
        config_path = path;
        // TODO: Real SDK integration
        // bus = std::make_unique<stdiobus::Bus>(path);
        // if (auto err = bus->start(); err) {
        //     LogDebug(BCLog::NET, "stdio_bus SDK failed to start: %s\n", err.message());
        //     return false;
        // }
        connected = true;
        LogDebug(BCLog::NET, "stdio_bus SDK connected (config: %s)\n", path);
        return true;
    }
    
    bool Send(const std::string& message) {
        if (!connected) return false;
        // TODO: Real SDK integration
        // if (auto err = bus->send(message); err) {
        //     return false;
        // }
        LogDebug(BCLog::NET, "stdio_bus SDK send: %s\n", message.substr(0, 100));
        return true;
    }
    
    void Disconnect() {
        if (connected) {
            // TODO: Real SDK integration
            // bus->stop(std::chrono::seconds(5));
            // bus.reset();
            connected = false;
            LogDebug(BCLog::NET, "stdio_bus SDK disconnected\n");
        }
    }
};

// ============================================================================
// StdioBusSdkHooks Implementation
// ============================================================================

StdioBusSdkHooks::StdioBusSdkHooks(Config config)
    : m_config(std::move(config))
    , m_shadow_mode(m_config.shadow_mode)
    , m_queue_capacity(m_config.queue_capacity)
    , m_sdk(std::make_unique<SdkImpl>())
{
}

StdioBusSdkHooks::~StdioBusSdkHooks()
{
    Stop();
}

bool StdioBusSdkHooks::Start()
{
    if (m_running.load(std::memory_order_relaxed)) {
        return true; // Already running
    }

    // Connect SDK
    if (!m_sdk->Connect(m_config.config_path)) {
        LogError("stdio_bus: Failed to connect SDK\n");
        return false;
    }

    // Start worker thread
    m_stop_requested.store(false, std::memory_order_relaxed);
    m_worker_thread = std::thread(&StdioBusSdkHooks::WorkerLoop, this);
    
    m_running.store(true, std::memory_order_release);
    m_enabled.store(true, std::memory_order_release);
    
    LogInfo("stdio_bus: Started (shadow_mode=%s, queue_capacity=%zu)\n",
            m_shadow_mode ? "true" : "false", m_queue_capacity);
    return true;
}

void StdioBusSdkHooks::Stop()
{
    if (!m_running.load(std::memory_order_relaxed)) {
        return; // Not running
    }

    m_enabled.store(false, std::memory_order_release);
    m_stop_requested.store(true, std::memory_order_release);
    
    // Wake up worker
    m_queue_cv.notify_all();
    
    // Wait for worker to finish
    if (m_worker_thread.joinable()) {
        m_worker_thread.join();
    }
    
    // Disconnect SDK
    m_sdk->Disconnect();
    
    m_running.store(false, std::memory_order_release);
    LogInfo("stdio_bus: Stopped\n");
}

// ============================================================================
// Hook Implementations (fast path - just enqueue)
// ============================================================================

void StdioBusSdkHooks::OnMessage(const MessageEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnHeaders(const HeadersEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnBlockReceived(const BlockReceivedEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnBlockValidated(const BlockValidatedEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnTxAdmission(const TxAdmissionEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnMsgHandlerLoop(const MsgHandlerLoopEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnRpcCall(const RpcCallEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

// ============================================================================
// Phase 4: Mempool Hook Implementations
// ============================================================================

void StdioBusSdkHooks::OnMempoolAdmissionAttempt(const MempoolAdmissionAttemptEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnMempoolAdmissionResult(const MempoolAdmissionResultEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnPackageAdmission(const PackageAdmissionEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnMempoolBatch(const MempoolBatchEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnMempoolOrdering(const MempoolOrderingEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnMempoolLockContention(const MempoolLockContentionEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

void StdioBusSdkHooks::OnMempoolEviction(const MempoolEvictionEvent& ev)
{
    if (!Enabled()) return;
    
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) {
        m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
    }
}

// ============================================================================
// Queue Operations
// ============================================================================

bool StdioBusSdkHooks::TryEnqueue(Event ev)
{
    std::unique_lock<std::mutex> lock(m_queue_mutex, std::try_to_lock);
    if (!lock.owns_lock()) {
        // Could not acquire lock immediately - drop event (fail-open)
        return false;
    }
    
    if (m_queue.size() >= m_queue_capacity) {
        // Queue full - drop event (fail-open)
        return false;
    }
    
    m_queue.push(std::move(ev));
    m_stats.queue_depth.store(m_queue.size(), std::memory_order_relaxed);
    
    lock.unlock();
    m_queue_cv.notify_one();
    return true;
}

// ============================================================================
// Background Worker
// ============================================================================

void StdioBusSdkHooks::WorkerLoop()
{
    LogDebug(BCLog::NET, "stdio_bus: Worker thread started\n");
    
    while (!m_stop_requested.load(std::memory_order_relaxed)) {
        Event ev;
        
        // Wait for event
        {
            std::unique_lock<std::mutex> lock(m_queue_mutex);
            m_queue_cv.wait_for(lock, std::chrono::milliseconds(100), [this] {
                return !m_queue.empty() || m_stop_requested.load(std::memory_order_relaxed);
            });
            
            if (m_queue.empty()) {
                continue;
            }
            
            ev = std::move(m_queue.front());
            m_queue.pop();
            m_stats.queue_depth.store(m_queue.size(), std::memory_order_relaxed);
        }
        
        // Serialize and send (outside lock)
        std::string json = SerializeEvent(ev);
        if (SendToSdk(json)) {
            m_stats.events_sent.fetch_add(1, std::memory_order_relaxed);
        } else {
            m_stats.errors.fetch_add(1, std::memory_order_relaxed);
        }
    }
    
    // Drain remaining events on shutdown
    {
        std::lock_guard<std::mutex> lock(m_queue_mutex);
        while (!m_queue.empty()) {
            Event ev = std::move(m_queue.front());
            m_queue.pop();
            std::string json = SerializeEvent(ev);
            SendToSdk(json);
        }
    }
    
    LogDebug(BCLog::NET, "stdio_bus: Worker thread stopped\n");
}

// ============================================================================
// Serialization
// ============================================================================

std::string StdioBusSdkHooks::SerializeEvent(const Event& ev) const
{
    std::ostringstream ss;
    ss << "{\"jsonrpc\":\"2.0\",\"method\":\"stdio_bus.event\",\"params\":{";
    
    std::visit([&ss](auto&& arg) {
        using T = std::decay_t<decltype(arg)>;
        
        if constexpr (std::is_same_v<T, MessageEvent>) {
            ss << "\"type\":\"message\","
               << "\"peer_id\":" << arg.peer_id << ","
               << "\"msg_type\":\"" << arg.msg_type << "\","
               << "\"size_bytes\":" << arg.size_bytes << ","
               << "\"received_us\":" << arg.received_us;
        }
        else if constexpr (std::is_same_v<T, HeadersEvent>) {
            ss << "\"type\":\"headers\","
               << "\"peer_id\":" << arg.peer_id << ","
               << "\"count\":" << arg.count << ","
               << "\"first_prev_hash\":\"" << arg.first_prev_hash.GetHex() << "\","
               << "\"received_us\":" << arg.received_us;
        }
        else if constexpr (std::is_same_v<T, BlockReceivedEvent>) {
            ss << "\"type\":\"block_received\","
               << "\"peer_id\":" << arg.peer_id << ","
               << "\"hash\":\"" << arg.hash.GetHex() << "\","
               << "\"height\":" << arg.height << ","
               << "\"size_bytes\":" << arg.size_bytes << ","
               << "\"tx_count\":" << arg.tx_count << ","
               << "\"received_us\":" << arg.received_us;
        }
        else if constexpr (std::is_same_v<T, BlockValidatedEvent>) {
            ss << "\"type\":\"block_validated\","
               << "\"hash\":\"" << arg.hash.GetHex() << "\","
               << "\"height\":" << arg.height << ","
               << "\"tx_count\":" << arg.tx_count << ","
               << "\"received_us\":" << arg.received_us << ","
               << "\"validated_us\":" << arg.validated_us << ","
               << "\"accepted\":" << (arg.accepted ? "true" : "false");
            if (!arg.reject_reason.empty()) {
                ss << ",\"reject_reason\":\"" << arg.reject_reason << "\"";
            }
        }
        else if constexpr (std::is_same_v<T, TxAdmissionEvent>) {
            ss << "\"type\":\"tx_admission\","
               << "\"txid\":\"" << arg.txid.GetHex() << "\","
               << "\"wtxid\":\"" << arg.wtxid.GetHex() << "\","
               << "\"size_bytes\":" << arg.size_bytes << ","
               << "\"received_us\":" << arg.received_us << ","
               << "\"processed_us\":" << arg.processed_us << ","
               << "\"accepted\":" << (arg.accepted ? "true" : "false");
            if (!arg.reject_reason.empty()) {
                ss << ",\"reject_reason\":\"" << arg.reject_reason << "\"";
            }
        }
        else if constexpr (std::is_same_v<T, MsgHandlerLoopEvent>) {
            ss << "\"type\":\"msg_handler_loop\","
               << "\"iteration\":" << arg.iteration << ","
               << "\"start_us\":" << arg.start_us << ","
               << "\"end_us\":" << arg.end_us << ","
               << "\"messages_processed\":" << arg.messages_processed << ","
               << "\"had_work\":" << (arg.had_work ? "true" : "false");
        }
        else if constexpr (std::is_same_v<T, RpcCallEvent>) {
            ss << "\"type\":\"rpc_call\","
               << "\"method\":\"" << arg.method << "\","
               << "\"start_us\":" << arg.start_us << ","
               << "\"end_us\":" << arg.end_us << ","
               << "\"success\":" << (arg.success ? "true" : "false");
        }
        // Phase 4: Mempool Events
        else if constexpr (std::is_same_v<T, MempoolAdmissionAttemptEvent>) {
            ss << "\"type\":\"mempool_admission_attempt\","
               << "\"txid\":\"" << arg.txid.GetHex() << "\","
               << "\"wtxid\":\"" << arg.wtxid.GetHex() << "\","
               << "\"source\":" << static_cast<int>(arg.source) << ","
               << "\"vsize\":" << arg.vsize << ","
               << "\"fee_sat\":" << arg.fee_sat << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, MempoolAdmissionResultEvent>) {
            ss << "\"type\":\"mempool_admission_result\","
               << "\"txid\":\"" << arg.txid.GetHex() << "\","
               << "\"wtxid\":\"" << arg.wtxid.GetHex() << "\","
               << "\"result\":" << static_cast<int>(arg.result) << ","
               << "\"reject_code\":" << arg.reject_code << ","
               << "\"replaced_count\":" << arg.replaced_count << ","
               << "\"effective_feerate_sat_vb\":" << arg.effective_feerate_sat_vb << ","
               << "\"start_us\":" << arg.start_us << ","
               << "\"end_us\":" << arg.end_us;
            if (!arg.reject_reason.empty()) {
                ss << ",\"reject_reason\":\"" << arg.reject_reason << "\"";
            }
        }
        else if constexpr (std::is_same_v<T, PackageAdmissionEvent>) {
            ss << "\"type\":\"package_admission\","
               << "\"package_hash\":\"" << arg.package_hash.GetHex() << "\","
               << "\"strategy\":" << static_cast<int>(arg.strategy) << ","
               << "\"tx_count\":" << arg.tx_count << ","
               << "\"total_vsize\":" << arg.total_vsize << ","
               << "\"total_fees_sat\":" << arg.total_fees_sat << ","
               << "\"accepted_count\":" << arg.accepted_count << ","
               << "\"rejected_count\":" << arg.rejected_count << ","
               << "\"start_us\":" << arg.start_us << ","
               << "\"end_us\":" << arg.end_us;
        }
        else if constexpr (std::is_same_v<T, MempoolBatchEvent>) {
            ss << "\"type\":\"mempool_batch\","
               << "\"batch_type\":" << static_cast<int>(arg.batch_type) << ","
               << "\"tx_count_in\":" << arg.tx_count_in << ","
               << "\"tx_count_out\":" << arg.tx_count_out << ","
               << "\"bytes_affected\":" << arg.bytes_affected << ","
               << "\"start_us\":" << arg.start_us << ","
               << "\"end_us\":" << arg.end_us;
        }
        else if constexpr (std::is_same_v<T, MempoolOrderingEvent>) {
            ss << "\"type\":\"mempool_ordering\","
               << "\"phase\":" << static_cast<int>(arg.phase) << ","
               << "\"candidate_count\":" << arg.candidate_count << ","
               << "\"cluster_count\":" << arg.cluster_count << ","
               << "\"work_budget\":" << arg.work_budget << ","
               << "\"work_used\":" << arg.work_used << ","
               << "\"start_us\":" << arg.start_us << ","
               << "\"end_us\":" << arg.end_us;
        }
        else if constexpr (std::is_same_v<T, MempoolLockContentionEvent>) {
            ss << "\"type\":\"mempool_lock_contention\","
               << "\"lock_name\":\"" << arg.lock_name << "\","
               << "\"context\":\"" << arg.context << "\","
               << "\"wait_us\":" << arg.wait_us << ","
               << "\"hold_us\":" << arg.hold_us << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, MempoolEvictionEvent>) {
            ss << "\"type\":\"mempool_eviction\","
               << "\"reason\":" << static_cast<int>(arg.reason) << ","
               << "\"tx_count\":" << arg.tx_count << ","
               << "\"bytes_removed\":" << arg.bytes_removed << ","
               << "\"fees_removed_sat\":" << arg.fees_removed_sat << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
    }, ev);
    
    ss << "}}";
    return ss.str();
}

bool StdioBusSdkHooks::SendToSdk(const std::string& json)
{
    try {
        return m_sdk->Send(json);
    } catch (...) {
        // Fail silently - hooks must not affect consensus
        LogDebug(BCLog::NET, "stdio_bus: SDK send threw exception\n");
        return false;
    }
}

// ============================================================================
// Statistics
// ============================================================================

StdioBusStats StdioBusSdkHooks::GetStats() const
{
    StdioBusStats stats;
    stats.events_total.store(m_stats.events_total.load(std::memory_order_relaxed));
    stats.events_dropped.store(m_stats.events_dropped.load(std::memory_order_relaxed));
    stats.events_sent.store(m_stats.events_sent.load(std::memory_order_relaxed));
    stats.errors.store(m_stats.errors.load(std::memory_order_relaxed));
    stats.last_hook_latency_us.store(m_stats.last_hook_latency_us.load(std::memory_order_relaxed));
    stats.queue_depth.store(m_stats.queue_depth.load(std::memory_order_relaxed));
    return stats;
}

void StdioBusSdkHooks::ResetStats()
{
    m_stats.events_total.store(0, std::memory_order_relaxed);
    m_stats.events_dropped.store(0, std::memory_order_relaxed);
    m_stats.events_sent.store(0, std::memory_order_relaxed);
    m_stats.errors.store(0, std::memory_order_relaxed);
    m_stats.last_hook_latency_us.store(0, std::memory_order_relaxed);
}

// ============================================================================
// Factory
// ============================================================================

std::shared_ptr<StdioBusSdkHooks> MakeStdioBusSdkHooks(
    const std::string& config_path,
    bool shadow_mode)
{
    StdioBusSdkHooks::Config config;
    config.config_path = config_path;
    config.shadow_mode = shadow_mode;
    config.queue_capacity = 4096;
    
    auto hooks = std::make_shared<StdioBusSdkHooks>(std::move(config));
    if (!hooks->Start()) {
        return nullptr;
    }
    return hooks;
}

} // namespace node
