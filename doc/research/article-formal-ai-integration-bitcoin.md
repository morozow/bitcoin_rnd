# Bitcoin Non-Consensus Review Gap: Acceptance Criteria for Adaptive Logic

## Scope (Read First)

This post is strictly about non-consensus node behavior.
It does not propose consensus changes.
It does not claim Bitcoin requires AI for protocol validity.
It does not propose a specific implementation in this phase.

The goal is narrower: identify a review gap in how adaptive logic is evaluated in operational paths, and ask whether minimal shared acceptance criteria would improve review quality.

---

## 1. Current State: Bitcoin Works Without AI

Bitcoin has operated for more than 15 years without AI in consensus-critical validation. That is a strength, and this post does not challenge it.

Consensus correctness is not the topic here. The topic is whether review practice for non-consensus operational logic has enough shared criteria when behavior becomes more adaptive — when components start making decisions based on learned patterns, statistical models, or external advisory inputs rather than purely deterministic rules.

---

## 2. Why Now

This is timely not because of a single "AI feature," but because review pressure is already visible in several active areas of Bitcoin Core development:

- Fee estimation accuracy and behavior are under active discussion ([#27995](https://github.com/bitcoin/bitcoin/issues/27995)), with proposals to make fee estimation mockable for testing ([#18243](https://github.com/bitcoin/bitcoin/issues/18243)). As fee logic becomes more sophisticated, the question of what constraints and evidence reviewers should expect becomes more pressing.

- Relay and mining policy separation is being discussed ([#32401](https://github.com/bitcoin/bitcoin/issues/32401)), alongside growing mempool policy composition complexity ([#29319](https://github.com/bitcoin/bitcoin/issues/29319)). These are policy-layer changes where composition conflicts and precedence ambiguity matter.

- Process isolation and boundary hardening are actively tracked in the multiprocess effort ([#28722](https://github.com/bitcoin/bitcoin/issues/28722)). As components are separated into distinct processes, the question of what isolation guarantees are sufficient becomes concrete.

- Network topology resilience is a live concern: net split risks ([#33958](https://github.com/bitcoin/bitcoin/issues/33958)), peer selection randomization ([#34019](https://github.com/bitcoin/bitcoin/issues/34019)), and connection diversity ([#28462](https://github.com/bitcoin/bitcoin/issues/28462), [#16599](https://github.com/bitcoin/bitcoin/issues/16599)) are all open threads where adaptive behavior could help or harm depending on how it is constrained.

These are not hypothetical concerns. They are current review surfaces where composition, boundaries, and failure behavior already matter — and where adaptive logic will increasingly be proposed.

---

## 3. The Structural Tension

Adaptive components and critical node software optimize for different properties:

| Adaptive behavior tends toward | Critical node behavior requires |
|---|---|
| Non-deterministic outputs | Reproducible decision paths |
| Model-dependent behavior | Auditable reasoning and evidence |
| Variable latency with tail risk | Bounded completion behavior |
| Evolving heuristics and policies | Stable, reviewable invariants |

This tension does not imply "do not adapt." It implies that review needs clearer acceptance criteria when adaptive behavior influences node operations. Without shared criteria, each proposal is evaluated ad hoc, and systemic risks can accumulate across individually reasonable changes.

---

## 4. Key Risk Areas

This post does not deep-dive each area. It maps the problem surface for focused discussion:

1. Non-consensus systemic effects — local adaptive policy choices can cause network-level harm (fragmentation, convergent behavior, centralization pressure) while remaining consensus-valid.

2. Trust-boundary ambiguity — unclear transitions from untrusted advisory input to actionable decision, with no shared vocabulary for trust states or provenance tracking.

3. Fallback ambiguity — inconsistent degradation and recovery behavior under stress, with no convention for monotonic degradation or anti-flapping controls.

4. Policy composition ambiguity — conflicts between layered policy rules with unclear precedence, no fail-closed defaults, and insufficient decision auditability.

5. Latency-budget ambiguity — advisory processing consuming time needed for mandatory operations, with no explicit budget reservation or replay-compatible timeout discipline.

6. Isolation ambiguity — process sandboxing treated as binary ("isolated or not") without explicit containment invariants, leakage expectations, or data minimization boundaries.

Each area can be discussed independently. Together they point to the same review gap: missing shared acceptance criteria for adaptive components in non-consensus paths.

---

## 5. The Most Underestimated Risk: Consensus-Safe but System-Unsafe Behavior

A critical distinction that deserves separate attention: some behaviors can remain fully consensus-valid while degrading network health and decentralization.

This happens when many nodes independently make locally reasonable adaptive decisions that couple into emergent network-level dynamics:

- Propagation fragmentation: different adaptive relay policies can reduce effective transaction reachability, so some transactions only propagate to subsets of the network — without violating any consensus rule.

- Convergent fee behavior: if a significant fraction of nodes use similar adaptive fee strategies, coordinated market effects emerge without explicit coordination — synchronized fee spikes or drops that distort the natural fee market.

- Peer-selection concentration: local optimization of peer metrics (latency, reliability) can reduce network graph diversity, increasing vulnerability to partitioning — while each individual node appears to be making a good local decision.

- Herd behavior and diversity loss: convergent adaptive strategies reduce behavioral diversity across the network. This diversity is itself a resilience property — it makes coordinated attacks harder. Convergent strategies erode it silently.

These effects are particularly dangerous because they are invisible to consensus-level review. If we only ask "is consensus safe?", we can miss "is the network still healthy and decentralized under these dynamics?" Current review practice does not have a standard way to evaluate these systemic effects.

---

## 6. What This Is Not

This post is not:

- An AI adoption mandate — Bitcoin does not need AI to function, and this post does not argue otherwise.
- A product pitch — no specific implementation is proposed or referenced in this phase.
- A request to re-architect Bitcoin Core — existing architecture is not claimed to be unsafe.
- A claim that current Core review is broken — the goal is incremental improvement of review criteria for a specific emerging class of changes.

This is a problem-framing post for review quality: how to evaluate adaptive operational behavior with less ambiguity and more shared conventions.

---

## 7. Questions for Discussion

Based on ongoing engineering analysis of these problem areas, three narrow questions for community discussion:

1. Should review adopt a minimal shared vocabulary for non-consensus decision inputs — for example, distinguishing untrusted advisory data from validated data from trusted core state? What minimum trust-state distinctions would help reviewers evaluate adaptive component proposals?

2. What minimum evidence should be expected when adaptive logic is proposed for operational paths? For example: explicit decision path documentation, failure behavior description, traceability for audit, bounded completion guarantees?

3. Which non-consensus risk classes should be treated as first-class review concerns? Candidates include: systemic network effects, policy composition conflicts, fallback instability, latency budget overrun, and isolation boundary drift. Which of these matter most for current and near-term review?

These are discussion questions, not prescriptions. Implementation-specific proposals are intentionally deferred until problem framing is discussed.

---

## Closing

Bitcoin does not need AI to remain a valid protocol. But review pressure around adaptive non-consensus behavior is already present in current workstreams — fee estimation, relay policy, mempool composition, process isolation, network topology.

The practical question is not "AI yes or no." The practical question is whether shared acceptance criteria for reviewing adaptive logic would improve review quality before complexity increases further.

Discussion on specific problem areas will follow in focused threads. This post establishes the framing.
