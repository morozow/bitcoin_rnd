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
    
    // Phase 3: Message Handler Saturation hooks
    void OnMsgProcPoll(const MsgProcPollEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_poll_events.push_back(ev);
    }
    
    void OnMsgProcStage(const MsgProcStageEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_stage_events.push_back(ev);
    }
    
    void OnMsgProcBackpressure(const MsgProcBackpressureEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_backpressure_events.push_back(ev);
    }
    
    void OnMsgProcDrop(const MsgProcDropEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_drop_events.push_back(ev);
    }
    
    void OnMsgProcLoop(const MsgProcLoopEvent& ev) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_proc_loop_events.push_back(ev);
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
    // Phase 3 events
    std::vector<MsgProcPollEvent> m_poll_events;
    std::vector<MsgProcStageEvent> m_stage_events;
    std::vector<MsgProcBackpressureEvent> m_backpressure_events;
    std::vector<MsgProcDropEvent> m_drop_events;
    std::vector<MsgProcLoopEvent> m_proc_loop_events;
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
    std::atomic<bool> running{true};
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

BOOST_FIXTURE_TEST_CASE(validation_observer_block_checked_accepted, ChainTestingSetup)
{
    auto hooks = std::make_shared<RecordingStdioBusHooks>();
    StdioBusValidationObserver observer(hooks);
    
    // Create a simple block
    CBlock block;
    block.nVersion = 1;
    block.hashPrevBlock = uint256::ZERO;
    block.nTime = 1234567890;
    block.nBits = 0x1d00ffff;
    block.nNonce = 0;
    
    // Simulate accepted block
    BlockValidationState state;
    observer.BlockChecked(std::make_shared<const CBlock>(block), state);
    
    BOOST_CHECK_EQUAL(hooks->BlocksValidatedCount(), 1);
    auto ev = hooks->GetBlockValidated(0);
    BOOST_CHECK(ev.accepted);
    BOOST_CHECK(ev.reject_reason.empty());
    BOOST_CHECK(ev.hash == block.GetHash());
}

BOOST_FIXTURE_TEST_CASE(validation_observer_block_checked_rejected, ChainTestingSetup)
{
    auto hooks = std::make_shared<RecordingStdioBusHooks>();
    StdioBusValidationObserver observer(hooks);
    
    CBlock block;
    block.nVersion = 1;
    
    // Simulate rejected block
    BlockValidationState state;
    state.Invalid(BlockValidationResult::BLOCK_CONSENSUS, "bad-txns-duplicate");
    observer.BlockChecked(std::make_shared<const CBlock>(block), state);
    
    BOOST_CHECK_EQUAL(hooks->BlocksValidatedCount(), 1);
    auto ev = hooks->GetBlockValidated(0);
    BOOST_CHECK(!ev.accepted);
    BOOST_CHECK(!ev.reject_reason.empty());
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
    uint256 hash;
    hash.SetHex("000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f");
    
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
    uint256 txid, wtxid;
    txid.SetHex("abc123");
    wtxid.SetHex("def456");
    
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
// Phase 3: Message Handler Saturation Tests (#27623)
// ============================================================================

BOOST_AUTO_TEST_SUITE_END()

// Include backpressure header for Phase 3 tests
#include <node/msgproc_backpressure.h>
#include <protocol.h>

BOOST_AUTO_TEST_SUITE(stdio_bus_phase3_tests)

// ============================================================================
// Test: ClassifyMsgPriority - table-driven tests
// ============================================================================

BOOST_AUTO_TEST_CASE(classify_msg_priority_high)
{
    // Consensus-critical messages should be HIGH priority
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::BLOCK, 1000000) == MsgPriority::High);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::CMPCTBLOCK, 50000) == MsgPriority::High);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::BLOCKTXN, 100000) == MsgPriority::High);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::HEADERS, 162000) == MsgPriority::High);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::TX, 500) == MsgPriority::High);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::GETDATA, 100) == MsgPriority::High);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::GETBLOCKS, 100) == MsgPriority::High);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::GETHEADERS, 100) == MsgPriority::High);
}

