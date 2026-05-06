# Assurance Agility Analysis: RFC 7696 Applicability to AI Advisory Systems

## Abstract

This document analyzes the applicability of RFC 7696 (Guidelines for Cryptographic Algorithm Agility and Selecting Mandatory-to-Implement Algorithms, BCP 201) to the AI advisory architecture defined in documents 01-10. The analysis reveals that RFC 7696 principles extend beyond cryptographic primitives to a broader concept we term "assurance agility" — the ability to evolve security-critical components (models, policies, trust profiles, evidence standards) without compromising safety guarantees during transition. The investigation uncovered 11 downgrade vectors, 4 of which represent gaps in the current R&D corpus. We propose an Assurance Agility Profile adapted from RFC 7696 design logic for the AI advisory plane.

**Keywords**: algorithm agility, RFC 7696, downgrade resistance, assurance evolution, transition safety, cryptographic lifecycle

---

## 1. Motivation

### 1.1 The Aging Problem Beyond Cryptography

RFC 7696 addresses a fundamental reality: cryptographic algorithms age and eventually become weak. Protocols that do not plan for algorithm transition pay enormous costs when migration becomes necessary. The WEP-to-WPA transition in IEEE 802.11 and the SHA-1-to-SHA-256 migration (5+ years from specification to widespread deployment) are canonical examples.

The AI advisory architecture defined in this research series faces an analogous but broader aging problem. In our domain, not only cryptographic primitives age — the entire assurance contour evolves:

| What ages | Crypto domain (RFC 7696) | AI advisory domain (this R&D) |
|-----------|--------------------------|-------------------------------|
| Primitives | Hash functions, ciphers, signatures | AI models, inference runtimes |
| Rules | Algorithm selection policies | Policy rules, trust profiles |
| Evidence | Certificate formats, key sizes | Attestation standards, evidence classes |
| Threat landscape | Cryptanalytic advances | Adversarial ML, drift, new attack classes |
| Operational context | Hardware capabilities | Deployment environments, regulatory requirements |

RFC 7696 Section 3.3 warns: "Picking One True Cipher Suite Can Be Harmful." This applies directly to our domain. Fixing a single AI model profile, policy schema, or trust boundary configuration creates the same ossification risk that fixed cipher suites create in cryptographic protocols.

Conversely, RFC 7696 Section 3.2 warns: "Too Many Choices Can Be Harmful." Excessive AI model variants, policy profiles, and trust configurations expand the attack surface. Each rarely-exercised profile is untested code.

### 1.2 Scope Boundary and Non-Goals

This analysis applies exclusively to the AI advisory/control plane as defined in documents 01-10. It does not apply to Bitcoin consensus cryptography or consensus rules.

Bitcoin consensus cryptography (SHA-256d, secp256k1/Schnorr, RIPEMD-160) operates under fundamentally different constraints: changes require network-wide coordination, backward compatibility with the entire UTXO set, and community consensus. RFC 7696-style agility is neither appropriate nor proposed for this layer.

The advisory plane — where AI models produce recommendations validated by policy gates before affecting operational behavior — has different lifecycle dynamics and can benefit from controlled agility without consensus implications.

**Non-goals**:
- No changes to Bitcoin consensus cryptography or consensus rules
- No claim of IETF normative applicability to Bitcoin protocol
- No deployment plan or product specification — this is problem-framing and research direction
- No claim that more controls are always better — complexity itself is a security risk (doc 00, Appendix D: Control Value Test)

### 1.3 Why This Analysis Now

Documents 01-10 define formal models for trust boundaries (doc 02), policy enforcement (doc 03), fallback behavior (doc 04), and isolation (doc 06). These models use cryptographic primitives (signatures, hashes, attestation) in security-critical roles. Without explicit agility provisions, these primitives become fixed dependencies — creating the same migration risk RFC 7696 was written to prevent.

Additionally, the model/policy/trust lifecycle questions raised in doc 10 (Future Directions) — particularly H1.1 (mechanized proofs), H2.1 (hardware-backed isolation), and H2.2 (distributed trust boundaries) — all intersect with agility concerns that RFC 7696 principles help frame.

