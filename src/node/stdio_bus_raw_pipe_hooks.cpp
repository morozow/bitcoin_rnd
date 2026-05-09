// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <node/stdio_bus_raw_pipe_hooks.h>
#include <node/stdio_bus_sdk_hooks.h>  // For SerializeEvent reuse

#include <logging.h>
#include <tinyformat.h>
#include <util/strencodings.h>

#include <cerrno>
#include <chrono>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <signal.h>
#include <sstream>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>

// For JSON config parsing (minimal, no external dependency)
#include <algorithm>
#include <stdexcept>

namespace node {

// ============================================================================
// Construction / Destruction
// ============================================================================

StdioBusRawPipeHooks::StdioBusRawPipeHooks(Config config)
    : m_config(std::move(config))
    , m_shadow_mode(m_config.shadow_mode)
    , m_queue_capacity(m_config.queue_capacity)
{
}

StdioBusRawPipeHooks::~StdioBusRawPipeHooks()
{
    Stop();
}

// ============================================================================
// Lifecycle
// ============================================================================

bool StdioBusRawPipeHooks::Start()
{
    if (m_running.load(std::memory_order_relaxed)) {
        return true;
    }

    // Spawn worker processes
    for (const auto& wc : m_config.workers) {
        WorkerProcess wp = SpawnWorker(wc);
        if (wp.pid > 0 && wp.write_fd >= 0) {
            m_workers.push_back(wp);
            m_active_workers.fetch_add(1, std::memory_order_relaxed);
            LogDebug(BCLog::NET, "raw_pipe: Spawned worker '%s' (pid=%d, fd=%d)\n",
                     wc.id, wp.pid, wp.write_fd);
        } else {
            LogError("raw_pipe: Failed to spawn worker '%s'\n", wc.id);
        }
    }

    if (m_workers.empty()) {
        LogError("raw_pipe: No workers spawned, aborting\n");
        return false;
    }

    // Start writer thread
    m_stop_requested.store(false, std::memory_order_relaxed);
    m_writer_thread = std::thread(&StdioBusRawPipeHooks::WriterLoop, this);

    m_running.store(true, std::memory_order_release);
    m_enabled.store(true, std::memory_order_release);

    LogInfo("raw_pipe: Started with %d workers (shadow_mode=%s, queue_capacity=%zu)\n",
            m_active_workers.load(), m_shadow_mode ? "true" : "false", m_queue_capacity);
    return true;
}

void StdioBusRawPipeHooks::Stop()
{
    if (!m_running.load(std::memory_order_relaxed)) {
        return;
    }

    m_enabled.store(false, std::memory_order_release);
    m_stop_requested.store(true, std::memory_order_release);

    // Wake up writer thread
    m_queue_cv.notify_all();

    if (m_writer_thread.joinable()) {
        m_writer_thread.join();
    }

    // Close write ends of pipes — this sends EOF to workers
    for (auto& wp : m_workers) {
        if (wp.write_fd >= 0) {
            close(wp.write_fd);
            wp.write_fd = -1;
        }
    }

    // Wait for worker processes to exit (they should exit on EOF)
    for (auto& wp : m_workers) {
        if (wp.pid > 0) {
            int status = 0;
            int ret = waitpid(wp.pid, &status, WNOHANG);
            if (ret == 0) {
                // Not exited yet, give it 2 seconds
                for (int i = 0; i < 20; ++i) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(100));
                    ret = waitpid(wp.pid, &status, WNOHANG);
                    if (ret != 0) break;
                }
                if (ret == 0) {
                    // Still running, send SIGTERM
                    kill(wp.pid, SIGTERM);
                    waitpid(wp.pid, &status, 0);
                }
            }
            LogDebug(BCLog::NET, "raw_pipe: Worker '%s' (pid=%d) exited\n",
                     wp.id, wp.pid);
            wp.pid = -1;
        }
    }

    m_workers.clear();
    m_active_workers.store(0, std::memory_order_relaxed);
    m_running.store(false, std::memory_order_release);
    LogInfo("raw_pipe: Stopped\n");
}