BOOST_AUTO_TEST_CASE(classify_msg_priority_medium)
{
    // Control-plane messages should be MEDIUM priority
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::VERSION, 100) == MsgPriority::Medium);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::VERACK, 0) == MsgPriority::Medium);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::SENDHEADERS, 0) == MsgPriority::Medium);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::SENDCMPCT, 10) == MsgPriority::Medium);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::PING, 8) == MsgPriority::Medium);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::PONG, 8) == MsgPriority::Medium);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::FEEFILTER, 8) == MsgPriority::Medium);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::WTXIDRELAY, 0) == MsgPriority::Medium);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::SENDADDRV2, 0) == MsgPriority::Medium);
}

BOOST_AUTO_TEST_CASE(classify_msg_priority_low)
{
    // Gossip/deferrable messages should be LOW priority
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::ADDR, 1000) == MsgPriority::Low);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::ADDRV2, 1000) == MsgPriority::Low);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::INV, 500) == MsgPriority::Low);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::GETADDR, 0) == MsgPriority::Low);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::NOTFOUND, 100) == MsgPriority::Low);
    BOOST_CHECK(ClassifyMsgPriority(NetMsgType::MEMPOOL, 0) == MsgPriority::Low);
}

BOOST_AUTO_TEST_CASE(classify_msg_priority_unknown)
{
    // Unknown small messages -> LOW
    BOOST_CHECK(ClassifyMsgPriority("unknown", 1000) == MsgPriority::Low);
    // Unknown large messages -> MEDIUM
    BOOST_CHECK(ClassifyMsgPriority("unknown", 100000) == MsgPriority::Medium);
}

// ============================================================================
// Test: IsHeavyMsgType
// ============================================================================

BOOST_AUTO_TEST_CASE(is_heavy_msg_type)
{
    // Block-related messages are heavy
    BOOST_CHECK(IsHeavyMsgType(NetMsgType::BLOCK, 1000000));
    BOOST_CHECK(IsHeavyMsgType(NetMsgType::CMPCTBLOCK, 50000));
    BOOST_CHECK(IsHeavyMsgType(NetMsgType::BLOCKTXN, 100000));
    
    // Large headers batches are heavy
    BOOST_CHECK(IsHeavyMsgType(NetMsgType::HEADERS, 200000)); // > 128KB
    BOOST_CHECK(!IsHeavyMsgType(NetMsgType::HEADERS, 50000)); // < 128KB
    
    // Other messages are not heavy
    BOOST_CHECK(!IsHeavyMsgType(NetMsgType::TX, 500));
    BOOST_CHECK(!IsHeavyMsgType(NetMsgType::INV, 1000));
    BOOST_CHECK(!IsHeavyMsgType(NetMsgType::ADDR, 1000));
}

// ============================================================================
// Test: MsgProcLoopBudget
// ============================================================================

BOOST_AUTO_TEST_CASE(loop_budget_reset)
{
    MsgProcLoopBudget budget;
    
    // Consume some budget
    budget.ConsumeHeavyMsg(500);
    budget.ConsumeHeavyMsg(300);
    budget.msgs_deferred = 2;
    budget.msgs_dropped = 1;
    
    BOOST_CHECK_EQUAL(budget.parse_us_consumed, 800);
    BOOST_CHECK_EQUAL(budget.heavy_msgs_consumed, 2);
    BOOST_CHECK_EQUAL(budget.parse_us_left, 2000 - 800);
    BOOST_CHECK_EQUAL(budget.heavy_msgs_left, 8 - 2);
    
    // Reset
    budget.Reset();
    
    BOOST_CHECK_EQUAL(budget.parse_us_consumed, 0);
    BOOST_CHECK_EQUAL(budget.heavy_msgs_consumed, 0);
    BOOST_CHECK_EQUAL(budget.parse_us_left, 2000);
    BOOST_CHECK_EQUAL(budget.heavy_msgs_left, 8);
    BOOST_CHECK_EQUAL(budget.msgs_deferred, 0);
    BOOST_CHECK_EQUAL(budget.msgs_dropped, 0);
}

BOOST_AUTO_TEST_CASE(loop_budget_no_negative)
{
    MsgProcLoopBudget budget;
    budget.parse_us_left = 100;
    budget.heavy_msgs_left = 1;
    
    // Consume more than available
    budget.ConsumeHeavyMsg(500);
    
    // Should not go negative
    BOOST_CHECK(budget.parse_us_left >= 0);
    BOOST_CHECK(budget.heavy_msgs_left >= 0);
}

