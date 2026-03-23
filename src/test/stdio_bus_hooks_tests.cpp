// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include <node/stdio_bus_hooks.h>
#include <node/stdio_bus_observer.h>
#include <primitives/block.h>
#include <primitives/transaction.h>
#include <consensus/validation.h>
#include <test/util/setup_common.h>
#include <uint256.h>
#include <util/time.h>

#include <atomic>
#include <chrono>
#include <memory>
#include <set>
#include <thread>
#include <vector>

using namespace node;

BOOST_FIXTURE_TEST_SUITE(stdio_bus_hooks_tests, BasicTestingSetup)

// ============================================================================
// Test: NoOpStdioBusHooks does nothing and is always safe
// ============================================================================

BOOST_AUTO_TEST_CASE(noop_hooks_disabled)
{
    NoOpStdioBusHooks hooks;
    BOOST_CHECK(!hooks.Enabled());
    BOOST_CHECK(hooks.ShadowMode());
}

BOOST_AUTO_TEST_CASE(noop_hooks_safe_to_call)
{
    NoOpStdioBusHooks hooks;
    
    // All hook calls should be safe no-ops
    MessageEvent msg_ev{.peer_id = 1, .msg_type = "headers", .size_bytes = 100, .received_us = 0};
    hooks.OnMessage(msg_ev);
    
    HeadersEvent hdr_ev{.peer_id = 1, .count = 10, .first_prev_hash = uint256::ZERO, .received_us = 0};
    hooks.OnHeaders(hdr_ev);
    
    BlockReceivedEvent blk_recv_ev{.peer_id = 1, .hash = uint256::ZERO, .height = 100, .size_bytes = 1000, .tx_count = 5, .received_us = 0};
    hooks.OnBlockReceived(blk_recv_ev);
    
    BlockValidatedEvent blk_val_ev{.hash = uint256::ZERO, .height = 100, .tx_count = 5, .received_us = 0, .validated_us = 1000, .accepted = true, .reject_reason = {}};
    hooks.OnBlockValidated(blk_val_ev);
    
    TxAdmissionEvent tx_ev{.txid = uint256::ZERO, .wtxid = uint256::ZERO, .size_bytes = 250, .received_us = 0, .processed_us = 100, .accepted = true, .reject_reason = {}};
    hooks.OnTxAdmission(tx_ev);
    
    MsgHandlerLoopEvent loop_ev{.iteration = 1, .start_us = 0, .end_us = 100, .messages_processed = 5, .had_work = true};
    hooks.OnMsgHandlerLoop(loop_ev);
    
    RpcCallEvent rpc_ev{.method = "getblockchaininfo", .start_us = 0, .end_us = 500, .success = true};
    hooks.OnRpcCall(rpc_ev);
    
    // If we get here without crash/exception, test passes
    BOOST_CHECK(true);
}

// ============================================================================
// Test: StdioBusMode parsing
// ============================================================================

BOOST_AUTO_TEST_CASE(parse_stdio_bus_mode)
{
    BOOST_CHECK(ParseStdioBusMode("off") == StdioBusMode::Off);
    BOOST_CHECK(ParseStdioBusMode("shadow") == StdioBusMode::Shadow);
    BOOST_CHECK(ParseStdioBusMode("active") == StdioBusMode::Active);
    
    // Invalid values default to Off
    BOOST_CHECK(ParseStdioBusMode("") == StdioBusMode::Off);
    BOOST_CHECK(ParseStdioBusMode("invalid") == StdioBusMode::Off);
    BOOST_CHECK(ParseStdioBusMode("SHADOW") == StdioBusMode::Off); // case sensitive
}

BOOST_AUTO_TEST_CASE(stdio_bus_mode_to_string)
{
    BOOST_CHECK(StdioBusModeToString(StdioBusMode::Off) == "off");
    BOOST_CHECK(StdioBusModeToString(StdioBusMode::Shadow) == "shadow");
    BOOST_CHECK(StdioBusModeToString(StdioBusMode::Active) == "active");
}