---

## 2. Method

### 2.1 Analysis Approach

The analysis proceeded through three phases:

1. **Direct mapping**: Identify cryptographic points in the R&D corpus where RFC 7696 applies without analogy.
2. **Structural analogy**: Map RFC 7696 principles to non-cryptographic security-critical components (models, policies, trust profiles).
3. **Gap analysis**: Use the extended framework to discover downgrade vectors not covered by the current R&D corpus.

### 2.2 Sources

- RFC 7696 (BCP 201, Housley, November 2015) — full text analysis
- Documents 00-10 of this research series — cross-referenced for coverage assessment
- Bitcoin Core open issues referenced in the R&D corpus — for deployment context

---

## 3. Structural Analogy: RFC 7696 → AI Advisory Domain

RFC 7696 defines principles for cryptographic protocol design. The following table maps each principle to its AI advisory analogue.

| RFC 7696 Principle | Section | AI Advisory Analogue | R&D Document |
|--------------------|---------|----------------------|--------------|
| Algorithm identifiers | 2.1 | `model_id`, `policy_id`, `crypto_profile_id`, `cap_profile` in registries | 02, 03 |
| Mandatory-to-implement (MTI) | 2.2 | Mandatory safe baseline: deterministic fallback + local policy engine | 01, 04 |
| Transition signaling (SHOULD+/SHOULD-/MUST-) | 2.2.3 | Lifecycle states for model/policy profiles: `preferred`, `allowed`, `deprecated`, `forbidden` | New |
| Downgrade protection | 2.4 | Anti-rollback for policy version, model version, health state, endorsement path | 01, 02, 03 |
| Integrity-protected negotiation | 2.4 | Signed transitions, authenticated state assertions, tamper-evident witness chain | 01, 03 |
| Transition mechanisms | 2.3 | Dual-run, canary, staged rollout via H/F state machine | 04 |
| Balance agility/complexity | 3.2 | Bounded allowlist of profiles; agility through controlled rotation, not large option sets | New |
| IANA registry model | 2.1 | Internal governance registry with deprecation policy and version lifecycle | New |
| Opportunistic security | 2.9 | Opportunistic assurance: degraded AI mode (H2/H1) preferable to full disable, above safety floor | 04 |
| Platform specifications | 2.2.1 | System-level protocol specifies MTI, not embedded components | 01 |
| Key size evolution | 2.2.2 | Evidence strength evolution: attestation depth, signature strength, schema strictness | New |
| Preserving interoperability | 2.6 | Compatibility windows for distributed Bitcoin node deployments with independent upgrade cycles | New |

### 3.1 The Central Insight: Assurance Agility

RFC 7696 solves `algorithm agility` — the ability to migrate cryptographic primitives. Our domain requires `assurance agility` — the ability to evolve the entire decision-making security contour:

```
Assurance Agility = Crypto Agility
                  + Semantic Agility (policy rules)
                  + Behavioral Agility (model profiles)
                  + Operational Agility (health/fallback/isolation)
```

The key risk is mixing these planes in a single version switch. Each plane should evolve independently with its own lifecycle, while maintaining cross-plane compatibility contracts.

### 3.2 Opportunistic Assurance

RFC 7696 Section 2.9 introduces opportunistic security: when strong algorithms are unavailable, weaker-but-present algorithms are preferable to no protection. This principle transfers to our domain as "opportunistic assurance":

When full AI advisory capability (H3) is unavailable, degraded operation (H2/H1) provides partial value and is preferable to complete AI disable (H0) — provided operation remains above the minimum safety floor.

This is already embodied in the fallback state machine (doc 04), but RFC 7696 provides additional design justification: the degraded path should be explicitly designed, tested, and maintained as a first-class operational mode, not treated as an error condition.

**Constraint**: Opportunistic assurance applies only above the mandatory safety floor. Below the floor, fail-closed (H0) is the only acceptable state. The floor is non-negotiable.

### 3.3 Verifiability Asymmetry

RFC 7696 Section 3.1 states: "Mandatory-to-implement algorithms MUST have a stable public specification and public documentation that has been well studied."

