// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <node/stdio_bus_sdk_hooks.h>

#include <logging.h>
#include <tinyformat.h>
#include <util/strencodings.h>
#include <stdiobus/bus.hpp>

#include <chrono>
#include <sstream>
#include <thread>
#include <unistd.h>
#include <fcntl.h>
#include <cerrno>
#include <cstring>

namespace node {

// ============================================================================
// SDK Implementation (placeholder for real stdio_bus SDK integration)
// ============================================================================

struct StdioBusSdkHooks::SdkImpl {
    std::string config_path;
    bool connected{false};
    std::unique_ptr<stdiobus::Bus> bus;

    bool Connect(const std::string& path) {
        config_path = path;

        // Create Bus with a real worker process for full IPC pipeline.
        // The worker receives events through fork/exec + pipe (real IPC).
        stdiobus::Options opts;
        if (!path.empty()) {
            opts.config_path = path;
        } else {
            // Embedded config with a real worker: /bin/cat reads and discards
            // This exercises the full pipeline: ingest → framing → routing → pipe write → worker read
            opts.config_json = R"({
                "pools": [{
                    "name": "trace",
                    "command": ["/bin/cat"],
                    "count": 1
                }]
            })";
        }
        opts.on_error = [](stdiobus::ErrorCode code, std::string_view msg) {
            LogDebug(BCLog::NET, "stdio_bus error [%d]: %s\n", static_cast<int>(code), std::string(msg));
        };

        bus = std::make_unique<stdiobus::Bus>(std::move(opts));

        if (auto err = bus->start(); err) {
            LogError("stdio_bus: Failed to start bus: %s\n", err.message());
            bus.reset();
            return false;
        }

        connected = true;
        LogDebug(BCLog::NET, "stdio_bus: Bus started (config: %s)\n", path.empty() ? "<embedded>" : path);
        return true;
    }

    bool Send(const std::string& message) {
        if (!connected || !bus) return false;
        // Send through the real stdio_bus protocol stack:
        // ingest → framing → routing → event loop
        if (auto err = bus->send(message); err) {
            return false;
        }
        return true;
    }

    void Disconnect() {
        if (connected && bus) {
            bus->stop(std::chrono::seconds(5));
            bus.reset();
            connected = false;
            LogDebug(BCLog::NET, "stdio_bus: Bus stopped\n");
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
// Phase 2: Block Processing Delay Events (#21803)
// ============================================================================

void StdioBusSdkHooks::OnBlockAnnounce(const BlockAnnounceEvent& ev)
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

void StdioBusSdkHooks::OnBlockRequestDecision(const BlockRequestDecisionEvent& ev)
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

void StdioBusSdkHooks::OnBlockInFlight(const BlockInFlightEvent& ev)
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

void StdioBusSdkHooks::OnStallerDetected(const StallerDetectedEvent& ev)
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

void StdioBusSdkHooks::OnCompactBlockDecision(const CompactBlockDecisionEvent& ev)
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

void StdioBusSdkHooks::OnBlockSourceResolved(const BlockSourceResolvedEvent& ev)
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

void StdioBusSdkHooks::OnTxRemoved(const TxRemovedEvent& ev)
{
    if (!Enabled()) return;
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
}

void StdioBusSdkHooks::OnTxReplaced(const TxReplacedEvent& ev)
{
    if (!Enabled()) return;
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
}

void StdioBusSdkHooks::OnTxRejected(const TxRejectedEvent& ev)
{
    if (!Enabled()) return;
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
}

void StdioBusSdkHooks::OnUTXOCacheFlush(const UTXOCacheFlushEvent& ev)
{
    if (!Enabled()) return;
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
}

void StdioBusSdkHooks::OnPeerConnection(const PeerConnectionEvent& ev)
{
    if (!Enabled()) return;
    int64_t start = GetMonotonicTimeUs();
    bool enqueued = TryEnqueue(ev);
    int64_t latency = GetMonotonicTimeUs() - start;
    m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed);
    m_stats.events_total.fetch_add(1, std::memory_order_relaxed);
    if (!enqueued) m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed);
}

// ============================================================================
// Full USDT tracepoint parity (new hooks)
// ============================================================================

#define STDIOBUS_DEFINE_HOOK(Method, EventType) \
    void StdioBusSdkHooks::Method(const EventType& ev) \
    { \
        if (!Enabled()) return; \
        int64_t start = GetMonotonicTimeUs(); \
        bool enqueued = TryEnqueue(ev); \
        int64_t latency = GetMonotonicTimeUs() - start; \
        m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed); \
        m_stats.events_total.fetch_add(1, std::memory_order_relaxed); \
        if (!enqueued) m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed); \
    }