// ============================================================================
// Test: GetMonotonicTimeUs returns increasing values
// ============================================================================

BOOST_AUTO_TEST_CASE(monotonic_time_increases)
{
    int64_t t1 = GetMonotonicTimeUs();
    std::this_thread::sleep_for(std::chrono::microseconds(100));
    int64_t t2 = GetMonotonicTimeUs();
    
    BOOST_CHECK(t2 > t1);
    BOOST_CHECK(t2 - t1 >= 100); // At least 100us passed
}

// ============================================================================
// Test: Recording hooks for verification
// ============================================================================

class RecordingStdioBusHooks : public StdioBusHooks {
public:
    bool Enabled() const override { return m_enabled; }
    bool ShadowMode() const override { return true; }
    
    void OnMessage(const MessageEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_messages.push_back(ev);
    }
    
    void OnHeaders(const HeadersEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_headers.push_back(ev);
    }
    
    void OnBlockReceived(const BlockReceivedEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_blocks_received.push_back(ev);
    }
    
    void OnBlockValidated(const BlockValidatedEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_blocks_validated.push_back(ev);
    }
    
    void OnTxAdmission(const TxAdmissionEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_tx_admissions.push_back(ev);
    }
    
    void OnMsgHandlerLoop(const MsgHandlerLoopEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_loop_events.push_back(ev);
    }
    
    void OnRpcCall(const RpcCallEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_rpc_calls.push_back(ev);
    }
    
    // Phase 5: P2P/RPC Degradation hooks (simplified)
    void OnRpcHttpEnqueue(const RpcHttpEnqueueEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_rpc_http_enqueue.push_back(ev);
    }
    
    void OnRpcHttpDispatch(const RpcHttpDispatchEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_rpc_http_dispatch.push_back(ev);
    }
    
    void OnRpcCallLifecycle(const RpcCallLifecycleEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_rpc_call_lifecycle.push_back(ev);
    }
    
    // Accessors
    size_t MessageCount() const { std::lock_guard<std::mutex> lock(m_mutex); return m_messages.size(); }
    size_t HeadersCount() const { std::lock_guard<std::mutex> lock(m_mutex); return m_headers.size(); }
    size_t BlocksReceivedCount() const { std::lock_guard<std::mutex> lock(m_mutex); return m_blocks_received.size(); }
    size_t BlocksValidatedCount() const { std::lock_guard<std::mutex> lock(m_mutex); return m_blocks_validated.size(); }
    size_t TxAdmissionsCount() const { std::lock_guard<std::mutex> lock(m_mutex); return m_tx_admissions.size(); }
    
    MessageEvent GetMessage(size_t i) const { std::lock_guard<std::mutex> lock(m_mutex); return m_messages.at(i); }
    HeadersEvent GetHeaders(size_t i) const { std::lock_guard<std::mutex> lock(m_mutex); return m_headers.at(i); }
    BlockValidatedEvent GetBlockValidated(size_t i) const { std::lock_guard<std::mutex> lock(m_mutex); return m_blocks_validated.at(i); }
    
    bool m_enabled{true};
    
private:
    mutable std::mutex m_mutex;
    std::vector<MessageEvent> m_messages;
    std::vector<HeadersEvent> m_headers;
    std::vector<BlockReceivedEvent> m_blocks_received;
    std::vector<BlockValidatedEvent> m_blocks_validated;
    std::vector<TxAdmissionEvent> m_tx_admissions;
    std::vector<MsgHandlerLoopEvent> m_loop_events;
    std::vector<RpcCallEvent> m_rpc_calls;
    // Phase 5 (simplified)
    std::vector<RpcHttpEnqueueEvent> m_rpc_http_enqueue;
    std::vector<RpcHttpDispatchEvent> m_rpc_http_dispatch;
    std::vector<RpcCallLifecycleEvent> m_rpc_call_lifecycle;
};

