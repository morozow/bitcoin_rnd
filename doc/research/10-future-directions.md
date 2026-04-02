# Future Directions: Research Agenda for AI Advisory Systems

## Abstract

This document presents a research agenda for advancing AI advisory systems in critical infrastructure. We organize future work into three horizons (0-18 months, 18-36 months, 36+ months), identify open research problems, assess enabling technologies, and document risks to the roadmap. The agenda builds on the theoretical foundations and case studies in documents 01-09.

**Keywords**: research agenda, future work, formal verification, hardware security, federated learning, explainability, multi-agent systems

---

## 1. Introduction

### 1.1 Purpose

This document defines the post-R&D roadmap beyond the current research series (docs 01-09). It separates near-term engineering hardening from long-term fundamental research, with explicit assumptions, dependencies, and exit criteria.

### 1.2 Scope

**In scope**:
- Research directions that strengthen safety/security claims
- Technology evolution and adoption
- Standardization and interoperability
- Risk management for the roadmap itself

**Out of scope**:
- Product roadmap (implementation-specific)
- Business strategy
- Organizational structure

### 1.3 Relationship to Other Documents

| Document | Relationship |
|----------|--------------|
| 01-06 | Theoretical foundations to be strengthened |
| 07-08 | Domain applications to be expanded |
| 09 | Evaluation methodology to be refined |

---

## 2. Research Agenda by Horizon

### 2.1 Horizon 1: Hardening and Validation (0-18 months)

**Focus**: Strengthen existing claims, improve tooling, operational readiness.

| ID | Direction | Goal | Success Criteria |
|----|-----------|------|------------------|
| H1.1 | Mechanized proofs | Prove core invariants in Coq/Isabelle | 100% MUST invariants proven |
| H1.2 | Policy compiler verification | Equivalence checking for policy DSL | Compiler certified |
| H1.3 | Runtime covert-channel monitoring | Online capacity estimation | <2% overhead, real-time alerts |
| H1.4 | Operator explainability | Actionable explanations | Improved decision accuracy |
| H1.5 | Benchmark standardization | Reproducible evaluation suite | Public benchmark released |

**Core Invariants for H1.1**:
- INV-GATE-1 (no bypass): MUST prove
- INV-FB-1 (fail-closed): MUST prove
- INV-REPLAY-1 (determinism): MUST prove
- INV-ISO-1 through INV-ISO-5: SHOULD prove (empirical acceptable)

**"Sufficient" = 100% MUST + 60% SHOULD**

### 2.2 Horizon 2: System-Level Expansion (18-36 months)

**Focus**: Extend to distributed systems, hardware integration, human factors.

| ID | Direction | Goal | Success Criteria |
|----|-----------|------|------------------|
| H2.1 | Hardware-backed isolation | TEE/microVM attestation in trust model | Attestation-bound trust elevation |
| H2.2 | Distributed trust boundaries | Cross-service composition proofs | Multi-node invariants verified |
| H2.3 | Federated model lifecycle | Privacy-preserving updates with safety gates | Safe update protocol deployed |
| H2.4 | Human factors modeling | Formal models for approval quality | Operator workload optimization |
| H2.5 | Cross-domain benchmark | Bitcoin + ICS unified evaluation | Comparative results published |

### 2.3 Horizon 3: Foundational Research (36+ months)

**Focus**: Long-term fundamental advances, emerging technologies.

| ID | Direction | Goal | Success Criteria |
|----|-----------|------|------------------|
| H3.1 | Multi-agent safety algebra | Coordination proofs for multiple AI agents | Formal framework published |
| H3.2 | Unified risk calculus | Safety + security + latency + economics | Optimization model validated |
| H3.3 | Post-quantum audit integrity | PQC signatures for forensic trails | PQC-ready logging deployed |
| H3.4 | Machine-checkable compliance | Automated regulatory mapping | Compliance automation demonstrated |
| H3.5 | Adaptive threshold learning | Dynamic thresholds from threat intelligence | Safe adaptation protocol |

---

## 3. Open Research Problems

### 3.1 Formal Verification of Isolation

**Problem**: Can we formally prove that container/microVM isolation works?

**Current State**: Mostly empirical validation with some formal protocol proofs.

**Research Direction**:
- Hybrid assurance model: formal protocol + empirical platform evidence
- Kernel/hypervisor assumptions explicitly documented
- Proof boundaries clearly defined
- Attestation as evidence of platform state