// ============================================================================
// Worker Spawning (raw fork/exec + pipe)
// ============================================================================

StdioBusRawPipeHooks::WorkerProcess StdioBusRawPipeHooks::SpawnWorker(
    const WorkerConfig& config)
{
    WorkerProcess wp;
    wp.id = config.id;

    // Create pipe: pipe_fds[0] = read end (child stdin), pipe_fds[1] = write end (parent)
    int pipe_fds[2];
    if (pipe(pipe_fds) != 0) {
        LogError("raw_pipe: pipe() failed for worker '%s': %s\n",
                 config.id, strerror(errno));
        return wp;
    }

    pid_t pid = fork();
    if (pid < 0) {
        // Fork failed
        LogError("raw_pipe: fork() failed for worker '%s': %s\n",
                 config.id, strerror(errno));
        close(pipe_fds[0]);
        close(pipe_fds[1]);
        return wp;
    }

    if (pid == 0) {
        // === Child process ===

        // Connect pipe read end to stdin
        close(pipe_fds[1]);  // Close write end in child
        if (dup2(pipe_fds[0], STDIN_FILENO) < 0) {
            _exit(127);
        }
        close(pipe_fds[0]);  // Close original fd after dup2

        // stderr is inherited from parent (so worker output goes to bitcoind stderr)
        // stdout is also inherited (workers may print to stdout)

        // Build argv for exec
        std::vector<const char*> argv;
        argv.push_back(config.command.c_str());
        for (const auto& arg : config.args) {
            argv.push_back(arg.c_str());
        }
        argv.push_back(nullptr);

        // exec the worker
        execvp(config.command.c_str(), const_cast<char* const*>(argv.data()));

        // If exec fails, exit
        _exit(127);
    }

    // === Parent process ===
    close(pipe_fds[0]);  // Close read end in parent

    // Set write end to non-blocking to avoid stalling bitcoind
    int flags = fcntl(pipe_fds[1], F_GETFL, 0);
    if (flags >= 0) {
        fcntl(pipe_fds[1], F_SETFL, flags | O_NONBLOCK);
    }

    wp.pid = pid;
    wp.write_fd = pipe_fds[1];
    return wp;
}

// ============================================================================
// Hook Implementations (fast path — identical to StdioBusSdkHooks)
// ============================================================================

#define RAW_PIPE_HOOK_IMPL(Method, EventType) \
    void StdioBusRawPipeHooks::Method(const EventType& ev) \
    { \
        if (!Enabled()) return; \
        int64_t start = GetMonotonicTimeUs(); \
        bool enqueued = TryEnqueue(ev); \
        int64_t latency = GetMonotonicTimeUs() - start; \
        m_stats.last_hook_latency_us.store(latency, std::memory_order_relaxed); \
        m_stats.events_total.fetch_add(1, std::memory_order_relaxed); \
        if (!enqueued) m_stats.events_dropped.fetch_add(1, std::memory_order_relaxed); \
    }