For the AI advisory plane, this creates an important asymmetry:

- **Mandatory baseline** (deterministic fallback, local policy engine, endorsement pipeline): MUST be publicly specified, formally verifiable, and well-studied. This is the MTI equivalent.
- **AI model profiles**: MAY be proprietary or opaque. They are not MTI — they are optional enhancements validated by the mandatory baseline.

This asymmetry is a design feature, not a deficiency. The mandatory baseline provides verifiable safety guarantees regardless of AI model quality. AI models provide utility within the safety envelope defined by the baseline.

---

## 4. Direct Cryptographic Applicability

The R&D corpus contains five points where cryptographic primitives are used in security-critical roles. RFC 7696 applies directly to each.

### 4.1 INV6: Anti-Replay (doc 01)

**Current**: Nonce + TTL + signature verification on AI messages.
**Gap**: No explicit `sig_alg`, `hash_alg`, `key_id` in message envelope.
**RFC 7696 requirement**: Algorithm identifiers MUST be carried in the protocol (Section 2.1).
**Recommendation**: Message envelope should include `sig_alg`, `hash_alg`, `key_id`, `issued_at`, `ttl`, `nonce`. Validator checks against allowlist policy.

### 4.2 Decision Witness Chain (doc 01, 03)

**Current**: Signed or hash-chained audit records.
**Gap**: No versioned envelope for witness cryptographic parameters.
**RFC 7696 requirement**: Migration to new algorithms must not break verification of historical records.
**Recommendation**: Witness envelope should include `witness_sig_alg`, `chain_hash_alg`, `schema_ver`. Historical witnesses remain verifiable under their original algorithm.

### 4.3 Policy Manifest Integrity (doc 03)

**Current**: `policy_ver` as monotonic version number.
**Gap**: Version number alone is not cryptographically verifiable.
**RFC 7696 requirement**: Integrity protection for algorithm/suite selection (Section 2.4).
**Recommendation**: Policy manifest should include `policy_hash`, `policy_sig_alg`, `signer_id`, `valid_from`, `deprecates`. Version becomes a verifiable artifact, not just a counter.

### 4.4 Model Attestation (doc 01, 06)

**Current**: `model_hash` verification.
**Gap**: No `hash_alg` or trust anchor specified alongside hash.
**RFC 7696 requirement**: Key size and algorithm parameters MUST be specified (Section 2.2.2).
**Recommendation**: Attestation should include `model_id`, `model_digest`, `digest_alg`, `attestation_sig_alg`, `attestor_key_id`. If TEE is used (doc 10, H2.1), add `tcb_ver`.

### 4.5 Endorsement Pipeline auth_ok (doc 02)

**Current**: Signature/nonce/TTL check as gate in endorsement pipeline.
**Gap**: No lifecycle governance for accepted signature algorithms.
**RFC 7696 requirement**: Protocols should support algorithm deprecation and transition (Section 2.3).
**Recommendation**: `auth_ok` should be a crypto-agile policy function: accept only algorithms with status `allowed` or `mandatory`; reject `deprecated` or `forbidden`; support controlled overlap windows during transition.

---

## 5. Extended Downgrade Taxonomy

RFC 7696 Section 2.4 establishes that algorithm negotiation SHOULD be integrity protected to prevent downgrade attacks. Applying this principle broadly to the AI advisory plane reveals 11 downgrade vectors — 4 identified in the initial R&D corpus and 7 discovered through this RFC 7696-informed analysis.

### 5.1 Baseline Vectors (Initial R&D Set)

**DG-1: Policy rollback**
- Risk: Rollback to older, more permissive `policy_ver`.
- Current coverage: Partial. `policy_ver` recorded in decision witness; rollback prevention not globally enforced.
- RFC 7696 parallel: Rollback to deprecated algorithm suite.
- Research direction: Signed monotonic policy epochs with reject-on-stale enforcement.

**DG-2: Model downgrade**
- Risk: Substitution of less safe model profile.
- Current coverage: Partial. `model_hash` exists; profile lifecycle control is weak.
- RFC 7696 parallel: Negotiation of weaker cipher suite.
- Research direction: Model profile registry with floor constraints and signed activation records.

