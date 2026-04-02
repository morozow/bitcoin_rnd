# Trust Boundary Ambiguity and Anti-Laundering Gaps for Adaptive Components

## Context

Adaptive and ML-based components are increasingly used to influence operational decisions around deterministic node logic. In practice, these integrations are often added through local checks and transformations rather than a unified trust model.

Without formal trust-state transitions and provenance continuity, advisory outputs can accumulate de facto authority through processing chains. The boundary between untrusted influence and trusted decision input becomes ambiguous.

## Problem Statement

How to reason formally about trust when non-deterministic advisory components interact with deterministic, safety-critical system logic.

Core tension:

- Advisory output is inherently untrusted (opaque, non-deterministic, potentially adversarial).
- Core node behavior requires integrity, auditability, and bounded authority.
- Data flow must preserve both integrity and confidentiality constraints.

Without explicit trust semantics, review cannot reliably answer what may influence which actions, under what evidence, and with what residual risk.

## Specific Gaps

Current practice lacks a shared vocabulary that distinguishes:

- untrusted advisory data (raw output from adaptive component),
- validated data (passes explicit endorsement checks),
- trusted core-authoritative state (deterministic, core-derived).

A minimal review convention: advisory-origin data may be elevated to validated status through explicit checks, but should not be treated as trusted core truth. This distinction is not currently standardized in Bitcoin Core review practice.

## Anti-Laundering Concern

A second gap is provenance preservation. If advisory-influenced data can be transformed and later appear indistinguishable from core-derived data, trust boundaries collapse silently.

The research frames this as an anti-laundering requirement: advisory influence should remain traceable through transformations, and authorization should be bound to the true initiator — to avoid confused-deputy behavior where a mediating component's privileges are used on behalf of an untrusted source.

## Why This Is Current Core Review Pain

Bitcoin Core already handles trust distinctions implicitly — for example, peer-provided data vs locally validated data, or RPC input vs internal state. But there is no explicit vocabulary or checklist for reviewing trust transitions when adaptive/external advisory inputs are introduced into operational decision paths. As adaptive components are discussed more frequently (fee estimation improvements, peer scoring proposals), this implicit handling becomes a review gap.

## Boundary With Other Issues

This issue covers trust states and provenance tracking for advisory data. Policy decision semantics and composition rules are covered in Issue 04. Failure handling is covered in Issue 03.

## Research Direction (non-binding)

Address trust ambiguity by proposing a minimal trust-state vocabulary (untrusted / validated / trusted) for review of non-consensus decision inputs. The research direction is to use explicit endorsement checks at the mediation boundary (schema, authorization, policy, binding, capability, budget) before advisory data can influence operational actions, with provenance continuity so advisory influence cannot be laundered through transformations. Authorization should be bound to the original initiator, and declassification authority should remain outside advisory components.

If trust labels and provenance are handled in application-local code paths, anti-laundering guarantees are not enforceable system-wide.

## Related Open Bitcoin Core Issues

No directly related open issues were found in bitcoin/bitcoin that address formal trust-boundary semantics or anti-laundering guarantees for advisory/adaptive data.

This suggests the trust-boundary problem is an under-explored area in current review practice, even as adaptive components are increasingly discussed in operational contexts (fee estimation, peer management).

## Discussion Questions

1. What trust states are minimally required for adaptive/advisory data in Bitcoin node software?
2. Should "validated-but-not-trusted" be treated as a mandatory intermediate class in review?
3. What endorsement checks are required before advisory output may influence operational actions?
4. What provenance guarantees are necessary to prevent laundering of advisory influence through intermediate transformations?
5. How should authorization be bound to prevent mediator/confused-deputy escalation paths?
