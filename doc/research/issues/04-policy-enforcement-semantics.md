# Under-Specified Policy Enforcement Semantics for Advisory-to-Action Mediation

## Context

As adaptive logic is integrated into operational workflows, validation and control checks tend to be added at multiple points in application code. This often improves functionality quickly but produces fragmented enforcement logic over time.

Without a formal policy model and a single deterministic mediation point, it is hard to prove that all advisory outputs are evaluated consistently. Composition conflicts and hidden bypass paths become difficult to detect and audit.

## Problem Statement

Policy enforcement is the control point between advisory output and deterministic system actions. The core gap: policy layers are often implemented as dispersed checks without a formally defined decision model, composition semantics, or verifiable audit trail.

Without precise semantics, policy behavior is hard to reason about under conflict, degradation, and evolution.

## Specific Gaps

1. Ambiguous effect semantics — a critical distinction is often missing between "deny" (this rule does not allow, others may) and "forbid" (categorically prohibited, non-overridable).

2. Non-predictable composition across multiple policies — combining behavior is frequently implicit. Outcomes become hard to predict when health, trust, domain, and runtime policies interact.

3. Weak fail-closed behavior under uncertainty — indeterminate evaluation paths are not consistently treated as deny/fail-closed.

4. Missing hierarchical constraint model — higher-order constraints (health/trust/global) do not always strictly bound lower-level domain/runtime policy decisions.

5. Insufficient decision auditability and replayability — many systems log outcomes but not full decision witnesses (inputs, context, rules evaluated, combining trace, obligations, provenance).

6. Limited pre-deploy policy analysis — conflicts, shadowing, unreachable rules, obligation incompatibilities, and delegation loops are often found late or not at all.

## Why This Matters

Even if advisory components are isolated, weak policy mediation can still allow unsafe influence paths. A formal policy model is required to make decisions explainable, reviewable, reproducible, and safe under composition and change.

## Why This Is Current Core Review Pain

Bitcoin Core review already faces policy-composition pressure in multiple active areas: fee estimation behavior and bounds (#27995, #18243), relay-vs-mining policy separation (#32401), and increasing mempool policy complexity (#29319). These discussions repeatedly involve how multiple rules interact, which rule should dominate on conflict, and how to make outcomes predictable across edge cases. The gap is not missing policy code, but missing shared semantics for composing and auditing policy decisions consistently. This issue asks whether lightweight, explicit decision semantics and traceability conventions would reduce review ambiguity in these ongoing threads.

## Boundary With Other Issues

This issue covers decision semantics, composition rules, and auditability for policy enforcement. Trust states and provenance tracking for advisory data are covered in Issue 02. Failure handling and recovery are covered in Issue 03.

## Research Direction (non-binding)

For new adaptive policy paths, require one explicit decision path with deterministic semantics and auditable trace. The research direction is to define explicit effect semantics (permit, deny, forbid), deterministic combining (default forbid-overrides), and fail-closed defaults (including indeterminate-as-deny), then evaluate policies synchronously in a controlled execution context. Policy layers should be hierarchical (health/trust/global/domain/runtime) with higher layers constraining lower ones, and decisions should emit a complete witness for audit and deterministic replay. Before deployment, policy sets should pass static checks for conflicts, shadowing, unreachable rules, gaps, and obligation incompatibilities; policy changes should be classified by safety impact (narrowing vs widening).

If checks remain distributed across application paths, composition semantics, replayability, and fail-closed guarantees are not reliably enforceable.

## Related Open Bitcoin Core Issues

- [#27995](https://github.com/bitcoin/bitcoin/issues/27995) Improving fee estimation accuracy — touches policy constraints on fee estimation output. Addresses estimation accuracy but not formal effect semantics (permit/deny/forbid), combining guarantees, or decision witness for audit replay.

- [#32401](https://github.com/bitcoin/bitcoin/issues/32401) rfc: separate relay from mining policy — proposes explicit separation of policy domains for more predictable mediation between relay and mining goals. Directly related to policy architecture, but does not introduce formal policy algebra, combining semantics, or verifiable composition guarantees.

- [#29319](https://github.com/bitcoin/bitcoin/issues/29319) Cluster mempool, CPFP carveout, and V3 transaction policy — evolves admission/relay/package policy rules where correct constraint composition is critical. Addresses specific policy evolution but does not establish a general verifiable framework for policy composition, conflict analysis, or obligation consistency.

- [#18243](https://github.com/bitcoin/bitcoin/issues/18243) Make fee estimation mockable via RPC — improves testability and reproducibility of fee-policy behavior. Enhances testing ergonomics but does not introduce formal trust/policy guarantees, fail-closed semantics, or bounded systemic-effect controls.

These open issues confirm that policy enforcement concerns are real and actively evolving. Each addresses a specific policy domain; this research issue frames the general formal semantics required for any advisory-to-action mediation — composition, auditability, fail-closed behavior, and decision witness.

## Discussion Questions

1. What minimum policy semantics should be required for advisory-to-action mediation (permit, deny, forbid)?
2. Should non-overridable "forbid" precedence be a default safety requirement?
3. What combining behavior is acceptable by default in safety-focused operational paths?
4. What fields are required in a complete decision witness for post-incident audit and deterministic replay?
5. Which static checks should be mandatory before policy deployment (conflicts, shadowing, gaps, obligation incompatibility, delegation cycles)?
6. How should policy changes be classified for review rigor (narrowing vs widening effects)?