RAW_PIPE_HOOK_IMPL(OnMessage, MessageEvent)
RAW_PIPE_HOOK_IMPL(OnHeaders, HeadersEvent)
RAW_PIPE_HOOK_IMPL(OnBlockReceived, BlockReceivedEvent)
RAW_PIPE_HOOK_IMPL(OnBlockValidated, BlockValidatedEvent)
RAW_PIPE_HOOK_IMPL(OnTxAdmission, TxAdmissionEvent)
RAW_PIPE_HOOK_IMPL(OnMsgHandlerLoop, MsgHandlerLoopEvent)
RAW_PIPE_HOOK_IMPL(OnRpcCall, RpcCallEvent)
RAW_PIPE_HOOK_IMPL(OnBlockAnnounce, BlockAnnounceEvent)
RAW_PIPE_HOOK_IMPL(OnBlockRequestDecision, BlockRequestDecisionEvent)
RAW_PIPE_HOOK_IMPL(OnBlockInFlight, BlockInFlightEvent)
RAW_PIPE_HOOK_IMPL(OnStallerDetected, StallerDetectedEvent)
RAW_PIPE_HOOK_IMPL(OnCompactBlockDecision, CompactBlockDecisionEvent)
RAW_PIPE_HOOK_IMPL(OnBlockSourceResolved, BlockSourceResolvedEvent)
RAW_PIPE_HOOK_IMPL(OnTxRemoved, TxRemovedEvent)
RAW_PIPE_HOOK_IMPL(OnTxReplaced, TxReplacedEvent)
RAW_PIPE_HOOK_IMPL(OnTxRejected, TxRejectedEvent)
RAW_PIPE_HOOK_IMPL(OnUTXOCacheFlush, UTXOCacheFlushEvent)
RAW_PIPE_HOOK_IMPL(OnPeerConnection, PeerConnectionEvent)
RAW_PIPE_HOOK_IMPL(OnPeerClosed, PeerClosedEvent)
RAW_PIPE_HOOK_IMPL(OnPeerEvicted, PeerEvictedEvent)
RAW_PIPE_HOOK_IMPL(OnPeerMisbehaving, PeerMisbehavingEvent)
RAW_PIPE_HOOK_IMPL(OnOutboundMessage, OutboundMessageEvent)
RAW_PIPE_HOOK_IMPL(OnMempoolAdded, MempoolAddedEvent)
RAW_PIPE_HOOK_IMPL(OnBlockConnected, BlockConnectedEvent)
RAW_PIPE_HOOK_IMPL(OnUTXOCacheAdd, UTXOCacheAddEvent)
RAW_PIPE_HOOK_IMPL(OnUTXOCacheSpent, UTXOCacheSpentEvent)
RAW_PIPE_HOOK_IMPL(OnUTXOCacheUncache, UTXOCacheUncacheEvent)
RAW_PIPE_HOOK_IMPL(OnCoinSelectionSelectedCoins, CoinSelectionSelectedCoinsEvent)
RAW_PIPE_HOOK_IMPL(OnCoinSelectionNormalCreateTx, CoinSelectionNormalCreateTxEvent)
RAW_PIPE_HOOK_IMPL(OnCoinSelectionAttemptingAps, CoinSelectionAttemptingApsEvent)
RAW_PIPE_HOOK_IMPL(OnCoinSelectionApsCreateTx, CoinSelectionApsCreateTxEvent)

#undef RAW_PIPE_HOOK_IMPL

// ============================================================================
// Queue Operations (identical to StdioBusSdkHooks)
// ============================================================================

bool StdioBusRawPipeHooks::TryEnqueue(Event ev)
{
    std::unique_lock<std::mutex> lock(m_queue_mutex, std::try_to_lock);
    if (!lock.owns_lock()) {
        return false;
    }

    if (m_queue.size() >= m_queue_capacity) {
        return false;
    }

    m_queue.push(std::move(ev));
    m_stats.queue_depth.store(m_queue.size(), std::memory_order_relaxed);

    lock.unlock();
    m_queue_cv.notify_one();
    return true;
}

// ============================================================================
// Background Writer Thread
// ============================================================================

void StdioBusRawPipeHooks::WriterLoop()
{
    LogDebug(BCLog::NET, "raw_pipe: Writer thread started\n");

    while (!m_stop_requested.load(std::memory_order_relaxed)) {
        Event ev;

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

        // Serialize and write to all worker pipes
        std::string json = SerializeEvent(ev);
        if (WriteToWorkers(json)) {
            m_stats.events_written.fetch_add(1, std::memory_order_relaxed);
        } else {
            m_stats.write_errors.fetch_add(1, std::memory_order_relaxed);
        }
    }

    // Drain remaining events on shutdown
    {
        std::lock_guard<std::mutex> lock(m_queue_mutex);
        while (!m_queue.empty()) {
            Event ev = std::move(m_queue.front());
            m_queue.pop();
            std::string json = SerializeEvent(ev);
            WriteToWorkers(json);
        }
    }

    LogDebug(BCLog::NET, "raw_pipe: Writer thread stopped\n");
}

