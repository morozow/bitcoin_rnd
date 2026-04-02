# Missing Risk-Based Isolation and Leakage Controls for Advisory Components

## Context

Advisory components are increasingly isolated with process and container mechanisms as they are integrated into node-adjacent workflows. These controls are important but are often treated as binary ("sandboxed or not") rather than as quantified risk controls.

Without risk-based leakage and containment guarantees, isolation cannot answer core safety questions: how much can leak, through which channels, and what blast radius remains after compromise. OS-level sandboxing alone does not provide that assurance.

## Problem Statement

Sandboxing advisory components is necessary but not sufficient. Four required isolation outcomes:

1. Prevent escape.
2. Contain blast radius if compromised.
3. Bound data exfiltration (including covert channels).
4. Preserve deterministic and replayable system behavior.

Current practice often treats isolation as a binary property ("sandboxed or not"), without explicit leakage budgets, data-class constraints, or measurable guarantees.

## Specific Gaps

1. No explicit isolation-level model — isolation controls are applied inconsistently, without a defined progression of containment strength and residual risk.

2. No invariant-based isolation contract — critical constraints (no direct core writes, no unauthorized egress, bounded resources, fail-closed sandbox behavior, no cross-tenant flow) are often not stated as enforceable invariants.

3. Covert channels not treated as measurable risk — timing, size, order, contention, and error channels are typically acknowledged qualitatively but not bounded quantitatively.

4. No risk-based leakage budgeting — data sensitivity is rarely mapped to explicit allowed leakage rates and per-session budgets.

5. Insufficient data minimization by architecture — advisory components may still receive raw sensitive data that could be excluded or transformed upstream in trusted zones.

6. Under-specified supply-chain and tenancy controls — image and model provenance, reproducibility, and cross-tenant isolation are often handled operationally, not as part of a formal safety case.

7. Emergent behavior not integrated into isolation risk model — out-of-distribution behavior, concept drift, reward hacking, and cross-component hazards can create isolation bypass pressure even without classic exploit signatures.

## Why This Matters

Without risk-based isolation, compromise impact and leakage risk are hard to bound and difficult to audit. This can create integrity and confidentiality failures in non-consensus paths while consensus logic still appears correct.

## Boundary With Other Issues

This issue covers process isolation, containment, and leakage control. Trust states for advisory data are covered in Issue 02. Policy decision semantics are covered in Issue 04.

## Research Direction (non-binding)

Phase 1 (minimum isolation baseline): define IPC allowlist, privilege boundaries, fail-closed error handling, and audit hooks for advisory components at the mediation/protocol boundary. Enforce explicit invariants: no direct core writes, restricted egress via trusted IPC boundary, bounded resources, fail-closed sandbox errors, no cross-tenant flow.

Phase 2 (advanced track): extend to covert-channel modeling (timing/size/order/contention/error), measurable leakage limits, class-based leakage budgets, and data minimization architecture where sensitive raw inputs stay outside advisory reach.

If isolation is implemented only as OS-level process sandboxing without protocol-level egress and leakage controls, confidentiality and containment guarantees remain incomplete.

## Related Open Bitcoin Core Issues

- [#28722](https://github.com/bitcoin/bitcoin/issues/28722) Multiprocess tracking issue — separating bitcoin-node, bitcoin-wallet, bitcoin-gui into isolated processes with IPC. Directly relevant to process isolation architecture but does not address covert-channel modeling, leakage budgets, data minimization, or risk-based containment levels.

The multiprocess effort confirms that process isolation is an active engineering priority in Bitcoin Core. This research issue extends the isolation question to include formal leakage guarantees, data classification, and risk-proportional containment — areas not currently covered by the multiprocess scope.

## Discussion Questions

1. What minimum isolation invariants should be required for advisory components in node operation?
2. Should covert-channel risk be evaluated with explicit measurable budgets rather than qualitative statements?
3. How should data classes map to allowable leakage rates and session budgets?
4. What architectural data-minimization boundaries are required so advisory components never access raw high-sensitivity material?
5. Which supply-chain controls are mandatory for advisory runtime artifacts (images, dependencies, models)?
6. What cross-tenant guarantees are required to prevent noisy-neighbor and side-channel interference from becoming safety issues?
