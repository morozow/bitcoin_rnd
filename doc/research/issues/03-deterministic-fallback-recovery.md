# Missing Deterministic Fallback and Anti-Flapping Recovery for Advisory Path Failures

## Context

Operational paths are starting to depend on adaptive components for better real-time decisions under changing conditions. These components can fail in multiple ways (timeouts, invalid outputs, degraded health, resource pressure) at runtime.

If fallback and recovery behavior is not specified deterministically, failure handling becomes inconsistent exactly during stress events. The result is unstable degradation and unpredictable recovery behavior when safety margins are thinnest.

## Problem Statement

When advisory paths fail, systems still need predictable behavior under stress. Four required properties for failure handling:

1. Deterministic response under equivalent failure conditions.
2. Safety preservation across all failure modes.
3. Bounded completion latency.
4. Controlled recovery back to normal operation.

Current fallback handling patterns are often partial (timeouts, retries, circuit breaking) and do not provide a complete deterministic safety model.

## Specific Gaps

1. No monotonic degradation convention — failure handling often lacks a strict rule that failure at one level can only move to a more conservative mode, never a more permissive one.

2. No anti-flapping controls — without hysteresis, dwell times, cooldowns, and transition rate limits, systems can oscillate between modes under noisy conditions.

3. No trigger classification — failure triggers (timeout, validation failure, policy deny, health/resource/security signals) are not consistently categorized and mapped to explicit response levels.

4. No gated recovery protocol — promotion back to normal mode is frequently under-specified, leading to premature recovery and repeated regressions.

5. No idempotent execution path — without idempotency keys and deterministic transition rules, repeated failures can cause duplicate application or ambiguous outcomes.

## Why This Is Current Core Review Pain

Bitcoin Core already handles some failure modes deterministically (e.g., peer disconnection on protocol violation, block download timeout and retry). But there is no shared convention for how adaptive/advisory components should degrade and recover. As proposals for adaptive fee estimation, peer scoring, or routing optimization emerge, reviewers need minimum fallback properties to evaluate — not a full formal state machine, but explicit answers to: "what happens when this component fails?"

## Boundary With Other Issues

This issue covers failure handling and recovery behavior. Latency budget and timeout discipline are covered in Issue 05. Policy decision semantics are covered in Issue 04.

## Prior-Art Limitations

Existing patterns each cover only part of the problem:

- Circuit breakers: no full hierarchy or action-class semantics.
- Retries/backoff: no deterministic safety guarantee.
- Bulkheads: isolation without fallback policy logic.
- Sagas: compensation focus, not real-time deterministic fallback.

## Research Direction (non-binding)

Address failure handling with minimum required properties: monotonic degradation (only stricter modes on failure), bounded recovery gating (eligibility, low-risk probing, success-streak validation before promotion), idempotent retries, and explicit anti-flapping controls (hysteresis, minimum dwell, cooldown, transition rate limits). Timeout ownership and state transitions should remain in the mediation layer so fallback cannot be bypassed by advisory components.

If fallback control is delegated to advisory workers or scattered app code, deterministic degradation, bounded completion, and total failure handling cannot be guaranteed.

## Related Open Bitcoin Core Issues

No directly related open issues were found in bitcoin/bitcoin that address deterministic fallback state machines or anti-flapping recovery for adaptive/advisory components.

This suggests the fallback/degradation problem is an under-explored area in current Bitcoin Core review practice. Timeout and failure handling are discussed in specific closed issues, but no open issue frames this as a formal discipline for adaptive component integration.

## Discussion Questions

1. What minimum properties should fallback logic satisfy before adaptive behavior is considered safe for operational paths?
2. Should monotonic degradation be required (only stricter modes on failure, explicit protocol for recovery)?
3. Which anti-flapping controls are mandatory in practice (hysteresis, dwell, cooldown, transition limits)?
4. What trigger taxonomy should be standardized for fallback decisions?
5. What evidence is required to demonstrate bounded completion and deterministic outcomes under repeated failure conditions?