// ============================================================================
// Pipe Write (the actual IPC — just write() to fd)
// ============================================================================

bool StdioBusRawPipeHooks::WriteToWorkers(const std::string& json_line)
{
    // Append newline for NDJSON framing (same as stdio_bus protocol)
    std::string line = json_line + "\n";
    const char* data = line.data();
    size_t len = line.size();

    bool any_success = false;

    for (auto& wp : m_workers) {
        if (wp.write_fd < 0) continue;

        // Non-blocking write. If pipe buffer is full, we drop (fail-open).
        ssize_t written = write(wp.write_fd, data, len);
        if (written > 0) {
            any_success = true;
        } else if (written < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                // Pipe buffer full — drop event for this worker (fail-open)
                // This matches stdio_bus behavior: never block the hot path
            } else if (errno == EPIPE) {
                // Worker died — close fd
                close(wp.write_fd);
                wp.write_fd = -1;
                m_active_workers.fetch_sub(1, std::memory_order_relaxed);
                LogDebug(BCLog::NET, "raw_pipe: Worker '%s' pipe broken (EPIPE)\n",
                         wp.id);
            }
        }
    }

    return any_success;
}

// ============================================================================
// Serialization (IDENTICAL to StdioBusSdkHooks — same JSON format)
// ============================================================================

std::string StdioBusRawPipeHooks::SerializeEvent(const Event& ev) const
{
    // This produces the exact same JSON-RPC envelope as StdioBusSdkHooks.
    // Workers receive identical input regardless of transport.
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
        else if constexpr (std::is_same_v<T, MempoolAddedEvent>) {
            ss << "\"type\":\"mempool_added\","
               << "\"txid\":\"" << arg.txid.GetHex() << "\","
               << "\"vsize\":" << arg.vsize << ","
               << "\"fee\":" << arg.fee << ","
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
        else if constexpr (std::is_same_v<T, PeerConnectionEvent>) {
            ss << "\"type\":\"peer_connection\","
               << "\"peer_id\":" << arg.peer_id << ","
               << "\"addr\":\"" << arg.addr << "\","
               << "\"conn_type\":\"" << arg.conn_type << "\","
               << "\"inbound\":" << (arg.inbound ? "true" : "false") << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, PeerClosedEvent>) {
            ss << "\"type\":\"peer_closed\","
               << "\"peer_id\":" << arg.peer_id << ","
               << "\"addr\":\"" << arg.addr << "\","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, OutboundMessageEvent>) {
            ss << "\"type\":\"outbound_message\","
               << "\"peer_id\":" << arg.peer_id << ","
               << "\"addr\":\"" << arg.addr << "\","
               << "\"msg_type\":\"" << arg.msg_type << "\","
               << "\"size_bytes\":" << arg.size_bytes << ","
               << "\"timestamp_us\":" << arg.timestamp_us;
        }
        else {
            // Fallback for remaining event types — emit minimal JSON
            ss << "\"type\":\"other\"";
        }
    }, ev);

    ss << "}}";
    return ss.str();
}

// ============================================================================
// Statistics
// ============================================================================

StdioBusRawPipeHooks::Stats StdioBusRawPipeHooks::GetStats() const
{
    return Stats{
        m_stats.events_total.load(std::memory_order_relaxed),
        m_stats.events_dropped.load(std::memory_order_relaxed),
        m_stats.events_written.load(std::memory_order_relaxed),
        m_stats.write_errors.load(std::memory_order_relaxed),
        m_stats.last_hook_latency_us.load(std::memory_order_relaxed),
        m_stats.queue_depth.load(std::memory_order_relaxed),
    };
}