STDIOBUS_DEFINE_HOOK(OnPeerClosed, PeerClosedEvent)
STDIOBUS_DEFINE_HOOK(OnPeerEvicted, PeerEvictedEvent)
STDIOBUS_DEFINE_HOOK(OnPeerMisbehaving, PeerMisbehavingEvent)
STDIOBUS_DEFINE_HOOK(OnOutboundMessage, OutboundMessageEvent)
STDIOBUS_DEFINE_HOOK(OnMempoolAdded, MempoolAddedEvent)
STDIOBUS_DEFINE_HOOK(OnBlockConnected, BlockConnectedEvent)
STDIOBUS_DEFINE_HOOK(OnUTXOCacheAdd, UTXOCacheAddEvent)
STDIOBUS_DEFINE_HOOK(OnUTXOCacheSpent, UTXOCacheSpentEvent)
STDIOBUS_DEFINE_HOOK(OnUTXOCacheUncache, UTXOCacheUncacheEvent)
STDIOBUS_DEFINE_HOOK(OnCoinSelectionSelectedCoins, CoinSelectionSelectedCoinsEvent)
STDIOBUS_DEFINE_HOOK(OnCoinSelectionNormalCreateTx, CoinSelectionNormalCreateTxEvent)
STDIOBUS_DEFINE_HOOK(OnCoinSelectionAttemptingAps, CoinSelectionAttemptingApsEvent)
STDIOBUS_DEFINE_HOOK(OnCoinSelectionApsCreateTx, CoinSelectionApsCreateTxEvent)

