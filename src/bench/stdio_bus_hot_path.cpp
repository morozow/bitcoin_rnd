// Copyright (c) 2026-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

// Microbenchmarks for stdio_bus USDT-mirror overhead on the UTXO cache
// hot path (utxocache:add / spent / uncache).
//
// We measure three scenarios:
//
//   1. `stdio_bus_utxocache_off`     — No global hooks installed.
//                                       This is the default for every binary
//                                       with -stdiobus=off.
//   2. `stdio_bus_utxocache_shadow`  — Hooks installed with Enabled()==true,
//                                       but On*() is a stack-only no-op to
//                                       isolate the dispatch overhead from
//                                       external I/O.
//
// The goal is to show operators/reviewers that:
//
//   - When stdio_bus is off (the default), the overhead on AddCoin/SpendCoin
//     is a single relaxed atomic load + predictable not-taken branch; no
//     allocations, no mutex, no syscalls.
//
//   - When stdio_bus is on and a worker is attached, the per-event overhead
//     is bounded by a shared_ptr snapshot under a mutex + an event struct
//     built on the stack + a virtual dispatch. This is a fixed cost that
//     scales linearly with the number of UTXO operations.

#include <bench/bench.h>
#include <coins.h>
#include <node/stdio_bus_hooks.h>
#include <primitives/transaction.h>
#include <script/script.h>
#include <uint256.h>

#include <atomic>
#include <memory>

namespace {

/**
 * Stack-only sink hook: Enabled() returns true but every On*() method
 * touches a single std::atomic counter and returns. This intentionally
 * avoids any I/O, allocation, or queue contention so the benchmark isolates
 * the overhead of the USDT-mirror call pattern itself.
 */
class CountingHooks final : public node::StdioBusHooks {
public:
    bool Enabled() const override { return true; }
    bool ShadowMode() const override { return true; }

    void OnMessage(const node::MessageEvent&) override {}
    void OnHeaders(const node::HeadersEvent&) override {}
    void OnBlockReceived(const node::BlockReceivedEvent&) override {}
    void OnBlockValidated(const node::BlockValidatedEvent&) override {}
    void OnTxAdmission(const node::TxAdmissionEvent&) override {}
    void OnMsgHandlerLoop(const node::MsgHandlerLoopEvent&) override {}
    void OnRpcCall(const node::RpcCallEvent&) override {}
    void OnBlockAnnounce(const node::BlockAnnounceEvent&) override {}
    void OnBlockRequestDecision(const node::BlockRequestDecisionEvent&) override {}
    void OnBlockInFlight(const node::BlockInFlightEvent&) override {}
    void OnStallerDetected(const node::StallerDetectedEvent&) override {}
    void OnCompactBlockDecision(const node::CompactBlockDecisionEvent&) override {}
    void OnBlockSourceResolved(const node::BlockSourceResolvedEvent&) override {}
    void OnTxRemoved(const node::TxRemovedEvent&) override {}
    void OnTxReplaced(const node::TxReplacedEvent&) override {}
    void OnTxRejected(const node::TxRejectedEvent&) override {}
    void OnUTXOCacheFlush(const node::UTXOCacheFlushEvent&) override {}
    void OnPeerConnection(const node::PeerConnectionEvent&) override {}
    void OnPeerClosed(const node::PeerClosedEvent&) override {}
    void OnPeerEvicted(const node::PeerEvictedEvent&) override {}
    void OnPeerMisbehaving(const node::PeerMisbehavingEvent&) override {}
    void OnOutboundMessage(const node::OutboundMessageEvent&) override {}
    void OnMempoolAdded(const node::MempoolAddedEvent&) override {}
    void OnBlockConnected(const node::BlockConnectedEvent&) override {}

    void OnUTXOCacheAdd(const node::UTXOCacheAddEvent&) override
    {
        m_add.fetch_add(1, std::memory_order_relaxed);
    }
    void OnUTXOCacheSpent(const node::UTXOCacheSpentEvent&) override
    {
        m_spent.fetch_add(1, std::memory_order_relaxed);
    }
    void OnUTXOCacheUncache(const node::UTXOCacheUncacheEvent&) override
    {
        m_uncache.fetch_add(1, std::memory_order_relaxed);
    }
    void OnCoinSelectionSelectedCoins(const node::CoinSelectionSelectedCoinsEvent&) override {}
    void OnCoinSelectionNormalCreateTx(const node::CoinSelectionNormalCreateTxEvent&) override {}
    void OnCoinSelectionAttemptingAps(const node::CoinSelectionAttemptingApsEvent&) override {}
    void OnCoinSelectionApsCreateTx(const node::CoinSelectionApsCreateTxEvent&) override {}