**Honest Position**: Full formal verification of kernel isolation is beyond current scope. We prove protocols and boundary semantics; platform isolation is validated empirically + attestation.

### 3.2 Interpretability vs Performance Trade-off

**Problem**: More interpretable models are often less accurate. How to balance?

**Research Direction**:
- Define utility of explanation (operator decision quality, not model fidelity)
- Study trade-off curves per domain
- Selective explainability (high-impact actions only)
- Explanation quality metrics that correlate with safety outcomes

**Valid Metrics**:
- Operator decision accuracy (correct approve/reject)
- Time to decision (not too fast, not too slow)
- Override quality (overrides that were correct)
- Post-incident: "explanation helped identify issue"

### 3.3 Adversarial Robustness

**Problem**: How to protect AI models from adversarial inputs?

**Scope**:
- In scope: Input attacks, data poisoning, prompt injection
- Out of scope (for now): Model extraction, membership inference

**Research Direction**:
- Robustness testing standards for advisory models
- Detection + containment policies for adversarial regimes
- Integration with fallback and quarantine triggers
- Adversarial training with safety constraints

### 3.4 Long-Term Drift and Safe Adaptation

**Problem**: AI models drift over time. How to detect and correct without breaking safety?

**Research Direction**:
- Drift detection with confidence bounds
- Safe update protocol (shadow mode, canary, rollback, MOC)
- Guarantees that adaptation does not violate established invariants
- Seasonal baseline models for comparison

**Drift Governance SLA**:
- Drift detected → 24h to assess severity
- High severity → immediate fallback to baseline
- Medium severity → 7 days to remediate
- Low severity → next scheduled update

### 3.5 Human-AI Collaboration

**Problem**: How to optimize operator-AI interaction?

**Research Direction**:
- Cognitive load metrics and limits
- Trust calibration (not over-trust, not under-trust)
- Approval workflow optimization under alarm fatigue
- Training and recertification cadence
- Automation bias detection and mitigation

---

## 4. Enabling Technologies

### 4.1 Hardware Security

| Technology | Status | Application |
|------------|--------|-------------|
| Intel TDX | Emerging | Confidential computing for AI |
| AMD SEV | Available | VM isolation |
| ARM CCA | Emerging | Mobile/edge AI isolation |
| TPM 2.0 | Mature | Attestation, secure boot |

**Dependency Risk**: If TEE vulnerable (side channels, firmware bugs):
- Claims downgraded: "hardware-attested" → "software-isolated"
- Compensating controls: enhanced monitoring
- Transparent disclosure to users

### 4.2 Verified Toolchains

| Tool | Purpose | Maturity |
|------|---------|----------|
| Coq/Isabelle | Theorem proving | Mature |
| TLA+ | Model checking | Mature |
| CBMC | C verification | Mature |
| Dafny | Verified programming | Growing |

### 4.3 Benchmark Infrastructure

**Requirements**:
- Standardized datasets (mempool traces, process data)
- Attack suites (adversarial scenarios)
- Replay corpora (historical decisions)
- Reproducibility packages

**Governance**:
- Independent working group stewardship
- Rotating membership
- Annual refresh with new scenarios
- 20% hidden test cases (prevent teaching to test)

### 4.4 Standards and Interoperability

| Standard Area | Current State | Goal |
|---------------|---------------|------|
| Decision witness format | Internal | Open specification |
| Provenance schema | Internal | Industry standard |
| Policy DSL | Internal | Portable format |
| Compliance mapping | Manual | Machine-checkable |

**If External Standards Fail**:
- Publish open specification
- Provide reference implementation
- Support multiple implementations
- Accept fragmentation as temporary state

---

## 5. Risk Register for Roadmap

### 5.1 Risk Structure

| Risk ID | Risk | Likelihood | Impact | Early Signal | Mitigation | Fallback |
|---------|------|------------|--------|--------------|------------|----------|
| RR-1 | TEE vulnerabilities | Medium | High | CVE announcements | Monitor, patch | Software isolation |
| RR-2 | Regulatory change | Medium | Medium | Draft regulations | Reserved capacity | Pivot scope |
| RR-3 | Talent shortage | High | High | Hiring difficulty | Training, outsource | Defer H2/H3 |
| RR-4 | Adoption friction | Medium | Medium | Pilot feedback | Simplify, document | Focus on high-risk domains |
| RR-5 | Proof complexity | Medium | Medium | Milestone delays | Scope reduction | Enhanced testing |

