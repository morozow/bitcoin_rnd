# Non-Consensus Systemic Risks from Adaptive Policies in Bitcoin Node Operation

## Context

Adaptive and ML-based techniques are increasingly being introduced in Bitcoin operational paths such as fee estimation, peer management, and relay/routing decisions. This adoption is happening incrementally across components, without a shared formal safety discipline for cross-node behavior.

When many nodes independently deploy similar adaptive strategies, local optimizations can couple into emergent network-level dynamics. This creates consensus-safe but system-unsafe risks (for example fragmentation, synchrony effects, and centralization pressure) that no single node controls.

## Problem Statement

A critical distinction: some behaviors can remain consensus-safe while becoming network/market-unsafe.

This means consensus correctness alone is not a sufficient safety criterion for adaptive operational policies. The open problem is how to reason about and constrain systemic side effects that emerge from many locally "valid" node decisions.

## Risk Classes

1. Transaction propagation fragmentation — different adaptive relay policies can reduce effective transaction reachability, so some transactions only propagate to subsets of the network.

2. Fee market manipulation dynamics (without explicit coordination) — if many nodes use similar adaptive fee strategies, convergent behavior can create coordinated market effects.

3. Mining centralization pressure — operators with stronger adaptive models may gain persistent operational advantage, creating centralization pressure over time.

4. Peer-selection-driven partition risk — local optimization of peer metrics can reduce graph diversity and increase partition susceptibility.

5. Herd behavior and loss of behavioral diversity — convergent adaptive strategies can reduce diversity that otherwise acts as a network-level resilience property.

## Why This Matters

These effects can degrade network health and decentralization while leaving consensus rules untouched. The engineering question is not only "Is consensus safe?" but also "Are network-level dynamics staying within safe operating bounds?"

## Candidate Stability Constraints

- Bounded relay fragmentation (for example, reachability floors)
- Bounded fee-policy deviation from baseline
- Bounded peer centralization with diversity floors
- Bounded propagation delay relative to baseline

## Candidate Coordination-Risk Controls

- Model diversity across deployments
- Randomized tie-break behavior within safe envelopes
- Anti-correlation noise
- Policy synchrony monitoring
- Operator-local emergency disable conditions with shared observability signals for synchrony stress

## Boundary With Other Issues

This issue covers network-level and market-level emergent effects from adaptive behavior. Trust semantics for advisory data are covered in Issue 02. Failure handling is covered in Issue 03. Policy decision semantics are covered in Issue 04.

## Research Direction (non-binding)

Address this risk class through protocol-level systemic guardrails, not node-local heuristics alone. The research direction is to enforce network-facing constraints in a trusted mediation layer: bounded relay reachability loss, bounded fee-policy deviation, and bounded peer-centralization metrics. It also proposes explicit coordination-risk controls at that same layer: model diversity requirements, randomized tie-breaking, anti-correlation noise, synchrony monitoring, and operator-local emergency disable conditions with shared observability signals for synchrony stress. For LN-style exploration/exploitation balance, keep a bounded non-adaptive exploration budget (for example, fixed random-route share) as a first-class policy control.

If these controls are not enforceable at the mediation/protocol boundary, they remain advisory and cannot reliably constrain consensus-safe but system-unsafe emergent behavior.

## Related Open Bitcoin Core Issues

- [#27995](https://github.com/bitcoin/bitcoin/issues/27995) Improving fee estimation accuracy — fee estimator may overpay by matching observed behavior rather than optimal targets. Addresses fee dynamics accuracy but lacks formal systemic-risk constraints or bounded fee-policy deviation controls.

- [#16599](https://github.com/bitcoin/bitcoin/issues/16599) ASN-based bucketing of network nodes — proposes diversifying peer bucketing beyond /16 groups to reduce eclipse risk. Addresses peer diversity at the bucketing level but without formal diversity invariants, coordination-risk controls, or network-wide stability bounds.

- [#34019](https://github.com/bitcoin/bitcoin/issues/34019) RFC: randomize over netgroups in outbound peer selection — reduces correlated peer selection behavior and improves topological diversity. Directly related to partition and herd-dynamics risk, but does not introduce formal policy-synchrony metrics or systemic coordination-risk controls.

- [#28462](https://github.com/bitcoin/bitcoin/issues/28462) Increase number of block-relay-only connections — strengthens block propagation resilience by reducing dependence on a limited connection set. Improves a connectivity parameter but without a formal model of emergent effects (fragmentation bounds, diversity floors, emergency disable conditions).

- [#33958](https://github.com/bitcoin/bitcoin/issues/33958) Net split meta issue — directly addresses the risk of network partitioning and degraded network-level safety while consensus remains formally valid. Aggregates related problems but without a unified formal framework for bounded systemic risk or coordination-effect verification.

- [#34542](https://github.com/bitcoin/bitcoin/issues/34542) RFC: Erlay Conceptual Discussion — relay protocol efficiency affects transaction propagation dynamics and potential fragmentation. Addresses relay bandwidth but not formalized safety bounds for adaptive policy interaction or convergent behavior across deployments.

These open issues confirm the problem surface is real and actively discussed. Each addresses individual symptoms; this research issue frames the systemic risk class that connects them and requires formal constraints beyond per-issue fixes.

## Discussion Questions

1. What non-consensus systemic effects should be treated as first-class review blockers in Bitcoin node policy changes?
2. Which network-level metrics are appropriate as safety constraints (reachability, diversity, propagation delay, fee-policy spread)?
3. How should the community evaluate coordination risk when no explicit coordination exists?
4. Under what conditions should an emergency disable mechanism be considered justified for adaptive policy fleets?
5. What evidence would be sufficient to show that an adaptive policy is consensus-safe and systemically safe?
