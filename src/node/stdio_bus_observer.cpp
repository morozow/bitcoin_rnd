// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <node/stdio_bus_observer.h>

#include <chain.h>
#include <consensus/validation.h>
#include <kernel/mempool_entry.h>
#include <primitives/block.h>
#include <primitives/transaction.h>
#include <logging.h>

namespace node {

StdioBusValidationObserver::StdioBusValidationObserver(std::shared_ptr<StdioBusHooks> hooks)
    : m_hooks(std::move(hooks))
{
}

void StdioBusValidationObserver::BlockChecked(
    const std::shared_ptr<const CBlock>& block,
    const BlockValidationState& state)
{
    if (!m_hooks || !m_hooks->Enabled()) return;

    const int64_t validated_us = GetMonotonicTimeUs();
    const uint256 hash = block->GetHash();

    // Try to get receive time for latency calculation
    int64_t received_us = validated_us; // Default to validated time if not tracked
    {
        std::lock_guard<std::mutex> lock(m_receive_times_mutex);
        auto it = m_block_receive_times.find(hash);
        if (it != m_block_receive_times.end()) {
            received_us = it->second;
            m_block_receive_times.erase(it);
        }
    }

    BlockValidatedEvent ev{
        .hash = hash,
        .height = -1, // Height not available in BlockChecked, will be set in BlockConnected
        .tx_count = block->vtx.size(),
        .received_us = received_us,
        .validated_us = validated_us,
        .accepted = state.IsValid(),
        .reject_reason = state.IsValid() ? std::string{} : state.ToString()
    };

    try {
        m_hooks->OnBlockValidated(ev);
    } catch (...) {
        // Fail silently - hooks must not affect consensus
        LogDebug(BCLog::NET, "stdio_bus: OnBlockValidated hook threw exception\n");
    }
}

void StdioBusValidationObserver::BlockConnected(
    const kernel::ChainstateRole& role,
    const std::shared_ptr<const CBlock>& block,
    const CBlockIndex* pindex)
{
    // Intentionally empty: the USDT-mirror for validation:block_connected is
    // emitted directly from Chainstate::ConnectBlock (src/validation.cpp) with
    // accurate inputs_count/sigops_cost/duration_ns. Those fields are not
    // available via CValidationInterface, so handling here would either
    // double-emit with zeroes (losing parity) or be a degraded signal.
    (void)role; (void)block; (void)pindex;
}

void StdioBusValidationObserver::TransactionAddedToMempool(
    const NewMempoolTransactionInfo& tx_info,
    uint64_t mempool_sequence)
{
    if (!m_hooks || !m_hooks->Enabled()) return;

    const int64_t processed_us = GetMonotonicTimeUs();
    const CTransactionRef& tx = tx_info.info.m_tx;

    TxAdmissionEvent ev{
        .txid = uint256{tx->GetHash().ToUint256()},
        .wtxid = uint256{tx->GetWitnessHash().ToUint256()},
        .size_bytes = static_cast<size_t>(tx_info.info.m_virtual_transaction_size),
        .received_us = processed_us, // Approximate - actual receive time not available here
        .processed_us = processed_us,
        .accepted = true,
        .reject_reason = {}
    };

    try {
        m_hooks->OnTxAdmission(ev);
    } catch (...) {
        // Fail silently - hooks must not affect consensus
        LogDebug(BCLog::NET, "stdio_bus: OnTxAdmission hook threw exception\n");
    }
}

void StdioBusValidationObserver::TransactionRemovedFromMempool(
    const CTransactionRef& tx,
    MemPoolRemovalReason reason,
    uint64_t mempool_sequence)
{
    // Intentionally empty: the USDT-mirror for mempool:removed is emitted
    // directly from CTxMemPool::removeUnchecked (src/txmempool.cpp) with
    // the real entry_time/fee/vsize fields that USDT exposes. Handling it
    // here as well would cause double-emission of tx_removed events with
    // strictly less information (entry_time/fee are not available in this
    // CValidationInterface callback).
    (void)tx; (void)reason; (void)mempool_sequence;
}

void StdioBusValidationObserver::MempoolTransactionsRemovedForBlock(
    const std::vector<RemovedMempoolTransactionInfo>& txs_removed_for_block,
    unsigned int nBlockHeight)
{
    // Intentionally empty: each transaction in txs_removed_for_block has
    // already been observed by CTxMemPool::removeUnchecked with
    // reason=BLOCK, which emits an OnTxRemoved directly.
    (void)txs_removed_for_block; (void)nBlockHeight;
}

void StdioBusValidationObserver::ChainStateFlushed(
    const kernel::ChainstateRole& role,
    const CBlockLocator& locator)
{
    // Intentionally empty: the USDT-mirror for utxocache:flush is emitted
    // directly from Chainstate::FlushStateToDisk (src/validation.cpp) with
    // accurate duration_us/mode/coins_count/coins_mem_usage/is_prune that
    // USDT exposes. CValidationInterface does not provide these.
    (void)role; (void)locator;
}

} // namespace node