**DG-3: Health state spoofing**
- Risk: False H3 claim when actual state is H1 or lower.
- Current coverage: Partial. State consumed by policy gate; provenance and freshness constraints on health assertions are underspecified.
- RFC 7696 parallel: Forged negotiation transcript.
- Research direction: Integrity-protected health attestations with freshness bounds per state class.

**DG-4: Endorsement bypass**
- Risk: Circumvention of validation pipeline before policy gate.
- Current coverage: Partial. Pipeline invariants defined (INV1, INV4); bypass resistance needs stronger operational guarantees.
- RFC 7696 parallel: Bypass of integrity protection on negotiation.
- Research direction: Hard invariant — no decision path without endorsement transcript. Fail-closed on verifier failure.

### 5.2 Newly Discovered Vectors (RFC 7696-Informed Extension)

**DG-5: Capability downgrade**
- Risk: Component claims it does not support stricter mode, forcing system onto permissive fallback path.
- Current coverage: **Gap**. Capability model (doc 02, Definition 2.13) is static; claim authenticity not enforced.
- RFC 7696 parallel: TLS client claiming support only for RC4 to force weak cipher.
- Research direction: Signed capability manifests with mandatory capability floor. No runtime path below MTI capability set.

**DG-6: Context downgrade**
- Risk: Incomplete context accepted as valid by policy gate, leading to permissive decision.
- Current coverage: Partial. INV4 (fail-closed on uncertainty) exists, but "incomplete context" may not be classified as "uncertainty" if it appears structurally valid.
- RFC 7696 parallel: Truncated negotiation parameters accepted as valid.
- Research direction: Explicit context completeness contract — required evidence fields, freshness proof for telemetry sources, fail-closed on missing required fields.

**DG-7: Evidence downgrade**
- Risk: Weaker signature algorithm, looser schema, or less strict evidence class still passes `auth_ok` / `schema_ok`.
- Current coverage: **Gap**. Endorsement pipeline checks exist but acceptance profiles are not lifecycle-governed.
- RFC 7696 parallel: Core RFC 7696 concern — algorithm deprecation without enforcement.
- Research direction: Evidence profile registry with lifecycle states (`preferred` / `allowed` / `deprecated` / `forbidden`). Sunset enforcement with overlap windows.

**DG-8: Temporal downgrade**
- Risk: Replay of stale-but-formally-valid health attestation, policy snapshot, or capability claim.
- Current coverage: Partial. INV6 covers anti-replay for AI messages (nonce + TTL). Artifact-wide freshness enforcement is incomplete — health snapshots, policy attestations, and capability claims may lack independent freshness guarantees.
- RFC 7696 parallel: Replay of valid-but-expired certificate or negotiation transcript.
- Research direction: Per-artifact-class monotonic counters and max-staleness enforcement. Not just AI messages — all state-carrying artifacts.

**DG-9: Dependency downgrade**
- Risk: Rollback of tokenizer, safety filter, prompt template, or policy interpreter while model hash remains unchanged.
- Current coverage: **Gap**. Attestation is centered on model artifact only (`model_hash`). Runtime closure is not attested.
- RFC 7696 parallel: Algorithm implementation vulnerability while algorithm identifier remains valid.
- Research direction: Full runtime closure attestation — model + dependencies + policy interpreter version. Stack digest or SBOM-based verification.

**DG-10: Split-brain downgrade**
- Risk: In distributed deployment, different validators operate with different policy/model epochs. Attacker routes through node with older, more permissive configuration.
- Current coverage: Partial. `policy_ver` in decision witness provides local traceability. No distributed minimum floor guarantee.
- RFC 7696 parallel: Section 2.6 — difficulty of deprecation in distributed systems where legacy support persists.
- Bitcoin-specific concern: Each node is independently operated. No central authority for forced upgrades. Deprecation must be network-tolerant, not centrally enforced.
- Research direction: Admission floor epochs, rollout barriers, compatibility windows. Minimum acceptable `policy_epoch` for inter-node advisory exchange.