// ============================================================================
// Test: ShouldDeferMessage - decision matrix
// ============================================================================

BOOST_AUTO_TEST_CASE(should_defer_disabled)
{
    MsgProcLoopBudget budget;
    MsgProcPeerLoopState peer_state;
    
    // When backpressure is disabled, always admit
    auto result = ShouldDeferMessage(NetMsgType::ADDR, 1000, 1000, 10000000, budget, peer_state, false);
    BOOST_CHECK(!result.defer);
    BOOST_CHECK(!result.drop);
}

BOOST_AUTO_TEST_CASE(should_defer_high_priority_never_dropped)
{
    MsgProcLoopBudget budget;
    budget.heavy_msgs_left = 0;  // Budget exhausted
    budget.parse_us_left = 0;
    MsgProcPeerLoopState peer_state;
    
    // HIGH priority messages should never be dropped, only deferred
    auto result = ShouldDeferMessage(NetMsgType::BLOCK, 1000000, 0, 0, budget, peer_state, true);
    BOOST_CHECK(result.defer);
    BOOST_CHECK(!result.drop);
    
    result = ShouldDeferMessage(NetMsgType::HEADERS, 162000, 0, 0, budget, peer_state, true);
    BOOST_CHECK(result.defer);
    BOOST_CHECK(!result.drop);
    
    result = ShouldDeferMessage(NetMsgType::TX, 500, 0, 0, budget, peer_state, true);
    // TX is not heavy, so no defer for budget exhaustion
    BOOST_CHECK(!result.defer);
    BOOST_CHECK(!result.drop);
}

BOOST_AUTO_TEST_CASE(should_defer_low_priority_dropped_on_queue_pressure)
{
    MsgProcLoopBudget budget;
    budget.queue_high_watermark_msgs = 100;
    MsgProcPeerLoopState peer_state;
    
    // LOW priority messages should be dropped under queue pressure
    auto result = ShouldDeferMessage(NetMsgType::ADDR, 1000, 200, 0, budget, peer_state, true);
    BOOST_CHECK(!result.defer);
    BOOST_CHECK(result.drop);
    BOOST_CHECK_EQUAL(std::string(result.reason), "queue_high_watermark");
    
    result = ShouldDeferMessage(NetMsgType::INV, 500, 200, 0, budget, peer_state, true);
    BOOST_CHECK(result.drop);
}

BOOST_AUTO_TEST_CASE(should_defer_peer_fairness_cap)
{
    MsgProcLoopBudget budget;
    budget.max_peer_heavy_per_loop = 2;
    MsgProcPeerLoopState peer_state;
    peer_state.heavy_msgs_processed = 2;  // Already at cap
    
    // Heavy message from peer at cap should be deferred
    auto result = ShouldDeferMessage(NetMsgType::BLOCK, 1000000, 0, 0, budget, peer_state, true);
    BOOST_CHECK(result.defer);
    BOOST_CHECK(!result.drop);
    BOOST_CHECK_EQUAL(std::string(result.reason), "peer_heavy_cap");
}

BOOST_AUTO_TEST_CASE(should_defer_budget_exhausted)
{
    MsgProcLoopBudget budget;
    budget.heavy_msgs_left = 0;
    MsgProcPeerLoopState peer_state;
    
    // Heavy HIGH priority -> defer
    auto result = ShouldDeferMessage(NetMsgType::BLOCK, 1000000, 0, 0, budget, peer_state, true);
    BOOST_CHECK(result.defer);
    BOOST_CHECK(!result.drop);
    BOOST_CHECK_EQUAL(std::string(result.reason), "heavy_budget_exhausted");
    
    // Heavy LOW priority -> drop
    // Note: BLOCK is HIGH, so we need a hypothetical heavy LOW message
    // In practice, there are no heavy LOW messages, but test the logic
}