BOOST_AUTO_TEST_CASE(recording_hooks_capture_events)
{
    auto hooks = std::make_shared<RecordingStdioBusHooks>();
    
    // Fire some events
    MessageEvent msg1{.peer_id = 1, .msg_type = "headers", .size_bytes = 100, .received_us = 1000};
    MessageEvent msg2{.peer_id = 2, .msg_type = "block", .size_bytes = 500000, .received_us = 2000};
    hooks->OnMessage(msg1);
    hooks->OnMessage(msg2);
    
    HeadersEvent hdr{.peer_id = 1, .count = 2000, .first_prev_hash = uint256::ONE, .received_us = 1500};
    hooks->OnHeaders(hdr);
    
    BOOST_CHECK_EQUAL(hooks->MessageCount(), 2);
    BOOST_CHECK_EQUAL(hooks->HeadersCount(), 1);
    
    // Verify captured data
    auto captured_msg1 = hooks->GetMessage(0);
    BOOST_CHECK_EQUAL(captured_msg1.peer_id, 1);
    BOOST_CHECK_EQUAL(captured_msg1.msg_type, "headers");
    BOOST_CHECK_EQUAL(captured_msg1.size_bytes, 100);
    
    auto captured_hdr = hooks->GetHeaders(0);
    BOOST_CHECK_EQUAL(captured_hdr.count, 2000);
    BOOST_CHECK(captured_hdr.first_prev_hash == uint256::ONE);
}

BOOST_AUTO_TEST_CASE(disabled_hooks_not_called)
{
    auto hooks = std::make_shared<RecordingStdioBusHooks>();
    hooks->m_enabled = false;
    
    BOOST_CHECK(!hooks->Enabled());
    
    // Even if we call hooks, they should check Enabled() first
    // This test verifies the pattern used in net_processing.cpp
    if (hooks->Enabled()) {
        MessageEvent msg{.peer_id = 1, .msg_type = "test", .size_bytes = 10, .received_us = 0};
        hooks->OnMessage(msg);
    }
    
    BOOST_CHECK_EQUAL(hooks->MessageCount(), 0);
}

// ============================================================================
// Test: Thread safety of hooks
// ============================================================================

BOOST_AUTO_TEST_CASE(hooks_thread_safe)
{
    auto hooks = std::make_shared<RecordingStdioBusHooks>();
    constexpr int NUM_THREADS = 4;
    constexpr int EVENTS_PER_THREAD = 1000;
    
    std::vector<std::thread> threads;
    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&hooks, t]() {
            for (int i = 0; i < EVENTS_PER_THREAD; ++i) {
                MessageEvent ev{
                    .peer_id = t,
                    .msg_type = "test",
                    .size_bytes = static_cast<size_t>(i),
                    .received_us = GetMonotonicTimeUs()
                };
                hooks->OnMessage(ev);
            }
        });
    }
    
    for (auto& th : threads) {
        th.join();
    }
    
    BOOST_CHECK_EQUAL(hooks->MessageCount(), NUM_THREADS * EVENTS_PER_THREAD);
}

// ============================================================================
// Test: StdioBusValidationObserver
// ============================================================================

BOOST_FIXTURE_TEST_CASE(validation_observer_disabled_when_hooks_disabled, ChainTestingSetup)
{
    auto hooks = std::make_shared<RecordingStdioBusHooks>();
    hooks->m_enabled = false;
    
    StdioBusValidationObserver observer(hooks);
    BOOST_CHECK(!observer.Enabled());
}

BOOST_FIXTURE_TEST_CASE(validation_observer_enabled_when_hooks_enabled, ChainTestingSetup)
{
    auto hooks = std::make_shared<RecordingStdioBusHooks>();
    hooks->m_enabled = true;
    
    StdioBusValidationObserver observer(hooks);
    BOOST_CHECK(observer.Enabled());
}

// ============================================================================
// Test: Event struct field validation
// ============================================================================

BOOST_AUTO_TEST_CASE(message_event_fields)
{
    MessageEvent ev{
        .peer_id = 42,
        .msg_type = "headers",
        .size_bytes = 162000,
        .received_us = 1234567890123
    };
    
    BOOST_CHECK_EQUAL(ev.peer_id, 42);
    BOOST_CHECK_EQUAL(ev.msg_type, "headers");
    BOOST_CHECK_EQUAL(ev.size_bytes, 162000);
    BOOST_CHECK_EQUAL(ev.received_us, 1234567890123);
}