**DG-11: Operator-path downgrade**
- Risk: Emergency/manual override path (e.g., manual_ack for quarantine exit in P7) becomes steady-state bypass of safety controls.
- Current coverage: **Gap**. Manual recovery exists; anti-abuse controls are underspecified.
- RFC 7696 parallel: Administrative override of algorithm policy becoming permanent exception.
- Research direction: Break-glass with TTL, dual-control requirement, override budget (max overrides per period), mandatory post-incident reconciliation, auto-revert after TTL expiry.

### 5.3 Coverage Assessment Criteria

To avoid subjective "partial" assessments, we use a four-level maturity scale:

| Level | Name | Meaning |
|-------|------|---------|
| L0 | Gap | No control defined in current R&D corpus |
| L1 | Defined | Control described in formal model but not enforcement-specified |
| L2 | Enforced | Control has enforcement mechanism in architecture (invariant, gate, fail-closed) |
| L3 | Verified | Control has verification method and evidence artifact defined |

### 5.4 Coverage Summary

| Vector | ID | Level | Classification | Blocking Gap |
|--------|----|-------|----------------|--------------|
| Policy rollback | DG-1 | L1 | Baseline | No signed monotonic enforcement |
| Model downgrade | DG-2 | L1 | Baseline | No profile lifecycle registry |
| Health state spoofing | DG-3 | L1 | Baseline | No freshness-bound attestation |
| Endorsement bypass | DG-4 | L2 | Baseline | Operational bypass paths underspecified |
| Capability downgrade | DG-5 | **L0** | RFC 7696-informed | No capability claim verification |
| Context downgrade | DG-6 | L1 | RFC 7696-informed | Completeness criteria underspecified |
| Evidence downgrade | DG-7 | **L0** | RFC 7696-informed | No evidence profile lifecycle |
| Temporal downgrade | DG-8 | L2 (AI msg only) | RFC 7696-informed | Other artifacts lack freshness |
| Dependency downgrade | DG-9 | **L0** | RFC 7696-informed | No runtime closure attestation |
| Split-brain downgrade | DG-10 | L1 | RFC 7696-informed | No distributed floor guarantee |
| Operator-path downgrade | DG-11 | **L0** | RFC 7696-informed | No override governance |

L0 gaps: DG-5, DG-7, DG-9, DG-11.
L1 (defined but not enforced): DG-1, DG-2, DG-3, DG-6, DG-10.
L2 (enforced): DG-4, DG-8 (partial scope).
L3 (verified): None claimed at this stage.

### 5.5 Open Questions

- Is the 11-vector taxonomy complete, or are there additional downgrade classes specific to AI advisory systems that neither RFC 7696 nor this analysis captures?
- For L1 vectors, what is the minimum enforcement mechanism that provides meaningful protection without excessive complexity?
- How should coverage targets differ between deployment contexts (personal node vs custodial vs exchange)?

---

## 6. Assurance Agility Profile (Proposed, Research Draft)

This profile adapts RFC 7696 design logic to the AI advisory plane. It is presented as a research proposal, not a normative specification. The profile addresses the balance between ossification (one fixed configuration) and fragmentation (unbounded configuration space).

### 6.1 Design Objective

Preserve long-term safety under model/policy/trust evolution while minimizing downgrade surface and interoperability fragmentation. Enable controlled migration without flag-day transitions.

### 6.2 Identifier Discipline

Every security-relevant artifact SHOULD carry explicit identifiers sufficient for lifecycle management and forensic replay.

| Artifact | Required Identifiers | Purpose |
|----------|---------------------|---------|
| AI message | `sig_alg`, `hash_alg`, `key_id`, `nonce`, `ttl` | Anti-replay, algorithm tracking |
| Decision witness | `witness_sig_alg`, `chain_hash_alg`, `schema_ver` | Forensic integrity |
| Policy manifest | `policy_id`, `policy_ver`, `policy_hash`, `policy_sig_alg`, `signer_id` | Anti-rollback |
| Model attestation | `model_id`, `model_digest`, `digest_alg`, `attestation_sig_alg`, `attestor_key_id` | Supply chain |
| Capability claim | `cap_profile_id`, `cap_ver`, `claim_sig` | Capability verification |
| Health assertion | `health_epoch`, `health_level`, `assertion_ts`, `assertion_sig` | Anti-spoofing |