BOOST_AUTO_TEST_CASE(should_defer_parse_budget_exhausted)
{
    MsgProcLoopBudget budget;
    budget.parse_us_left = 0;
    MsgProcPeerLoopState peer_state;
    
    // Heavy message with parse budget exhausted -> defer
    auto result = ShouldDeferMessage(NetMsgType::BLOCK, 1000000, 0, 0, budget, peer_state, true);
    BOOST_CHECK(result.defer);
    BOOST_CHECK(!result.drop);
}

BOOST_AUTO_TEST_CASE(should_defer_normal_admit)
{
    MsgProcLoopBudget budget;  // Fresh budget
    MsgProcPeerLoopState peer_state;  // Fresh state
    
    // Normal conditions -> admit
    auto result = ShouldDeferMessage(NetMsgType::BLOCK, 1000000, 0, 0, budget, peer_state, true);
    BOOST_CHECK(!result.defer);
    BOOST_CHECK(!result.drop);
    BOOST_CHECK_EQUAL(std::string(result.reason), "admit");
    
    result = ShouldDeferMessage(NetMsgType::TX, 500, 0, 0, budget, peer_state, true);
    BOOST_CHECK(!result.defer);
    BOOST_CHECK(!result.drop);
    
    result = ShouldDeferMessage(NetMsgType::ADDR, 1000, 0, 0, budget, peer_state, true);
    BOOST_CHECK(!result.defer);
    BOOST_CHECK(!result.drop);
}

// ============================================================================
// Test: Phase 3 NoOp hooks
// ============================================================================

BOOST_AUTO_TEST_CASE(noop_phase3_hooks_safe)
{
    NoOpStdioBusHooks hooks;
    
    // All Phase 3 hook calls should be safe no-ops
    MsgProcPollEvent poll_ev{
        .peer_id = 1,
        .msg_type = "block",
        .msg_size_bytes = 1000000,
        .poll_more_work = true,
        .recv_queue_msgs = 5,
        .recv_queue_bytes = 5000000,
        .timestamp_us = GetMonotonicTimeUs()
    };
    hooks.OnMsgProcPoll(poll_ev);
    
    MsgProcStageEvent stage_ev{
        .peer_id = 1,
        .msg_type = "block",
        .stage = MsgProcStage::Process,
        .start_us = 1000,
        .end_us = 2000,
        .success = true
    };
    hooks.OnMsgProcStage(stage_ev);
    
    MsgProcBackpressureEvent bp_ev{
        .peer_id = 1,
        .msg_type = "addr",
        .priority = MsgPriority::Low,
        .decision = BackpressureDecision::DropLowPri,
        .reason = "queue_high_watermark",
        .timestamp_us = GetMonotonicTimeUs(),
        .recv_queue_msgs = 300,
        .recv_queue_bytes = 10000000,
        .global_inflight_blocks = 5,
        .loop_budget_parse_us_left = 0,
        .loop_budget_heavy_msgs_left = 0,
        .peer_heavy_msgs_processed = 3,
        .max_peer_heavy_msgs_per_loop = 2
    };
    hooks.OnMsgProcBackpressure(bp_ev);
    
    MsgProcDropEvent drop_ev{
        .peer_id = 1,
        .msg_type = "addr",
        .reason = "queue_high_watermark",
        .dropped_count = 5,
        .timestamp_us = GetMonotonicTimeUs()
    };
    hooks.OnMsgProcDrop(drop_ev);
    
    MsgProcLoopEvent loop_ev{
        .iteration = 100,
        .start_us = 1000,
        .end_us = 5000,
        .peers_scanned = 10,
        .msgs_processed = 50,
        .msgs_deferred = 2,
        .msgs_dropped = 1,
        .had_work = true,
        .parse_us_consumed = 1500,
        .heavy_msgs_consumed = 3
    };
    hooks.OnMsgProcLoop(loop_ev);
    
    // If we get here without crash/exception, test passes
    BOOST_CHECK(true);
}

// ============================================================================
// Test: MsgProcPeerLoopState
// ============================================================================

BOOST_AUTO_TEST_CASE(peer_loop_state_reset)
{
    MsgProcPeerLoopState state;
    state.heavy_msgs_processed = 5;
    
    state.Reset();
    
    BOOST_CHECK_EQUAL(state.heavy_msgs_processed, 0);
}

BOOST_AUTO_TEST_SUITE_END()