BOOST_AUTO_TEST_CASE(block_validated_event_fields)
{
    // Use a constant hash
    uint256 hash = uint256::ONE;
    
    BlockValidatedEvent ev{
        .hash = hash,
        .height = 800000,
        .tx_count = 3500,
        .received_us = 1000000,
        .validated_us = 1500000,
        .accepted = true,
        .reject_reason = {}
    };
    
    BOOST_CHECK(ev.hash == hash);
    BOOST_CHECK_EQUAL(ev.height, 800000);
    BOOST_CHECK_EQUAL(ev.tx_count, 3500);
    BOOST_CHECK_EQUAL(ev.validated_us - ev.received_us, 500000); // 500ms validation time
    BOOST_CHECK(ev.accepted);
}

BOOST_AUTO_TEST_CASE(tx_admission_event_fields)
{
    uint256 txid = uint256::ONE;
    uint256 wtxid = uint256::ZERO;
    
    TxAdmissionEvent ev{
        .txid = txid,
        .wtxid = wtxid,
        .size_bytes = 250,
        .received_us = 1000,
        .processed_us = 1100,
        .accepted = false,
        .reject_reason = "insufficient fee"
    };
    
    BOOST_CHECK(ev.txid == txid);
    BOOST_CHECK(ev.wtxid == wtxid);
    BOOST_CHECK_EQUAL(ev.size_bytes, 250);
    BOOST_CHECK(!ev.accepted);
    BOOST_CHECK_EQUAL(ev.reject_reason, "insufficient fee");
}

// ============================================================================
// Test: Latency measurement helper
// ============================================================================

BOOST_AUTO_TEST_CASE(latency_measurement)
{
    int64_t start = GetMonotonicTimeUs();
    
    // Simulate some work
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
    
    int64_t end = GetMonotonicTimeUs();
    int64_t latency_us = end - start;
    
    // Should be at least 1ms (1000us)
    BOOST_CHECK(latency_us >= 1000);
    // Should be less than 100ms (sanity check)
    BOOST_CHECK(latency_us < 100000);
}

// ============================================================================
// Phase 5: P2P/RPC Degradation Tests (#18678) - Simplified
// ============================================================================

BOOST_AUTO_TEST_CASE(generate_request_id_unique)
{
    std::set<int64_t> ids;
    constexpr int NUM_IDS = 1000;
    
    for (int i = 0; i < NUM_IDS; ++i) {
        int64_t id = GenerateRequestId();
        BOOST_CHECK(ids.find(id) == ids.end()); // Should be unique
        ids.insert(id);
    }
    
    BOOST_CHECK_EQUAL(ids.size(), NUM_IDS);
}

BOOST_AUTO_TEST_CASE(generate_request_id_thread_safe)
{
    std::mutex ids_mutex;
    std::set<int64_t> ids;
    constexpr int NUM_THREADS = 4;
    constexpr int IDS_PER_THREAD = 1000;
    
    std::vector<std::thread> threads;
    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&ids, &ids_mutex]() {
            for (int i = 0; i < IDS_PER_THREAD; ++i) {
                int64_t id = GenerateRequestId();
                std::lock_guard<std::mutex> lock(ids_mutex);
                ids.insert(id);
            }
        });
    }
    
    for (auto& th : threads) {
        th.join();
    }
    
    // All IDs should be unique
    BOOST_CHECK_EQUAL(ids.size(), NUM_THREADS * IDS_PER_THREAD);
}

