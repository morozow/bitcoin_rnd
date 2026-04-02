# Missing Latency-Budget Discipline for Advisory Paths Under Load

## Context

Adaptive inference is being added to latency-sensitive operational paths where requests must still complete within bounded time. Inference latency is variable and can exhibit heavy-tail behavior under load.

Without explicit budget reservation and mediation-owned timeout control, advisory processing can consume time required for mandatory policy, apply, audit, and fallback steps. That turns latency variance into reliability and safety risk.

## Problem Statement

Advisory integration introduces a four-way tension:

1. Utility — longer inference windows can improve advice.
2. Latency — shorter windows improve responsiveness.
3. Reliability — bounded completion within SLO.
4. Determinism — replayable timing decisions.

The key gap: many systems do not reserve and enforce latency budgets so that advisory work can never consume time required for mandatory policy and fallback execution.

## Specific Gaps

1. No explicit latency decomposition and reserved critical budget — without a formal budget split, advisory latency can crowd out mandatory processing paths.

2. No enforced fallback reserve — systems often lack a hard guard ensuring fallback always has guaranteed execution time.

3. No deterministic timeout/replay contract — adaptive timeout controllers may improve runtime behavior but break replay determinism unless controller state and chosen timeout are recorded.

4. Weak handling of queueing variance and heavy tails — inference latency is often right-skewed and high-variance; average-based controls understate tail risk and queueing delay.

5. Insufficient load-mode governance — admission control, shedding, and priority policy are frequently under-specified across normal, degraded, shedding, and emergency states.

6. SLO claims without explicit assumptions ledger — SLO guarantees are conditional; without tracked assumptions and violation responses, guarantees are not operationally meaningful.

## Why This Is Current Core Review Pain

Bitcoin Core already encounters latency and timeout pain in practice: block download stalls (addressed in multiple closed issues), RPC batch request overload, and IBD sync delays under resource pressure. These are symptoms of the same underlying problem — no explicit budget discipline that separates mandatory processing time from optional/advisory time. As adaptive components are proposed for latency-sensitive paths (fee estimation, peer scoring), reviewers need a convention for: "how much time can this component consume, and what happens when it exceeds that?"

## Boundary With Other Issues

This issue covers timing discipline, timeout budgets, and load behavior. Failure handling and recovery state machines are covered in Issue 03. Policy decision semantics are covered in Issue 04.

## Research Direction (non-binding)

For latency-sensitive paths, require explicit timeout budget split, fallback-time reservation, and logged timeout decisions for replay and debug. The research direction is to decompose total latency, reserve a non-negotiable critical budget (policy/apply/audit/fallback minimum), and allocate advisory time only from the remaining budget, with an early-cutoff rule that forces fallback once remaining time is below the fallback reserve. Timeout adaptation should be mode-aware (normal/degraded/shedding/emergency), but replay-compatible: chosen advisory timeout and controller state must be logged so replay uses recorded decisions, not recomputation. Under load, admission thresholds, priority scheduling, fairness policy, and shedding behavior should be enforced by the trusted boundary that owns queueing and clock semantics.

If advisory workers or scattered app code control timing decisions, bounded completion and conditional SLO guarantees cannot be enforced consistently.

## Related Open Bitcoin Core Issues

Latency and timeout concerns appear in several closed issues and discussions but are not currently framed as a formal budget discipline for adaptive/advisory paths. This suggests the latency-budget problem is under-specified in current practice.

## Discussion Questions

1. What minimum latency budget decomposition should be required before adaptive logic is accepted in operational paths?
2. Should fallback-time reservation be a mandatory invariant (advisory cannot consume fallback budget)?
3. What deterministic logging is required for adaptive timeout decisions to support replay and audit?
4. Which load controls should be mandatory (admission thresholds, shedding policy, priority classes, queue fairness)?
5. How should conditional SLO claims be reviewed, and which assumptions must be explicitly monitored at runtime?
6. What is the expected behavior when queueing-model assumptions no longer hold?
