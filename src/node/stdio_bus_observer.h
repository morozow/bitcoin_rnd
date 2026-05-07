// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_NODE_STDIO_BUS_OBSERVER_H
#define BITCOIN_NODE_STDIO_BUS_OBSERVER_H

#include <node/stdio_bus_hooks.h>
#include <validationinterface.h>
#include <txmempool.h>

#include <memory>
#include <map>
#include <mutex>

namespace node {

/**
 * @brief CValidationInterface observer for stdio_bus hooks
 * 
 * This observer forwards validation events to StdioBusHooks.
 * It follows the same pattern as CZMQNotificationInterface.
 * 
 * Thread safety: Callbacks are invoked on background thread.
 * All hook calls must be non-blocking.
 */
class StdioBusValidationObserver final : public CValidationInterface
{
public:
    explicit StdioBusValidationObserver(std::shared_ptr<StdioBusHooks> hooks);
    ~StdioBusValidationObserver() = default;

    // Non-copyable
    StdioBusValidationObserver(const StdioBusValidationObserver&) = delete;
    StdioBusValidationObserver& operator=(const StdioBusValidationObserver&) = delete;

    /** Check if observer is enabled */
    bool Enabled() const { return m_hooks && m_hooks->Enabled(); }

    // Test-only accessors that proxy to the protected CValidationInterface
    // callbacks so unit tests can exercise the observer without registering it.
    void TestInvokeBlockChecked(const std::shared_ptr<const CBlock>& block,
                                const BlockValidationState& state)
    {
        BlockChecked(block, state);
    }
    void TestInvokeBlockConnected(const kernel::ChainstateRole& role,
                                  const std::shared_ptr<const CBlock>& block,
                                  const CBlockIndex* pindex)
    {
        BlockConnected(role, block, pindex);
    }
    void TestInvokeTransactionAddedToMempool(const NewMempoolTransactionInfo& tx,
                                             uint64_t mempool_sequence)
    {
        TransactionAddedToMempool(tx, mempool_sequence);
    }
    void TestInvokeTransactionRemovedFromMempool(const CTransactionRef& tx,
                                                 MemPoolRemovalReason reason,
                                                 uint64_t mempool_sequence)
    {
        TransactionRemovedFromMempool(tx, reason, mempool_sequence);
    }
    void TestInvokeMempoolTransactionsRemovedForBlock(
        const std::vector<RemovedMempoolTransactionInfo>& txs,
        unsigned int nBlockHeight)
    {
        MempoolTransactionsRemovedForBlock(txs, nBlockHeight);
    }
    void TestInvokeChainStateFlushed(const kernel::ChainstateRole& role,
                                     const CBlockLocator& locator)
    {
        ChainStateFlushed(role, locator);
    }

protected:
    // CValidationInterface callbacks

    /**
     * Called after block validation completes (accepted or rejected).
     * This is the primary hook point for OnBlockValidated.
     */
    void BlockChecked(const std::shared_ptr<const CBlock>& block,
                      const BlockValidationState& state) override;

    /**
     * Called when a block is connected to the active chain.
     * Can be used for additional timing metrics.
     */
    void BlockConnected(const kernel::ChainstateRole& role,
                        const std::shared_ptr<const CBlock>& block,
                        const CBlockIndex* pindex) override;

    /**
     * Called when a transaction is added to mempool.
     * Used for OnTxAdmission hook.
     */
    void TransactionAddedToMempool(const NewMempoolTransactionInfo& tx,
                                   uint64_t mempool_sequence) override;

    /**
     * Called when a transaction is removed from mempool.
     * Covers mempool:removed tracepoint.
     */
    void TransactionRemovedFromMempool(const CTransactionRef& tx,
                                       MemPoolRemovalReason reason,
                                       uint64_t mempool_sequence) override;

    /**
     * Called when transactions are removed from mempool due to block connection.
     * Covers batch mempool:removed events.
     */
    void MempoolTransactionsRemovedForBlock(
        const std::vector<RemovedMempoolTransactionInfo>& txs_removed_for_block,
        unsigned int nBlockHeight) override;

    /**
     * Called when chain state is flushed to disk.
     * Covers utxocache:flush tracepoint.
     */
    void ChainStateFlushed(const kernel::ChainstateRole& role,
                           const CBlockLocator& locator) override;

private:
    std::shared_ptr<StdioBusHooks> m_hooks;
    
    // Track block receive times for latency calculation
    // Key: block hash, Value: receive timestamp in microseconds
    // Note: This is a simplified approach; production code might use
    // a bounded LRU cache to prevent unbounded growth
    mutable std::map<uint256, int64_t> m_block_receive_times;
    mutable std::mutex m_receive_times_mutex;
};

} // namespace node

#endif // BITCOIN_NODE_STDIO_BUS_OBSERVER_H