BOOST_AUTO_TEST_CASE(rpc_http_enqueue_event_fields)
{
    RpcHttpEnqueueEvent ev{
        .request_id = 12345,
        .uri = "/",
        .peer_addr = "127.0.0.1:8332",
        .received_us = 1000000,
        .queue_depth = 10,
        .max_queue_depth = 64,
        .admitted = true
    };
    
    BOOST_CHECK_EQUAL(ev.request_id, 12345);
    BOOST_CHECK_EQUAL(ev.uri, "/");
    BOOST_CHECK_EQUAL(ev.peer_addr, "127.0.0.1:8332");
    BOOST_CHECK_EQUAL(ev.queue_depth, 10);
    BOOST_CHECK_EQUAL(ev.max_queue_depth, 64);
    BOOST_CHECK(ev.admitted);
}

BOOST_AUTO_TEST_CASE(rpc_http_dispatch_event_fields)
{
    RpcHttpDispatchEvent ev{
        .request_id = 12345,
        .enqueued_us = 1000000,
        .dispatched_us = 1001000
    };
    
    BOOST_CHECK_EQUAL(ev.request_id, 12345);
    BOOST_CHECK_EQUAL(ev.dispatched_us - ev.enqueued_us, 1000); // 1ms queue wait
}

BOOST_AUTO_TEST_CASE(rpc_call_lifecycle_event_fields)
{
    RpcCallLifecycleEvent ev{
        .request_id = 12345,
        .method = "getblockchaininfo",
        .peer_addr = "127.0.0.1:8332",
        .exec_start_us = 1001200,
        .exec_end_us = 1002000,
        .success = true,
        .http_status = 200,
        .response_size = 1024
    };
    
    BOOST_CHECK_EQUAL(ev.method, "getblockchaininfo");
    BOOST_CHECK(ev.success);
    BOOST_CHECK_EQUAL(ev.http_status, 200);
    
    // Calculate exec time
    int64_t exec_time = ev.exec_end_us - ev.exec_start_us;
    BOOST_CHECK_EQUAL(exec_time, 800);
}

BOOST_AUTO_TEST_CASE(request_id_correlation)
{
    // Test that same request_id can be used across all three events
    int64_t request_id = GenerateRequestId();
    
    RpcHttpEnqueueEvent enqueue_ev{
        .request_id = request_id,
        .uri = "/",
        .peer_addr = "127.0.0.1:8332",
        .received_us = 1000000,
        .queue_depth = 5,
        .max_queue_depth = 64,
        .admitted = true
    };
    
    RpcHttpDispatchEvent dispatch_ev{
        .request_id = request_id,
        .enqueued_us = 1000000,
        .dispatched_us = 1001000
    };
    
    RpcCallLifecycleEvent lifecycle_ev{
        .request_id = request_id,
        .method = "getblockchaininfo",
        .peer_addr = "127.0.0.1:8332",
        .exec_start_us = 1001100,
        .exec_end_us = 1002000,
        .success = true,
        .http_status = 200,
        .response_size = 1024
    };
    
    // All events should have same request_id
    BOOST_CHECK_EQUAL(enqueue_ev.request_id, dispatch_ev.request_id);
    BOOST_CHECK_EQUAL(dispatch_ev.request_id, lifecycle_ev.request_id);
    
    // Timestamps should be monotonic: enqueue <= dispatch <= exec_start <= exec_end
    BOOST_CHECK(enqueue_ev.received_us <= dispatch_ev.dispatched_us);
    BOOST_CHECK(dispatch_ev.dispatched_us <= lifecycle_ev.exec_start_us);
    BOOST_CHECK(lifecycle_ev.exec_start_us <= lifecycle_ev.exec_end_us);
}

BOOST_AUTO_TEST_CASE(noop_hooks_phase5_safe_to_call)
{
    NoOpStdioBusHooks hooks;
    
    // All Phase 5 hook calls should be safe no-ops
    RpcHttpEnqueueEvent enqueue_ev{
        .request_id = 1, .uri = "/", .peer_addr = "127.0.0.1",
        .received_us = 0, .queue_depth = 0, .max_queue_depth = 64,
        .admitted = true
    };
    hooks.OnRpcHttpEnqueue(enqueue_ev);
    
    RpcHttpDispatchEvent dispatch_ev{
        .request_id = 1, .enqueued_us = 0, .dispatched_us = 100
    };
    hooks.OnRpcHttpDispatch(dispatch_ev);
    
    RpcCallLifecycleEvent lifecycle_ev{
        .request_id = 1, .method = "test", .peer_addr = "127.0.0.1",
        .exec_start_us = 0, .exec_end_us = 100,
        .success = true, .http_status = 200, .response_size = 100
    };
    hooks.OnRpcCallLifecycle(lifecycle_ev);
    
    // If we get here without crash/exception, test passes
    BOOST_CHECK(true);
}