### 5.2 Dependency Risk Coupling

**Scenario**: TEE maturity AND formal methods hiring both fail.

**Fallback Plan**:
- Continue with empirical validation + enhanced monitoring
- Use V5b instead of V6 (software isolation)
- Increase testing coverage instead of proofs
- Roadmap value preserved at ~70%

### 5.3 Reserved Capacity

- 20% of roadmap capacity reserved for:
  - Regulatory response
  - Critical vulnerability response
  - Unexpected dependencies
- Quarterly review of reserved capacity usage

---

## 6. Milestones and Exit Criteria

### 6.1 Milestones

| ID | Milestone | Horizon | Target Date | Dependencies |
|----|-----------|---------|-------------|--------------|
| M1 | Core invariants proven | H1 | +12 months | Formal methods team |
| M2 | Benchmark suite released | H1 | +15 months | Dataset collection |
| M3 | Hardware attestation integrated | H2 | +24 months | TEE maturity |
| M4 | Compliance automation demonstrated | H3 | +42 months | Regulatory stability |

### 6.2 Failure Criteria

| Milestone | Failure Condition | Response |
|-----------|-------------------|----------|
| M1 | <50% invariants proven at +18 months | Pivot to enhanced testing |
| M2 | No reproducible benchmark at +12 months | Outsource or defer |
| M3 | TEE adoption <10% at +24 months | Fallback to software isolation |
| M4 | Regulatory requirements change fundamentally | Re-scope |

### 6.3 Exit Criteria (Numeric Thresholds)

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| Safety improvement | Unsafe rate ≤ baseline (p<0.05) | Statistical test |
| Latency overhead | p95 ≤ 25% vs baseline | Benchmark |
| Audit completeness | 100% decision witness | Audit |
| Compliance artifacts | 100% required present | Checklist |

**"Done" = All thresholds met for 3 consecutive months**

### 6.4 Sunset Criteria

Direction is sunset when:
- 2 consecutive milestones missed
- No measurable progress in 12 months
- Cost exceeds 3× original estimate
- Dependency technology abandoned

Sunset process: formal review, documentation, knowledge transfer.

---

## 7. Resource Requirements

### 7.1 FTE Estimates

| Horizon | FTE | Roles |
|---------|-----|-------|
| H1 | 3 | 1 formal methods, 1 security, 1 engineering |
| H2 | 5 | +1 distributed systems, +1 human factors |
| H3 | 8 | +2 research, +1 standards |

### 7.2 If Unfundable

Priority order:
1. H1 (core hardening) - essential
2. H2.1, H2.4 (hardware, human factors) - high value
3. H2.2, H2.3 (distributed, federated) - deferrable
4. H3 (foundational) - long-term, can wait

---

## 8. Domain-Specific Branches

### 8.1 Core Roadmap (Shared)

Applies to all domains:
- Mediation principle (policy gate)
- Fail-closed fallback
- Process isolation
- Audit trails
- Deterministic replay

### 8.2 Bitcoin Branch

Domain-specific directions:
- Fee estimation model improvements
- Peer selection optimization
- Lightning routing privacy
- Cross-chain generalization

### 8.3 ICS Branch

Domain-specific directions:
- Setpoint optimization refinement
- Predictive maintenance accuracy
- Safety system integration
- Regulatory compliance automation (IEC 61508/62443)

---

## 9. Incident Learning Loop

### 9.1 Integration Process

```
Incident → Post-Incident Review (72h) → Roadmap Impact Assessment (7 days)
    ↓
Systemic Issue? → Add to next horizon milestone
    ↓
Urgent? → Use reserved capacity
    ↓
Track: incident → roadmap change → resolution
```

### 9.2 SLA

| Event Type | Assessment | Roadmap Update |
|------------|------------|----------------|
| Critical incident | 72 hours | 7 days |
| Near-miss | 7 days | 14 days |
| Audit finding | 14 days | 30 days |

---

## 10. Adoption Economics

### 10.1 Minimum Business Case

| Domain | Justification Threshold |
|--------|------------------------|
| Safety-critical | Any reduction in unsafe events |
| Production-critical | >10% operational improvement |
| Non-critical | >20% improvement to justify 2× cost |

### 10.2 Break-Even Analysis

Required per deployment:
- Cost of C4 implementation
- Expected safety/operational benefits
- Payback period calculation
- Risk-adjusted ROI

---