#undef STDIOBUS_DEFINE_HOOK

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
               << "\"addr\":\"" << arg.addr << "\","
               << "\"conn_type\":\"" << arg.conn_type << "\","
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
        // Phase 2: Block Processing Delay Events
        else if constexpr (std::is_same_v<T, BlockAnnounceEvent>) {
            const char* via_str = "unknown";
            switch (arg.via) {
                case BlockAnnounceVia::Headers: via_str = "headers"; break;
                case BlockAnnounceVia::CompactBlock: via_str = "compact_block"; break;
                case BlockAnnounceVia::Inv: via_str = "inv"; break;
            }
            ss << "\"type\":\"block_announce\","
               << "\"hash\":\"" << arg.hash.GetHex() << "\","
               << "\"peer_id\":" << arg.peer_id << ","
               << "\"via\":\"" << via_str << "\","
               << "\"chainwork_delta\":" << arg.chainwork_delta << ","
               << "\"height\":" << arg.height << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, BlockRequestDecisionEvent>) {
            const char* reason_str = "unknown";
            switch (arg.reason) {
                case BlockRequestReason::NewBlock: reason_str = "new_block"; break;
                case BlockRequestReason::Retry: reason_str = "retry"; break;
                case BlockRequestReason::Hedge: reason_str = "hedge"; break;
                case BlockRequestReason::CompactFallback: reason_str = "compact_fallback"; break;
                case BlockRequestReason::ParallelDownload: reason_str = "parallel_download"; break;
            }
            ss << "\"type\":\"block_request_decision\","
               << "\"hash\":\"" << arg.hash.GetHex() << "\","
               << "\"peer_id\":" << arg.peer_id << ","
               << "\"reason\":\"" << reason_str << "\","
               << "\"is_preferred_peer\":" << (arg.is_preferred_peer ? "true" : "false") << ","
               << "\"first_in_flight\":" << (arg.first_in_flight ? "true" : "false") << ","
               << "\"already_in_flight\":" << arg.already_in_flight << ","
               << "\"can_direct_fetch\":" << (arg.can_direct_fetch ? "true" : "false") << ","
               << "\"is_limited_peer\":" << (arg.is_limited_peer ? "true" : "false") << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, BlockInFlightEvent>) {
            const char* action_str = "unknown";
            switch (arg.action) {
                case InFlightAction::Add: action_str = "add"; break;
                case InFlightAction::Remove: action_str = "remove"; break;
                case InFlightAction::Timeout: action_str = "timeout"; break;
            }
            ss << "\"type\":\"block_in_flight\","
               << "\"hash\":\"" << arg.hash.GetHex() << "\","
               << "\"peer_id\":" << arg.peer_id << ","
               << "\"action\":\"" << action_str << "\","
               << "\"inflight_count\":" << arg.inflight_count << ","
               << "\"peer_inflight_count\":" << arg.peer_inflight_count << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, StallerDetectedEvent>) {
            ss << "\"type\":\"staller_detected\","
               << "\"hash\":\"" << arg.hash.GetHex() << "\","
               << "\"staller_peer_id\":" << arg.staller_peer_id << ","
               << "\"waiting_peer_id\":" << arg.waiting_peer_id << ","
               << "\"window_end_height\":" << arg.window_end_height << ","
               << "\"stall_duration_us\":" << arg.stall_duration_us << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, CompactBlockDecisionEvent>) {
            const char* action_str = "unknown";
            switch (arg.action) {
                case CompactBlockAction::Reconstruct: action_str = "reconstruct"; break;
                case CompactBlockAction::GetBlockTxn: action_str = "get_block_txn"; break;
                case CompactBlockAction::GetData: action_str = "get_data"; break;
                case CompactBlockAction::Wait: action_str = "wait"; break;
                case CompactBlockAction::Drop: action_str = "drop"; break;
            }
            ss << "\"type\":\"compact_block_decision\","
               << "\"hash\":\"" << arg.hash.GetHex() << "\","
               << "\"peer_id\":" << arg.peer_id << ","
               << "\"action\":\"" << action_str << "\","
               << "\"missing_tx_count\":" << arg.missing_tx_count << ","
               << "\"first_in_flight\":" << (arg.first_in_flight ? "true" : "false") << ","
               << "\"is_highbandwidth\":" << (arg.is_highbandwidth ? "true" : "false") << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, BlockSourceResolvedEvent>) {
            ss << "\"type\":\"block_source_resolved\","
               << "\"hash\":\"" << arg.hash.GetHex() << "\","
               << "\"source_peer_id\":" << arg.source_peer_id << ","
               << "\"first_requested_peer_id\":" << arg.first_requested_peer_id << ","
               << "\"announce_to_receive_us\":" << arg.announce_to_receive_us << ","
               << "\"request_to_receive_us\":" << arg.request_to_receive_us << ","
               << "\"total_requests\":" << arg.total_requests << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, TxRemovedEvent>) {
            ss << "\"type\":\"tx_removed\","
                << "\"txid\":\"" << arg.txid.GetHex() << "\","
                << "\"reason\":\"" << arg.reason << "\","
                << "\"vsize\":" << arg.vsize << ","
                << "\"fee\":" << arg.fee << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, TxReplacedEvent>) {
            ss << "\"type\":\"tx_replaced\","
                << "\"replaced_txid\":\"" << arg.replaced_txid.GetHex() << "\","
                << "\"replaced_vsize\":" << arg.replaced_vsize << ","
                << "\"replaced_fee\":" << arg.replaced_fee << ","
                << "\"replacement_txid\":\"" << arg.replacement_txid.GetHex() << "\","
                << "\"replacement_vsize\":" << arg.replacement_vsize << ","
                << "\"replacement_fee\":" << arg.replacement_fee << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, TxRejectedEvent>) {
            ss << "\"type\":\"tx_rejected\","
                << "\"txid\":\"" << arg.txid.GetHex() << "\","
                << "\"reason\":\"" << arg.reason << "\","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, UTXOCacheFlushEvent>) {
            ss << "\"type\":\"utxocache_flush\","
                << "\"duration_us\":" << arg.duration_us << ","
                << "\"mode\":" << arg.mode << ","
                << "\"coins_count\":" << arg.coins_count << ","
                << "\"coins_mem_usage\":" << arg.coins_mem_usage << ","
                << "\"is_flush_for_prune\":" << (arg.is_flush_for_prune ? "true" : "false") << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, PeerConnectionEvent>) {
            ss << "\"type\":\"peer_connection\","
                << "\"peer_id\":" << arg.peer_id << ","
                << "\"addr\":\"" << arg.addr << "\","
                << "\"conn_type\":\"" << arg.conn_type << "\","
                << "\"network\":" << arg.network << ","
                << "\"inbound\":" << (arg.inbound ? "true" : "false") << ","
                << "\"existing_connections\":" << arg.existing_connections << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, PeerClosedEvent>) {
            ss << "\"type\":\"peer_closed\","
                << "\"peer_id\":" << arg.peer_id << ","
                << "\"addr\":\"" << arg.addr << "\","
                << "\"conn_type\":\"" << arg.conn_type << "\","
                << "\"network\":" << arg.network << ","
                << "\"time_established\":" << arg.time_established << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, PeerEvictedEvent>) {
            ss << "\"type\":\"peer_evicted\","
                << "\"peer_id\":" << arg.peer_id << ","
                << "\"addr\":\"" << arg.addr << "\","
                << "\"conn_type\":\"" << arg.conn_type << "\","
                << "\"network\":" << arg.network << ","
                << "\"time_established\":" << arg.time_established << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, PeerMisbehavingEvent>) {
            ss << "\"type\":\"peer_misbehaving\","
                << "\"peer_id\":" << arg.peer_id << ","
                << "\"message\":\"" << arg.message << "\","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, OutboundMessageEvent>) {
            ss << "\"type\":\"outbound_message\","
                << "\"peer_id\":" << arg.peer_id << ","
                << "\"addr\":\"" << arg.addr << "\","
                << "\"conn_type\":\"" << arg.conn_type << "\","
                << "\"msg_type\":\"" << arg.msg_type << "\","
                << "\"size_bytes\":" << arg.size_bytes << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, MempoolAddedEvent>) {
            ss << "\"type\":\"mempool_added\","
                << "\"txid\":\"" << arg.txid.GetHex() << "\","
                << "\"vsize\":" << arg.vsize << ","
                << "\"fee\":" << arg.fee << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, BlockConnectedEvent>) {
            ss << "\"type\":\"block_connected\","
                << "\"hash\":\"" << arg.hash.GetHex() << "\","
                << "\"height\":" << arg.height << ","
                << "\"tx_count\":" << arg.tx_count << ","
                << "\"inputs_count\":" << arg.inputs_count << ","
                << "\"sigops_cost\":" << arg.sigops_cost << ","
                << "\"duration_ns\":" << arg.duration_ns << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, UTXOCacheAddEvent>) {
            ss << "\"type\":\"utxocache_add\","
                << "\"txid\":\"" << arg.txid.GetHex() << "\","
                << "\"vout\":" << arg.vout << ","
                << "\"height\":" << arg.height << ","
                << "\"value\":" << arg.value << ","
                << "\"is_coinbase\":" << (arg.is_coinbase ? "true" : "false") << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, UTXOCacheSpentEvent>) {
            ss << "\"type\":\"utxocache_spent\","
                << "\"txid\":\"" << arg.txid.GetHex() << "\","
                << "\"vout\":" << arg.vout << ","
                << "\"height\":" << arg.height << ","
                << "\"value\":" << arg.value << ","
                << "\"is_coinbase\":" << (arg.is_coinbase ? "true" : "false") << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, UTXOCacheUncacheEvent>) {
            ss << "\"type\":\"utxocache_uncache\","
                << "\"txid\":\"" << arg.txid.GetHex() << "\","
                << "\"vout\":" << arg.vout << ","
                << "\"height\":" << arg.height << ","
                << "\"value\":" << arg.value << ","
                << "\"is_coinbase\":" << (arg.is_coinbase ? "true" : "false") << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, CoinSelectionSelectedCoinsEvent>) {
            ss << "\"type\":\"coin_selection_selected_coins\","
                << "\"wallet_name\":\"" << arg.wallet_name << "\","
                << "\"algorithm\":\"" << arg.algorithm << "\","
                << "\"target\":" << arg.target << ","
                << "\"waste\":" << arg.waste << ","
                << "\"selected_value\":" << arg.selected_value << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, CoinSelectionNormalCreateTxEvent>) {
            ss << "\"type\":\"coin_selection_normal_create_tx\","
                << "\"wallet_name\":\"" << arg.wallet_name << "\","
                << "\"success\":" << (arg.success ? "true" : "false") << ","
                << "\"fee\":" << arg.fee << ","
                << "\"change_pos\":" << arg.change_pos << ","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, CoinSelectionAttemptingApsEvent>) {
            ss << "\"type\":\"coin_selection_attempting_aps\","
                << "\"wallet_name\":\"" << arg.wallet_name << "\","
                << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, CoinSelectionApsCreateTxEvent>) {
            ss << "\"type\":\"coin_selection_aps_create_tx\","
                << "\"wallet_name\":\"" << arg.wallet_name << "\","
                << "\"use_aps\":" << (arg.use_aps ? "true" : "false") << ","
                << "\"success\":" << (arg.success ? "true" : "false") << ","
                << "\"fee\":" << arg.fee << ","
                << "\"change_pos\":" << arg.change_pos << ","
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
    stats.events_total = m_stats.events_total.load(std::memory_order_relaxed);
    stats.events_dropped = m_stats.events_dropped.load(std::memory_order_relaxed);
    stats.events_sent = m_stats.events_sent.load(std::memory_order_relaxed);
    stats.errors = m_stats.errors.load(std::memory_order_relaxed);
    stats.last_hook_latency_us = m_stats.last_hook_latency_us.load(std::memory_order_relaxed);
    stats.queue_depth = m_stats.queue_depth.load(std::memory_order_relaxed);
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