// ============================================================================
// Phase 5b: RpcLoadMonitor Backpressure Tests (#18678)
// ============================================================================

BOOST_AUTO_TEST_SUITE_END()

// Include RpcLoadMonitor for backpressure tests
#include <node/rpc_load_monitor.h>

BOOST_AUTO_TEST_SUITE(rpc_load_monitor_tests)

BOOST_AUTO_TEST_CASE(initial_state_is_normal)
{
    node::AtomicRpcLoadMonitor monitor;
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::NORMAL);
    BOOST_CHECK_EQUAL(monitor.GetQueueDepth(), 0);
    BOOST_CHECK_EQUAL(monitor.GetQueueCapacity(), 0);
}

BOOST_AUTO_TEST_CASE(state_transitions_normal_to_elevated)
{
    node::AtomicRpcLoadMonitor monitor;
    
    // Below threshold - stay NORMAL
    monitor.OnQueueDepthSample(70, 100);  // 70%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::NORMAL);
    
    // At threshold - transition to ELEVATED
    monitor.OnQueueDepthSample(75, 100);  // 75%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::ELEVATED);
}

BOOST_AUTO_TEST_CASE(state_transitions_normal_to_critical)
{
    node::AtomicRpcLoadMonitor monitor;
    
    // Jump directly to CRITICAL
    monitor.OnQueueDepthSample(90, 100);  // 90%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::CRITICAL);
}

BOOST_AUTO_TEST_CASE(state_transitions_elevated_to_critical)
{
    node::AtomicRpcLoadMonitor monitor;
    
    // First go to ELEVATED
    monitor.OnQueueDepthSample(80, 100);  // 80%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::ELEVATED);
    
    // Then to CRITICAL
    monitor.OnQueueDepthSample(95, 100);  // 95%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::CRITICAL);
}

BOOST_AUTO_TEST_CASE(hysteresis_elevated_to_normal)
{
    node::AtomicRpcLoadMonitor monitor;
    
    // Go to ELEVATED
    monitor.OnQueueDepthSample(80, 100);  // 80%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::ELEVATED);
    
    // Drop to 60% - still ELEVATED (hysteresis)
    monitor.OnQueueDepthSample(60, 100);  // 60%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::ELEVATED);
    
    // Drop to 50% - still ELEVATED (at threshold)
    monitor.OnQueueDepthSample(50, 100);  // 50%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::ELEVATED);
    
    // Drop below 50% - back to NORMAL
    monitor.OnQueueDepthSample(49, 100);  // 49%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::NORMAL);
}

BOOST_AUTO_TEST_CASE(hysteresis_critical_to_elevated)
{
    node::AtomicRpcLoadMonitor monitor;
    
    // Go to CRITICAL
    monitor.OnQueueDepthSample(95, 100);  // 95%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::CRITICAL);
    
    // Drop to 75% - still CRITICAL (hysteresis)
    monitor.OnQueueDepthSample(75, 100);  // 75%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::CRITICAL);
    
    // Drop to 70% - still CRITICAL (at threshold)
    monitor.OnQueueDepthSample(70, 100);  // 70%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::CRITICAL);
    
    // Drop below 70% - back to ELEVATED
    monitor.OnQueueDepthSample(69, 100);  // 69%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::ELEVATED);
}