    std::atomic<uint64_t> m_add{0};
    std::atomic<uint64_t> m_spent{0};
    std::atomic<uint64_t> m_uncache{0};
};

/** RAII guard that installs global hooks for the duration of the bench. */
struct GlobalHooksGuard {
    std::shared_ptr<node::StdioBusHooks> previous;
    explicit GlobalHooksGuard(std::shared_ptr<node::StdioBusHooks> h)
        : previous(node::GetGlobalStdioBusHooks())
    {
        node::SetGlobalStdioBusHooks(std::move(h));
    }
    ~GlobalHooksGuard() { node::SetGlobalStdioBusHooks(previous); }
};

/** Prepare a coins cache pre-populated with N synthetic coins. Returns the
 *  vector of outpoints so benchmarks can operate on them deterministically. */
std::vector<COutPoint> SetupCache(CCoinsViewCache& coins, size_t n)
{
    std::vector<COutPoint> outs;
    outs.reserve(n);
    for (size_t i = 0; i < n; ++i) {
        COutPoint op{Txid::FromUint256(uint256{static_cast<uint8_t>(i)}),
                     static_cast<uint32_t>(i)};
        CTxOut txout;
        txout.nValue = 50'000 + static_cast<int64_t>(i);
        txout.scriptPubKey << OP_TRUE;
        coins.AddCoin(op, Coin{std::move(txout), /*nHeightIn=*/1, /*fCoinBaseIn=*/false},
                      /*possible_overwrite=*/false);
        outs.push_back(op);
    }
    return outs;
}

void BenchAddCoin(benchmark::Bench& bench)
{
    CCoinsView empty;
    CCoinsViewCache coins{&empty};

    uint32_t i = 0;
    bench.run([&] {
        COutPoint op{Txid::FromUint256(uint256{static_cast<uint8_t>(i & 0xff)}), i};
        CTxOut txout;
        txout.nValue = 50'000;
        txout.scriptPubKey << OP_TRUE;
        coins.AddCoin(op, Coin{std::move(txout), /*nHeightIn=*/1, /*fCoinBaseIn=*/false},
                      /*possible_overwrite=*/true);
        ++i;
    });
}

void BenchSpendCoin(benchmark::Bench& bench)
{
    CCoinsView empty;
    CCoinsViewCache coins{&empty};
    auto outs = SetupCache(coins, 1024);

    size_t idx = 0;
    bench.run([&] {
        const auto& op = outs[idx % outs.size()];
        // Re-add a coin at this outpoint before spending so the benchmark can
        // spend for many iterations without exhausting the cache.
        CTxOut txout;
        txout.nValue = 42;
        txout.scriptPubKey << OP_TRUE;
        coins.AddCoin(op, Coin{std::move(txout), /*nHeightIn=*/1, /*fCoinBaseIn=*/false},
                      /*possible_overwrite=*/true);
        coins.SpendCoin(op);
        ++idx;
    });
}

} // namespace

// === OFF path: no global hooks installed (default case). =====================

static void StdioBusHotPath_AddCoin_Off(benchmark::Bench& bench)
{
    node::SetGlobalStdioBusHooks(nullptr);
    BenchAddCoin(bench);
}

static void StdioBusHotPath_SpendCoin_Off(benchmark::Bench& bench)
{
    node::SetGlobalStdioBusHooks(nullptr);
    BenchSpendCoin(bench);
}

// === SHADOW path: hooks installed, Enabled()==true, dispatch only. ===========

static void StdioBusHotPath_AddCoin_Shadow(benchmark::Bench& bench)
{
    auto hooks = std::make_shared<CountingHooks>();
    GlobalHooksGuard guard{hooks};
    BenchAddCoin(bench);
    assert(hooks->m_add.load() > 0);
}

static void StdioBusHotPath_SpendCoin_Shadow(benchmark::Bench& bench)
{
    auto hooks = std::make_shared<CountingHooks>();
    GlobalHooksGuard guard{hooks};
    BenchSpendCoin(bench);
    // Both AddCoin (prewarm + per-iteration add) and SpendCoin fire.
    assert(hooks->m_spent.load() > 0);
    assert(hooks->m_add.load() > 0);
}

BENCHMARK(StdioBusHotPath_AddCoin_Off);
BENCHMARK(StdioBusHotPath_AddCoin_Shadow);
BENCHMARK(StdioBusHotPath_SpendCoin_Off);
BENCHMARK(StdioBusHotPath_SpendCoin_Shadow);