## 11. Cross-Document Linkage

### 11.1 Open Problems to Document Limitations

| Open Problem | Source Document | Limitation Reference |
|--------------|-----------------|---------------------|
| Formal isolation verification | 06 | Section 15.1 |
| Interpretability trade-off | 07, 08 | Operator trust sections |
| Adversarial robustness | 06 | Attack scenarios |
| Long-term drift | 09 | Time horizon bias |
| Human-AI collaboration | 08 | Human factors section |

### 11.2 Future Directions to Architecture Changes

| Direction | Affected Component | Change Type |
|-----------|-------------------|-------------|
| Hardware attestation | Trust boundary model | Extension |
| Distributed trust | Policy enforcement | New algebra |
| Federated learning | Model lifecycle | New protocol |
| Multi-agent | Coordination layer | New component |

---

## 12. Conclusions

### 12.1 Research Priorities

1. **Immediate (H1)**: Mechanize proofs, standardize benchmarks, improve explainability
2. **Medium-term (H2)**: Hardware integration, distributed systems, human factors
3. **Long-term (H3)**: Multi-agent coordination, unified risk calculus, PQC readiness

### 12.2 Key Dependencies

- Formal methods expertise availability
- TEE ecosystem maturity
- Regulatory stability
- Industry adoption willingness

### 12.3 Bounded Guarantees

Current guarantees are:
- Formal for protocol properties (mediation, fallback)
- Empirical for platform properties (isolation, covert channels)
- Hybrid for end-to-end claims

Evolution path: Strengthen formal coverage while maintaining empirical validation.

### 12.4 Next Review Cycle

- Quarterly roadmap review
- Annual strategic assessment
- Milestone-triggered re-planning
- Incident-driven updates

---

## Appendix A: Claims Ledger

| Claim | Type | Evidence | Owner | Document |
|-------|------|----------|-------|----------|
| No policy bypass | Formal (target) | TLA+ model | Security | 03 |
| Fail-closed fallback | Formal (target) | TLA+ model | Platform | 04 |
| Replay determinism | Formal (target) | Proof | Platform | 02, 05 |
| Isolation effectiveness | Empirical | Attack tests | Security | 06 |
| Covert channel bounds | Empirical | Measurement | Security | 06 |
| Fee efficiency improvement | Empirical | A/B test | Product | 07 |
| Safety preservation (ICS) | Empirical | Monitoring | Safety | 08 |

---

## Appendix B: Threshold Registry

| Threshold | Value | Document | Rationale |
|-----------|-------|----------|-----------|
| T_ai (Bitcoin) | 100ms | 07 | Fee estimation latency |
| T_ai (ICS) | 50-500ms | 08 | Process-specific |
| Covert C_secret | <0.1 bit/s | 06 | High-value data |
| Covert C_internal | <10 bit/s | 06 | Internal data |
| Latency overhead | ≤25% | 09 | Acceptance criterion |
| Unsafe rate | ≤ baseline | 09 | Safety criterion |
| Fallback correctness | 100% | 09 | Reliability criterion |

---

## Appendix C: Artifact Index

| Artifact | Location | Purpose |
|----------|----------|---------|
| TLA+ models | `/formal/tla/` | Formal specifications |
| Test reports | `/evidence/tests/` | Validation evidence |
| Benchmark configs | `/benchmark/configs/` | Reproducibility |
| Decision witness samples | `/evidence/witness/` | Audit examples |
| Environment fingerprints | `/evidence/env/` | Reproducibility |

---

## Appendix D: Glossary Additions

| Term | Definition |
|------|------------|
| Horizon | Time-bounded research phase |
| Mechanized proof | Machine-checked formal proof |
| TEE | Trusted Execution Environment |
| PQC | Post-Quantum Cryptography |
| Attestation | Cryptographic proof of system state |

---

## References

1. Lamport, L. "Specifying Systems: The TLA+ Language." (2002).
2. Klein, G., et al. "seL4: Formal Verification of an OS Kernel." (2009).
3. Costan, V., Devadas, S. "Intel SGX Explained." (2016).
4. Boneh, D., Shoup, V. "A Graduate Course in Applied Cryptography." (2020).
5. EU AI Act. "Regulation on Artificial Intelligence." (2024).

---

*Document Version: 1.0*
*Last Updated: 2026-03-26*
*Authors: Kiro + Codex (AI Research Collaboration)*
*Next Review: Quarterly roadmap review scheduled*