BOOST_AUTO_TEST_CASE(full_cycle_normal_critical_normal)
{
    node::AtomicRpcLoadMonitor monitor;
    
    // Start NORMAL
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::NORMAL);
    
    // Spike to CRITICAL
    monitor.OnQueueDepthSample(95, 100);
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::CRITICAL);
    
    // Drop to ELEVATED
    monitor.OnQueueDepthSample(65, 100);
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::ELEVATED);
    
    // Drop to NORMAL
    monitor.OnQueueDepthSample(40, 100);
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::NORMAL);
}

BOOST_AUTO_TEST_CASE(zero_capacity_safe)
{
    node::AtomicRpcLoadMonitor monitor;
    
    // Zero capacity should not crash or change state
    monitor.OnQueueDepthSample(10, 0);
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::NORMAL);
    BOOST_CHECK_EQUAL(monitor.GetQueueDepth(), 10);
    BOOST_CHECK_EQUAL(monitor.GetQueueCapacity(), 0);
}

BOOST_AUTO_TEST_CASE(negative_capacity_safe)
{
    node::AtomicRpcLoadMonitor monitor;
    
    // Negative capacity should not crash
    monitor.OnQueueDepthSample(10, -1);
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::NORMAL);
}

BOOST_AUTO_TEST_CASE(custom_thresholds)
{
    node::AtomicRpcLoadMonitor::Config cfg{
        .elevated_ratio = 0.50,    // Enter ELEVATED at 50%
        .critical_ratio = 0.80,    // Enter CRITICAL at 80%
        .leave_elevated = 0.30,    // Leave ELEVATED at 30%
        .leave_critical = 0.60     // Leave CRITICAL at 60%
    };
    node::AtomicRpcLoadMonitor monitor(cfg);
    
    // Test custom thresholds
    monitor.OnQueueDepthSample(50, 100);  // 50%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::ELEVATED);
    
    monitor.OnQueueDepthSample(80, 100);  // 80%
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::CRITICAL);
    
    monitor.OnQueueDepthSample(59, 100);  // 59% - back to ELEVATED
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::ELEVATED);
    
    monitor.OnQueueDepthSample(29, 100);  // 29% - back to NORMAL
    BOOST_CHECK(monitor.GetState() == node::RpcLoadState::NORMAL);
}

BOOST_AUTO_TEST_CASE(thread_safety)
{
    node::AtomicRpcLoadMonitor monitor;
    std::atomic<bool> running{true};
    constexpr int NUM_READERS = 4;
    constexpr int NUM_WRITERS = 2;
    constexpr int ITERATIONS = 10000;
    
    std::vector<std::thread> threads;
    
    // Writer threads
    for (int w = 0; w < NUM_WRITERS; ++w) {
        threads.emplace_back([&monitor, &running]() {
            for (int i = 0; i < ITERATIONS && running; ++i) {
                int depth = (i % 100);  // Oscillate 0-99
                monitor.OnQueueDepthSample(depth, 100);
            }
        });
    }
    
    // Reader threads
    for (int r = 0; r < NUM_READERS; ++r) {
        threads.emplace_back([&monitor, &running]() {
            for (int i = 0; i < ITERATIONS && running; ++i) {
                auto state = monitor.GetState();
                auto depth = monitor.GetQueueDepth();
                auto cap = monitor.GetQueueCapacity();
                // Just read - no crashes
                (void)state;
                (void)depth;
                (void)cap;
            }
        });
    }
    
    for (auto& th : threads) {
        th.join();
    }
    
    // If we get here without crash, test passes
    BOOST_CHECK(true);
}

BOOST_AUTO_TEST_CASE(depth_and_capacity_tracking)
{
    node::AtomicRpcLoadMonitor monitor;
    
    monitor.OnQueueDepthSample(42, 100);
    BOOST_CHECK_EQUAL(monitor.GetQueueDepth(), 42);
    BOOST_CHECK_EQUAL(monitor.GetQueueCapacity(), 100);
    
    monitor.OnQueueDepthSample(17, 64);
    BOOST_CHECK_EQUAL(monitor.GetQueueDepth(), 17);
    BOOST_CHECK_EQUAL(monitor.GetQueueCapacity(), 64);
}

BOOST_AUTO_TEST_SUITE_END()