### 6.3 Lifecycle Signaling

Each profile entry SHOULD include lifecycle state, adapted from RFC 7696 Section 2.2.3 transition signaling:

| State | Semantics | Operational Effect |
|-------|-----------|-------------------|
| `preferred` | Recommended for new deployments. Analogous to SHOULD+. | Default selection. |
| `allowed` | Acceptable for current use. Analogous to SHOULD. | Accepted without warning. |
| `deprecated` | Scheduled for removal. Analogous to SHOULD-. | Accepted with warning + audit. |
| `forbidden` | Must not be used. Analogous to MUST NOT. | Rejected immediately. |

Each entry carries temporal metadata: `introduced_at`, `recommended_at`, `deprecated_at`, `sunset_at`.

**Lifecycle transitions**:
```
preferred → allowed → deprecated → forbidden
```

Transitions are monotonic (no re-promotion without new version). Transition events are signed and recorded in the assurance transcript.

**Health-state interaction**: Under degraded health (H1/H2), `deprecated` profiles MAY be accepted during grace period to maintain availability. Under H3, only `preferred` and `allowed` profiles are accepted. Under H0, no AI profiles are active (fallback only).

### 6.4 Integrity-Protected Transitions

Policy, model, capability, and evidence profile transitions SHOULD be:
- Signed by authorized transition authority
- Timestamped with monotonic clock
- Replay-resistant (transition_id + epoch counter)
- Recorded in decision witness chain
- Externally auditable

Rollback (transition to older version) SHOULD be treated as a security event requiring elevated authorization and mandatory audit, not as a normal operational action.

### 6.5 Minimum Assurance Floor

Define mandatory baseline capabilities and evidence classes that MUST remain available in all operational states, including degraded health.

| Component | Mandatory Baseline | Rationale |
|-----------|-------------------|-----------|
| Fallback engine | Deterministic fallback for all advisory paths | Safety under AI failure |
| Policy engine | Local policy evaluation with fail-closed default | Mediation guarantee |
| Endorsement pipeline | Schema + auth + policy + bind + cap + budget checks | Trust boundary integrity |
| Audit trail | Append-only decision witness with integrity protection | Forensic capability |
| Anti-replay | Nonce + TTL + freshness enforcement | Temporal integrity |

No runtime path SHOULD operate below this floor. The floor is the MTI equivalent for the advisory plane.

**Verifiability requirement** (from RFC 7696 Section 3.1): The mandatory baseline MUST be publicly specifiable and formally verifiable. AI model profiles MAY be opaque — they are optional enhancements validated by the verifiable baseline. This asymmetry is intentional: safety guarantees derive from the baseline, not from AI model properties.

### 6.6 Bounded Choice

Keep active profile sets intentionally small and testable. Agility is achieved through controlled rotation, not large simultaneous option sets.

**Principle**: The number of active profiles SHOULD NOT exceed the number that can be fully tested on every release cycle.

**Rationale** (RFC 7696 Section 3.2): "Support for many algorithm alternatives is also harmful. Both of these can lead to portions of the implementation that are rarely used, increasing the opportunity for undiscovered exploitable implementation bugs."

### 6.7 Downgrade Resistance as First-Class Invariant

Treat rollback, spoofing, bypass, and stale-state replay as primary threat classes (Section 5 taxonomy). Each downgrade vector SHOULD have:
- Explicit control mapping to verification logic
- Defined fail mode (fail-closed default)
- Evidence trail in decision witness
- Coverage in test catalog

### 6.8 Operational Governance

Emergency and manual override paths SHOULD be:
- Time-bounded (TTL on override authorization)
- Dual-controlled (two independent approvals for safety-critical overrides)
- Budget-limited (maximum overrides per period)
- Audited (override events as first-class signed entries in assurance transcript)
- Auto-reverted (override expires after TTL; renewal requires fresh authorization)

