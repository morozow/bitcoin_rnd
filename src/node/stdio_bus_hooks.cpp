// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <node/stdio_bus_hooks.h>

#include <atomic>
#include <memory>
#include <mutex>

namespace node {

namespace {
// Global hooks state.
//
// Notes on the design:
//
// - On libstdc++ we could use std::atomic<std::shared_ptr<T>> (C++20) for
//   truly lock-free reads on hot paths. libc++ on Apple Clang does not
//   accept shared_ptr in std::atomic<T> ("T must be trivially copyable").
//
// - To stay portable we use a "fast-path gate" atomic bool + mutex-guarded
//   shared_ptr. Hot callers (coins.cpp AddCoin/SpendCoin) check the atomic
//   first; when stdio_bus is off the cost is a single relaxed atomic load
//   and a predictable not-taken branch, with no lock acquisition at all.
//
// - Only when hooks are enabled do we take the mutex to obtain a shared_ptr
//   snapshot. That happens at most on every event (which is fine — the
//   event itself is going to a queue anyway).
std::atomic<bool> g_hooks_present{false};
std::mutex g_hooks_mutex;
std::shared_ptr<StdioBusHooks> g_hooks;
} // namespace

void SetGlobalStdioBusHooks(std::shared_ptr<StdioBusHooks> hooks)
{
    std::lock_guard<std::mutex> lock(g_hooks_mutex);
    g_hooks = std::move(hooks);
    g_hooks_present.store(static_cast<bool>(g_hooks), std::memory_order_release);
}

std::shared_ptr<StdioBusHooks> GetGlobalStdioBusHooks()
{
    // Fast path: stdio_bus not installed, return nullptr without taking the lock.
    if (!g_hooks_present.load(std::memory_order_acquire)) {
        return {};
    }
    std::lock_guard<std::mutex> lock(g_hooks_mutex);
    return g_hooks;
}

} // namespace node