// ============================================================================
// Config Parsing
// ============================================================================

StdioBusRawPipeHooks::Config ParseRawPipeConfig(const std::string& config_path)
{
    StdioBusRawPipeHooks::Config config;

    // Minimal JSON parsing for the pools array format.
    // Format: {"pools": [{"id": "...", "command": "...", "args": [...]}]}
    // We reuse the same config format as stdiobus_trace.json for consistency.
    std::ifstream file(config_path);
    if (!file.is_open()) {
        LogError("raw_pipe: Cannot open config file: %s\n", config_path);
        return config;
    }

    std::string content((std::istreambuf_iterator<char>(file)),
                         std::istreambuf_iterator<char>());

    // Simple extraction — find "pools" array entries.
    // For production this would use a proper JSON parser, but Bitcoin Core
    // avoids heavy JSON dependencies in src/. This is sufficient for the
    // benchmark config format.
    //
    // We parse the same format that the Python benchmark runner writes:
    // {"pools": [{"id": "...", "command": "python3", "args": ["script.py", ...], "instances": 1}]}

    // Find each pool entry by looking for "id" fields
    size_t pos = 0;
    while ((pos = content.find("\"id\"", pos)) != std::string::npos) {
        StdioBusRawPipeHooks::WorkerConfig wc;

        // Extract id
        size_t colon = content.find(':', pos);
        size_t quote1 = content.find('"', colon + 1);
        size_t quote2 = content.find('"', quote1 + 1);
        if (quote1 != std::string::npos && quote2 != std::string::npos) {
            wc.id = content.substr(quote1 + 1, quote2 - quote1 - 1);
        }

        // Extract command
        size_t cmd_pos = content.find("\"command\"", pos);
        if (cmd_pos != std::string::npos && cmd_pos < pos + 500) {
            size_t c1 = content.find('"', content.find(':', cmd_pos) + 1);
            size_t c2 = content.find('"', c1 + 1);
            if (c1 != std::string::npos && c2 != std::string::npos) {
                wc.command = content.substr(c1 + 1, c2 - c1 - 1);
            }
        }

        // Extract args array
        size_t args_pos = content.find("\"args\"", pos);
        if (args_pos != std::string::npos && args_pos < pos + 500) {
            size_t bracket_open = content.find('[', args_pos);
            size_t bracket_close = content.find(']', bracket_open);
            if (bracket_open != std::string::npos && bracket_close != std::string::npos) {
                std::string args_str = content.substr(bracket_open + 1,
                                                      bracket_close - bracket_open - 1);
                // Parse quoted strings from args array
                size_t a_pos = 0;
                while ((a_pos = args_str.find('"', a_pos)) != std::string::npos) {
                    size_t a_end = args_str.find('"', a_pos + 1);
                    if (a_end != std::string::npos) {
                        wc.args.push_back(args_str.substr(a_pos + 1, a_end - a_pos - 1));
                        a_pos = a_end + 1;
                    } else {
                        break;
                    }
                }
            }
        }

        if (!wc.id.empty() && !wc.command.empty()) {
            config.workers.push_back(std::move(wc));
        }

        pos = quote2 != std::string::npos ? quote2 + 1 : pos + 4;
    }

    LogDebug(BCLog::NET, "raw_pipe: Parsed %zu workers from %s\n",
             config.workers.size(), config_path);
    return config;
}

std::shared_ptr<StdioBusRawPipeHooks> MakeRawPipeHooks(
    const std::string& config_path,
    bool shadow_mode)
{
    auto config = ParseRawPipeConfig(config_path);
    if (config.workers.empty()) {
        LogError("raw_pipe: No workers in config, cannot create hooks\n");
        return nullptr;
    }
    config.shadow_mode = shadow_mode;

    auto hooks = std::make_shared<StdioBusRawPipeHooks>(std::move(config));
    if (!hooks->Start()) {
        return nullptr;
    }
    return hooks;
}

} // namespace node