Operator actions SHOULD be represented as first-class signed events in the same assurance transcript as automated decisions. This prevents the operator path from becoming an invisible bypass channel (DG-11).

### 6.9 Open Questions for This Profile

- What is the right size for the active profile set? RFC 7696 suggests "small" but does not quantify. For the advisory plane, is 2-3 active profiles per component sufficient, or does the AI model diversity requirement push toward more?
- How should lifecycle transitions interact with the fallback state machine? If a `preferred` model profile is deprecated mid-operation, should the system transition through H2→H1 or switch directly to the new preferred profile?
- Can the assurance agility profile itself be formally verified (AA-11), or is it inherently a governance artifact that resists mechanization?
- What is the cost of identifier discipline (Section 6.2) in terms of message overhead and processing latency? Does it fit within the latency budget model (doc 05)?

---

## 7. Hardware and Distributed System Considerations

### 7.1 Hardware-Constrained Agility

RFC 7696 Section 4 notes: "Hardware offers challenges in the transition of algorithms... board-level replacement may be needed to change the algorithm."

For the AI advisory plane, this is relevant in two contexts:

1. **TEE-anchored attestation** (doc 10, H2.1): If model or policy attestation is bound to hardware root-of-trust with fixed cryptographic primitives, algorithm agility is physically constrained. Transition planning must account for hardware lifecycle, not just software deployment.

2. **Resource-constrained nodes**: Lightweight Bitcoin nodes or embedded Lightning implementations may not support the full profile set. The mandatory baseline (Section 6.5) must be implementable on constrained platforms. Advanced profiles are optional.

**Research direction**: Hardware-aware agility profiles that distinguish software-rotatable components from hardware-anchored components, with separate lifecycle management for each.

### 7.2 Distributed Deployment Without Central Authority

RFC 7696 Section 2.6 discusses the difficulty of algorithm deprecation in distributed systems: "Implementers have been reluctant to remove deprecated algorithms... over concerns that some party will no longer have the ability to connect."

This is acutely relevant for Bitcoin, where:
- Each node is independently operated
- No central authority can force upgrades
- Network health depends on sufficient adoption of current profiles
- Legacy nodes may persist indefinitely

**Implications for assurance agility**:
- Deprecation must be network-tolerant: deprecated profiles accepted during overlap windows
- Admission floors (minimum acceptable epoch) must be soft-enforced through peer behavior, not hard-enforced through central mandate
- Compatibility windows must be long enough for organic adoption but short enough to limit downgrade exposure
- Split-brain risk (DG-10) is inherent and must be managed, not eliminated

**Research direction**: Network-tolerant deprecation protocols for advisory plane profiles. Measurement of profile adoption across the network (analogous to RFC 6975 for DNSSEC algorithm signaling). Admission floor coordination without central authority.

---

## 8. Research Directions

### 8.1 Immediate (Horizon 1 alignment)

| ID | Direction | Connection |
|----|-----------|------------|
| AA-1 | Add algorithm identifiers to all cryptographic points (Section 4) | Prerequisite for any agility |
| AA-2 | Define evidence profile registry with lifecycle states | Closes DG-7 |
| AA-3 | Specify runtime closure attestation (model + dependencies) | Closes DG-9 |
| AA-4 | Formalize operator override governance (TTL, dual-control, budget) | Closes DG-11 |
| AA-5 | Extend INV6 freshness to all state-carrying artifacts | Strengthens DG-8 coverage |

### 8.2 Medium-term (Horizon 2 alignment)

| ID | Direction | Connection |
|----|-----------|------------|
| AA-6 | Hardware-aware agility profiles for TEE-anchored attestation | H2.1 + Section 7.1 |
| AA-7 | Network-tolerant deprecation protocol for distributed advisory | H2.2 + Section 7.2 |
| AA-8 | Signed capability manifests with mandatory floor | Closes DG-5 |
| AA-9 | Context completeness contracts for policy gate | Strengthens DG-6 coverage |
| AA-10 | Admission floor epoch coordination for Bitcoin network | DG-10 + Bitcoin case study |

