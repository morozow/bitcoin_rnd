# Review Gap: No Shared Acceptance Criteria for Adaptive Logic in Non-Consensus Node Paths

## Summary

Bitcoin has operated for over 15 years without AI in consensus-critical validation, and this issue does not propose changing that. Consensus behavior is explicitly out of scope.

The focus is operational node behavior, where adaptive and ML-assisted logic is increasingly explored — for example in fee estimation, peer management, and Lightning routing — without shared acceptance criteria for review.

## Problem Statement

Adaptive integrations in operational layers are emerging incrementally. Today, there is no common set of acceptance criteria for how such components should interact with deterministic node behavior under adversarial conditions, load, degradation, and recovery.

This creates a review gap: proposals can appear locally reasonable while still introducing unclear trust transitions, unstable failure handling, or network-level side effects. Reviewers lack a shared vocabulary and minimum checklist to evaluate these risks consistently.

## Why This Matters

Even when consensus remains correct, operational behavior can still create systemic risk — for example: network fragmentation dynamics, fee-market distortions, centralization pressure, and unstable peer dynamics.

The core question is not whether Bitcoin can run without AI (it can), but what minimum criteria a reviewer should apply when adaptive components are proposed for non-consensus paths.

## What This Asks Now

This series seeks community input on three concrete outcomes:

1. A shared minimum vocabulary for evaluating adaptive component safety in non-consensus paths (trust states, fallback properties, policy semantics, latency discipline, isolation baseline).
2. Identification of which risk areas are most under-specified in current review practice and should be prioritized.
3. Agreement on what evidence a proposal should provide to be reviewable as disciplined engineering rather than ad hoc heuristic tuning.

## Scope

In scope:
- Formal guarantees for non-consensus adaptive components in node software
- Trust boundaries, policy mediation, fallback behavior, latency bounds, isolation, and systemic side effects

Out of scope:
- Consensus rule changes
- Claims that AI is required for Bitcoin protocol validity
- Productization or rollout plans

## Series Index

This umbrella tracks the following focused discussion issues:

1. Non-consensus systemic risks from adaptive behavior (network and market effects)
2. Trust boundary definition and anti-laundering guarantees
3. Deterministic fallback and anti-flapping recovery behavior
4. Policy enforcement semantics, composition, and auditability
5. Latency budget and bounded behavior under load
6. Risk-based isolation and leakage control for advisory components

## Shared Context (for linked issues)

> Adaptive and ML-based techniques are increasingly being applied to Bitcoin operational layers (for example: fee estimation, peer management, Lightning routing). These integrations are happening incrementally and without a shared formal safety model. This issue examines one specific part of that risk surface.

## Related Open Bitcoin Core Issues (Coverage Map)

The following open issues in bitcoin/bitcoin touch parts of this problem surface. They confirm that the underlying concerns are real and actively discussed, but typically address individual symptoms rather than the formal guarantees framed in this series.

| Research Issue | Related bitcoin/bitcoin Open Issues | Coverage |
|---|---|---|
| R1: Non-consensus systemic risks | #27995, #16599, #34019, #28462, #33958, #34542 | Strong — multiple open issues address individual symptoms (fee accuracy, peer diversity, net splits, relay efficiency) but none frame the systemic risk class connecting them |
| R2: Trust boundary / anti-laundering | (no open issues found) | Gap — no open issue addresses formal trust semantics or provenance tracking for advisory data |
| R3: Deterministic fallback | (no open issues found) | Gap — no open issue addresses deterministic fallback state machines or anti-flapping for adaptive components |
| R4: Policy enforcement semantics | #27995, #32401, #29319, #18243 | Partial — open issues address specific policy domains (fee, relay/mining separation, cluster mempool) but not general formal policy algebra or decision witness |
| R5: Latency budget | (no open issues found) | Gap — latency/timeout concerns appear in closed issues but no open issue frames formal budget discipline for advisory paths |
| R6: Risk-based isolation | #28722 | Partial — multiprocess effort addresses process separation but not covert-channel modeling, leakage budgets, or risk-based containment |

R2 (trust boundary), R3 (deterministic fallback), and R5 (latency budget) have no direct counterparts in current open issues, suggesting these are under-explored areas in current review practice.

## Discussion Questions

1. What minimum formal guarantees should be required before adaptive logic is considered safe in non-consensus paths?
2. Which risks are most under-specified in current review practice: trust, fallback, latency, isolation, or systemic effects?
3. What evidence should a proposal provide to be reviewable as engineering rather than heuristic tuning?