### 8.3 Long-term (Horizon 3 alignment)

| ID | Direction | Connection |
|----|-----------|------------|
| AA-11 | Formal verification of downgrade resistance properties | H1.1 (mechanized proofs) |
| AA-12 | Post-quantum agility for advisory plane attestation | H3 + RFC 7696 forward-looking |
| AA-13 | Multi-agent assurance coordination across heterogeneous profiles | H3.1 (multi-agent safety) |

---

## 9. Relationship to Other Documents

| Document | Relationship to This Analysis |
|----------|-------------------------------|
| 01 (AI Advisory Pattern) | INV6 anti-replay, health state machine — direct agility points |
| 02 (Trust Boundary Model) | Capability model, endorsement pipeline — DG-5, DG-7 gaps identified |
| 03 (Policy Enforcement Algebra) | Policy versioning, decision witness — DG-1, DG-6 coverage assessed |
| 04 (Fallback State Machine) | Health transitions, quarantine — DG-3, DG-11 coverage assessed |
| 05 (Latency Budget Theory) | Timing constraints on transition overhead — agility must not violate latency SLOs |
| 06 (Isolation Experiments) | Model attestation, supply chain — DG-9 gap identified |
| 07 (Bitcoin Case Study) | Distributed deployment, no central authority — DG-10, Section 7.2 |
| 08 (Industrial Case Study) | Hardware constraints, safety certification — Section 7.1 |
| 09 (Comparative Evaluation) | Evaluation methodology for agility overhead measurement |
| 10 (Future Directions) | H1.1, H2.1, H2.2 — research direction alignment |

---

## 10. Limitations

1. **No formal verification**: The downgrade taxonomy and coverage assessment are based on architectural analysis, not mechanized proof. Formal verification of downgrade resistance properties is a research direction (AA-11), not a current claim.

2. **Coverage assessment is qualitative**: The L0-L3 maturity scale provides structure but relies on expert judgment. Independent review may reclassify some vectors.

3. **Deployment model dependency**: Recommendations in Sections 6 and 7 assume a general advisory deployment. Specific deployment contexts (personal node, custodial, exchange) may require different agility profiles — this analysis does not differentiate.

4. **Cost of controls not quantified**: Each proposed control adds complexity. Complexity itself is a security risk (doc 00, Appendix D). The Control Value Test should be applied before adopting any recommendation from this analysis.

5. **Covert channel interaction not analyzed**: Agility mechanisms (transition signaling, capability negotiation) may themselves create covert channels. Interaction with doc 06 isolation model is noted but not formally analyzed.

---

## 11. Conclusion

RFC 7696 is applicable to this R&D — not as a normative requirement for Bitcoin consensus, but as a mature engineering framework whose principles transfer to the AI advisory plane.

The analysis yielded three concrete outcomes:

1. **Five direct cryptographic points** (Section 4) where algorithm identifiers and lifecycle governance are needed but currently absent.

2. **Seven new downgrade vectors** (DG-5 through DG-11) discovered by applying RFC 7696 downgrade-resistance thinking beyond cryptographic primitives. Four of these (DG-5, DG-7, DG-9, DG-11) represent gaps in the current R&D corpus.

3. **An Assurance Agility Profile** (Section 6) that adapts RFC 7696 design logic — identifier discipline, lifecycle signaling, integrity-protected transitions, minimum assurance floor, bounded choice, and operational governance — to the AI advisory domain.

The central insight is that the R&D corpus addresses a problem broader than cryptographic agility: assurance agility — the ability to evolve the entire security-critical decision contour (models, policies, trust profiles, evidence standards, operational procedures) without compromising safety during transition. RFC 7696 provides the design vocabulary and proven patterns for this evolution.

---

## References

- RFC 7696: R. Housley, "Guidelines for Cryptographic Algorithm Agility and Selecting Mandatory-to-Implement Algorithms", BCP 201, November 2015.
- RFC 6975: S. Crocker, S. Rose, "Signaling Cryptographic Algorithm Understanding in DNS Security Extensions (DNSSEC)", July 2013.
- Documents 01-10 of this research series.
