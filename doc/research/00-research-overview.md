# R&D: AI Agent System via stdio_bus

## Research Overview

This document presents novel research into safe AI agent integration within deterministic systems. The stdio_bus transport layer serves as the implementation substrate, but the research contributions are architectural patterns, formal models, and safety guarantees for AI agents in critical infrastructure.

## Research Questions

### RQ1: Safe AI Placement in Critical Systems
How can AI agents be integrated into systems with strict correctness requirements (financial, industrial, blockchain) without compromising system integrity?

**Hypothesis**: AI agents can safely enhance critical systems when:
1. AI output is treated as untrusted advisory input
2. A deterministic policy layer validates all AI recommendations
3. Fallback behavior is defined for all AI failure modes
4. AI cannot directly affect system state

### RQ2: Trust Boundary Formalization
What formal model captures the trust relationship between AI components and deterministic system cores?

**Hypothesis**: A three-zone trust model (Untrusted AI → Policy Gate → Trusted Core) with explicit invariants provides verifiable safety guarantees.

### RQ3: Latency-Bounded AI Integration
How can AI inference be integrated into real-time message processing without violating latency SLOs?

**Hypothesis**: Timeout-bounded AI with deterministic fallback enables real-time AI enhancement while maintaining latency guarantees.

### RQ4: Failure Mode Completeness
Can we enumerate and handle all AI failure modes in a way that preserves system availability?

**Hypothesis**: A finite state machine of AI health states with defined transitions covers all failure scenarios.

## Novel Contributions

### Contribution 1: AI Advisory Architecture Pattern
A new architectural pattern where AI provides recommendations that are validated by a deterministic policy engine before affecting system behavior.

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI ADVISORY PATTERN                          │
│                                                                 │
│  ┌─────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────┐ │
│  │  Input  │───▶│  AI Agent   │───▶│   Policy    │───▶│ Out │ │
│  │  Data   │    │  (Advisory) │    │   Engine    │    │ put │ │
│  └─────────┘    └─────────────┘    │(Authoritative)   └─────┘ │
│                        │           └──────┬──────┘            │
│                        │                  │                    │
│                   UNTRUSTED          DETERMINISTIC             │
│                   OUTPUT             VALIDATION                │
│                                                                 │
│  Key Invariant: AI output NEVER directly affects system state  │
└─────────────────────────────────────────────────────────────────┘
```

### Contribution 2: Deterministic Fallback State Machine
A formal state machine for AI health with guaranteed fallback behavior.

### Contribution 3: Policy Enforcement Algebra
A formal algebra for expressing AI output constraints and validation rules.

### Contribution 4: Latency Budget Model
A mathematical model for allocating latency budgets to AI inference with graceful degradation.

### Contribution 5: Trust Boundary Calculus
A formal calculus for reasoning about information flow across AI/deterministic boundaries.

## Document Structure

| Document | Research Focus | Status | R&D Dialogue |
|----------|----------------|--------|--------------|
| `01-ai-advisory-pattern.md` | Novel architectural pattern for safe AI integration | ✓ Complete | ✓ Full |
| `02-trust-boundary-model.md` | Formal trust model with invariants and proofs | ✓ Complete | ✓ Full |
| `03-policy-enforcement-algebra.md` | Formal language for AI output validation | ✓ Complete | ✓ Full |
| `04-fallback-state-machine.md` | Complete failure mode enumeration and handling | ✓ Complete | ✓ Full |
| `05-latency-budget-theory.md` | Mathematical model for real-time AI integration | ✓ Complete | ✓ Full |
| `06-isolation-experiments.md` | Experimental validation of isolation mechanisms | ✓ Complete | ✓ Full |
| `07-bitcoin-case-study.md` | Deep application to blockchain/P2P systems | ✓ Complete | ✓ Full |
| `08-industrial-case-study.md` | Application to industrial control systems | ✓ Complete | ✓ Full |
| `09-comparative-evaluation.md` | Baseline vs AI-assisted performance analysis | ✓ Complete | ✓ Full |
| `10-future-directions.md` | Open problems and research roadmap | ✓ Complete | ✓ Full |
| `11-assurance-agility-rfc7696-analysis.md` | RFC 7696 applicability, downgrade taxonomy, assurance agility profile | ✓ Complete | ✓ Full |

## Claim of Novelty

This research makes the following novel contributions to the field of AI system integration:

1. **First formal treatment** of AI advisory patterns for critical infrastructure
2. **Novel trust boundary model** with verifiable safety invariants
3. **Complete failure mode enumeration** for AI agents in real-time systems
4. **Latency budget theory** for bounded AI inference in message processing
5. **Policy enforcement algebra** for expressing AI output constraints

## Relationship to Implementation

The stdio_bus transport layer provides the implementation substrate for this research. The transport layer documentation (`docs/universal-transport/00-12`) describes the engineering implementation, while this research documentation (`docs/universal-transport/research/`) presents the novel theoretical contributions.

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENTATION STRUCTURE                       │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              R&D: AI Agent System Research               │   │
│  │                                                          │   │
│  │  - Novel patterns, models, theories                      │   │
│  │  - Formal proofs and invariants                          │   │
│  │  - Experimental validation                               │   │
│  │  - Case studies (Bitcoin, Industrial)                    │   │
│  │                                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│                            │ implements                         │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           Engineering: Transport Layer Docs              │   │
│  │                                                          │   │
│  │  - Wire protocols, framing, modes                        │   │
│  │  - API reference, configuration                          │   │
│  │  - Performance benchmarks                                │   │
│  │  - Compliance documentation                              │   │
│  │                                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## References

- [Transport Layer Overview](../00-overview.md)
- [AI Agent Integration (Engineering)](../05-ai-agent-integration.md)
- [Use Cases](../06-use-cases.md)

---

## Appendix A: Canonical Glossary

**Purpose**: This glossary provides NORMATIVE definitions for terms used across all research documents. When terms appear in documents 01-10, they have the meanings defined here.

### A.1 Trust and Security Terms

| Term | Definition | Documents |
|------|------------|-----------|
| **TCB (Trusted Computing Base)** | Set of components whose correctness is required for security guarantees. Includes: Gate, Actuator, LabelManager, Audit, ContextBuilder. | 02 |
| **Integrity Level (I)** | Trust level of data: Iᵤ (untrusted), Iᵥ (validated), Iₜ (trusted). AI output max = Iᵥ. | 02 |
| **Confidentiality Level (C)** | Secrecy level: Cₚ (public), Cᵢ (internal), Cₛ (secret). | 02 |
| **Provenance (Prov)** | Record of data origin and transformations, including ai_influenced flag. | 02 |
| **Endorsement** | Process of elevating integrity from Iᵤ to Iᵥ through validation pipeline. | 02 |
| **Declassification** | Governed lowering of confidentiality level by authorized DA. | 02 |
| **Taint** | Boolean flag indicating AI influence: ai_influenced = true. | 02 |

### A.2 Policy Terms

| Term | Definition | Documents |
|------|------------|-----------|
| **Effect** | Policy decision outcome: Permit, Deny, Forbid, NotApplicable, Indeterminate. | 03 |
| **Permit** | Action is allowed. | 03 |
| **Deny** | Action rejected, fallback may be attempted. | 03, 04 |
| **Forbid** | Action categorically rejected, no fallback (veto). | 03, 04 |
| **Indeterminate** | Evaluation error, treated as Deny (fail-closed). | 03 |
| **Obligation** | Side-effect action triggered by policy decision (log, notify, escalate). | 03 |
| **Combining Algorithm** | Method for combining multiple rule decisions (forbid-overrides default). | 03 |

### A.3 Fallback Terms

| Term | Definition | Documents |
|------|------------|-----------|
| **Fallback Level (F0-F3)** | Degradation hierarchy: F0 (normal), F1 (degraded), F2 (safe default), F3 (safe stop). | 04 |
| **F0 (Normal)** | Full AI advisory path active. | 04 |
| **F1 (Degraded)** | AI disabled, cache/rule-based fallback. | 04 |
| **F2 (Safe Default)** | Conservative deterministic outcome. | 04 |
| **F3 (Safe Stop)** | Reject all, escalate. Terminal state. | 04 |
| **Quarantine** | Security lockdown state, high-impact actions blocked. | 04 |
| **Recovery** | Protocol for returning from degraded state to normal. | 04 |
| **Anti-Flapping** | Mechanisms to prevent rapid state oscillation (hysteresis, dwell, cooldown). | 04 |

### A.4 Health Terms

| Term | Definition | Documents |
|------|------------|-----------|
| **Health Level (H0-H3)** | AI agent health: H0 (failed), H1 (untrusted), H2 (degraded), H3 (healthy). | 01, 04 |
| **H3 (Healthy)** | Full AI capability, actions A0-A2 permitted. | 01 |
| **H2 (Degraded)** | Reduced trust, actions A0-A1 permitted. | 01 |
| **H1 (Untrusted)** | Minimal AI influence, A0 only. | 01 |
| **H0 (Failed)** | AI path disabled, fallback only. | 01 |
| **Action Class (A0-A3)** | Risk classification: A0 (read-only), A1 (reversible), A2 (bounded), A3 (high-impact). | 01 |

### A.5 Timing Terms

| Term | Definition | Documents |
|------|------------|-----------|
| **T_total** | End-to-end latency budget for request. | 05 |
| **T_ai** | Maximum time allocated for AI inference. | 01, 05 |
| **T_fb** | Time budget for fallback execution. | 04, 05 |
| **T_critical** | Reserved time for policy + apply + audit. | 05 |
| **SLO** | Service Level Objective: P(T > T_slo) ≤ ε. | 05 |
| **Timeout** | AI response time exceeded T_ai, triggers fallback. | 01, 04, 05 |

### A.6 System Terms

| Term | Definition | Documents |
|------|------------|-----------|
| **Gate (Policy Gate)** | TCB component that validates AI output and enforces policy. | 01, 02, 03 |
| **Actuator** | TCB component with exclusive write access to Core. | 02 |
| **Core** | Deterministic system state, protected by TCB. | 01, 02 |
| **Decision Witness** | Complete audit record of policy decision for replay. | 03 |
| **Replay Determinism** | Property that same input + snapshot produces same output. | 02, 03, 05 |

### A.7 Cross-Document Semantic Contracts

**Contract 1**: Deny in 03 (policy) triggers Fallback in 04 (state machine).
**Contract 2**: Forbid in 03 (policy) triggers F3/Reject in 04 (no fallback).
**Contract 3**: Health H0 in 01 implies FallbackOnly state in 04.
**Contract 4**: T_ai timeout in 05 triggers Timeout event in 04.
**Contract 5**: Indeterminate in 03 treated as Deny, triggers F2 fallback.

---

## Appendix B: Leakage Budget and Data Class Policy

### B.1 Risk-Based Leakage Budget Model

**Problem**: Fixed thresholds (e.g., 0.1 bit/s) lack scientific justification. Appropriate threshold depends on secret value, exposure window, and threat model.

**Leakage Budget Formula**:
```
C_threshold = Secret_value_bits / (T_acceptable × N_channels × Safety_margin)

where:
- Secret_value_bits = entropy of the secret
- T_acceptable = maximum acceptable exposure window
- N_channels = number of potential covert channels
- Safety_margin = 1.5-2.0 (conservative factor)
```

**Example (Bitcoin Private Key)**:
```
Secret_value_bits = 256 bits
T_acceptable = 3600 seconds (1 hour)
N_channels = 3 (timing, size, contention)
Safety_margin = 2.0

C_threshold = 256 / (3600 × 3 × 2.0) = 0.012 bit/s
```

### B.2 Data Classification Policy

| Data Class | Symbol | Threshold | Leakage Budget | Primary Control |
|------------|--------|-----------|----------------|-----------------|
| Class A (Permanent Secrets) | C_A | < 0.01 bit/s | < 1 bit/session | **Data Minimization** (AI never sees) |
| Class B (Long-lived Credentials) | C_B | < 0.1 bit/s | < 100 bits/day | Threshold + Monitoring |
| Class C (Session Tokens) | C_C | < 1 bit/s | < 1000 bits/session | Monitoring |
| Class D (Public) | C_D | No limit | No limit | None |

**Critical Principle**: For Class A secrets, primary control is data minimization (AI never has access). Thresholds are secondary controls.

### B.3 Dual-Limit Enforcement

Every session must satisfy BOTH:
1. `capacity_limit` (bit/s) - instantaneous rate
2. `leakage_budget` (bits/session, bits/day) - cumulative volume

### B.4 Effective Capacity Estimation

```
C_effective = max(UCB_lab, UCB_staging, UCB_prod)

where UCB = Upper Confidence Bound (not mean!)
```

Use maximum of upper bounds, not minimum. Minimum underestimates risk.

### B.5 Infiltration/C2 Risk

Covert channels are bidirectional. Beyond exfiltration (data out), consider infiltration (commands in).

**Controls**:
- Strict determinism of input interface
- Rate/shape limits on input events
- Detection of encoded control patterns
- Quarantine on suspected C2 channel

---

## Appendix C: Emergent Behavior and Drift Governance

### C.1 Emergent Behavior as Threat Category

**Definition**: Non-adversarial model risk arising from:
1. Training data biases
2. Distribution shift in production (OOD)
3. Reward hacking (if optimization objective exists)
4. Unexpected component interactions

**Classification**: Operational hazard, not cyber attack. But for safety engineering, treated similarly due to equivalent consequences.

### C.2 Detection Methods

**Shadow Baseline Monitoring**: Run deterministic baseline in parallel, measure delta.

**Drift Detectors**:
- Feature drift
- Prediction drift
- Outcome drift

**Leading Indicators**:
- Clamp-hit rate
- Fallback rate
- Edge-of-envelope bias
- Unexplained KPI degradation

**Counterfactual Checks**: "What would baseline have done?"

### C.3 Multi-Metric Guardrail with Delayed Feedback

**Problem**: Ground truth often delayed (minutes to days). Need real-time monitoring.

**Solution**: Two-channel monitoring:

**Channel 1: Fast Risk Score (online proxies)**
- Distribution drift
- Uncertainty/OOD score
- Policy clamp rate
- Edge-of-envelope bias

**Channel 2: Slow Value Score (delayed outcomes)**
- Actual vs predicted
- Baseline comparison
- Risk events

**Decision Logic**:
```
RiskScore < 0.3 → AI disabled (immediate)
RiskScore 0.3-0.5 → Minimal influence
RiskScore 0.5-0.8 → Reduced influence
RiskScore > 0.8 AND ValueScore > 0.7 → Full AI influence
```

**Bayesian Update**: Use Bayesian approach for ValueScore to handle noise and provide uncertainty quantification.

### C.4 Distinguishing Good vs Bad Drift

**Good Drift**: AI improves, delayed outcomes better than baseline, no risk indicator growth.

**Bad Drift**: Outcomes worsen or risk indicators grow.

**Reward Hacking**: Local metric improves but system-level guards worsen.

---

## Appendix D: Control Value Test

**Purpose**: Filter new controls to avoid complexity bloat. Complexity itself is a security risk.

Add control ONLY if all 5 answers are "yes":

1. **Risk linkage**: Which specific top-risk does it reduce (ID from risk registry)?
2. **Measurable effect**: Is there a metric before/after (Δrisk, Δincident rate)?
3. **Non-duplication**: Does it duplicate existing control with same effect?
4. **Operational viability**: Does it fit latency/ops budget without alert fatigue?
5. **Failure behavior**: If this control breaks, does system remain safe (fail-closed)?

If any answer is "no", control goes to backlog, not production.

---

## Appendix E: Testing Strategy

### E.1 Threat-Driven Test Catalog

Tests organized by threat model, not by component.

| Threat | Test ID | Property | Method | Evidence |
|--------|---------|----------|--------|----------|
| Escape | ATK-1,5,6 | SAFE-1 | Attack suite | 0 of N successes |
| Covert leak | Covert tests | SAFE-4b | MI measurement | R_MI < threshold |
| Cross-tenant | CT-1..4 | SAFE-4a | Isolation tests | 0 leakage |

### E.2 Test Execution Cadence

| Trigger | Scope | Frequency |
|---------|-------|-----------|
| PR/commit | Fast gate | Every commit |
| Nightly | Deep security | Daily |
| Release | Full hardening | Per release |
| Model change | Full validation | Per model update |
| Quarterly | Red team | Quarterly |

### E.3 Negative Testing

**Challenge**: Proving AI CANNOT do something.

**Approach**: Bounded claims with statistical confidence.
- "0 successful escapes in N attempts" → upper 95% bound ≈ 3/N
- Property-based testing for forbidden transitions
- Formal model checks where possible

### E.4 Emergent Behavior Testing

**Challenge**: Testing for unanticipated behaviors.

**Approach**:
- Canary/shadow mode
- Drift and anomaly detectors
- Chaos/fault injection
- Incident learning loop updates test catalog

### E.5 Multi-Tenant Testing

**Challenge**: Testing without real sensitive data.

**Approach**:
- Synthetic tenants + adversarial workloads
- Canary tokens (seeded secrets to detect leakage)
- Tenant-isolated replay datasets
- Privacy-preserving telemetry

---

## Appendix F: Operational Readiness Checklist

### F.1 Runbooks

Required runbooks:
- Fallback activation procedure
- Quarantine response procedure
- Model rollback procedure
- Recovery from degraded state
- Emergency AI disable

### F.2 Incident Response

| Severity | Response Time | Escalation | Notification |
|----------|---------------|------------|--------------|
| Critical | Immediate (auto) | CISO + on-call | Page immediately |
| High | < 5 min | Security team | Alert |
| Medium | < 1 hour | Ticket | Email |
| Low | Next business day | Backlog | Log only |

### F.3 Monitoring Dashboards

Required dashboards:
- AI health score (real-time)
- Fallback rate by state
- Policy clamp rate
- Covert channel capacity
- Cross-tenant isolation metrics
- Latency budget utilization

**Owner**: Platform team
**Review cadence**: Daily (automated), weekly (human review)

### F.4 On-Call Model

- Primary on-call: Platform team
- Secondary: Security team
- Escalation: CISO delegate for critical incidents
- Severity routing: Automated based on alert type

### F.5 Training Matrix

| Role | Training Required | Frequency | Assessment |
|------|-------------------|-----------|------------|
| Operator | AI system overview, approval workflow | Initial + annual | Competency test |
| Engineer | Model understanding, envelope setting | Initial + updates | Technical review |
| Security | Threat model, incident response | Initial + quarterly | Tabletop exercise |
| On-call | Runbooks, escalation procedures | Initial + quarterly | Drill |

### F.6 Change Management Workflow

**Tools**: Git + MOC tracking system + approval workflow

**Approvals**:
- Model update: Dual (AI Platform + Security)
- Policy change: Dual (Security + Domain Owner)
- Infrastructure change: Single (Platform) + post-change review

**Audit Trail**: All changes logged with:
- What changed
- Who approved
- Why (rationale)
- Test evidence
- Rollback plan

### F.7 Production Readiness Criteria

System is ready for production when:
- [ ] All R&D claims validated
- [ ] Operational controls in place
- [ ] Runbooks written and reviewed
- [ ] Monitoring dashboards deployed
- [ ] On-call rotation staffed
- [ ] Training completed for all roles
- [ ] Drills completed (including AI-off drills for ICS)
- [ ] Evidence pack complete
- [ ] Incident response tested
- [ ] Rollback procedure tested

---

## Appendix B: Cross-Cutting Policies

### B.1 Claims Ledger

**Purpose**: Central registry of all safety/security claims with evidence requirements.

| Claim ID | Claim | Type | Evidence | Owner | Review |
|----------|-------|------|----------|-------|--------|
| CLM-01 | No AI escape from sandbox | Empirical | ATK-1,5,6 (0 of N) | Security | Quarterly |
| CLM-02 | Covert channel capacity bounded | Empirical | R_MI measurements | Platform | Monthly |
| CLM-03 | Consensus integrity preserved (Bitcoin) | Empirical | Replay tests (0 divergence) | Platform | Per release |
| CLM-04 | No unsafe AI-induced transitions (ICS) | Empirical | Transition monitoring | Safety | Quarterly |
| CLM-05 | Fallback activates within T_fb | Empirical | Fault injection | Platform | Monthly |
| CLM-06 | Cross-tenant isolation | Empirical | CT-1..4 tests | Security | Quarterly |
| CLM-07 | Supply chain verified | Empirical | SBOM + signatures | Security | Per release |
| CLM-08 | SIS demand rate unchanged (ICS) | Empirical | Demand rate tracking | Safety | Monthly |

**Claim Language Rules**:
- Use "no observed" instead of "cannot"
- Use "within validated scope" instead of "always"
- Use "higher assurance" instead of "maximum security"
- Specify N for "0 of N" claims
- Include confidence bounds

### B.2 Threshold Registry

**Purpose**: Single source of truth for all thresholds to prevent drift between documents.

| Threshold ID | Name | Value | Unit | Document | Rationale |
|--------------|------|-------|------|----------|-----------|
| TH-LEAK-A | Class A leakage rate | < 0.01 | bit/s | 06 | Risk-based calculation |
| TH-LEAK-B | Class B leakage rate | < 0.1 | bit/s | 06 | Risk-based calculation |
| TH-LEAK-C | Class C leakage rate | < 1.0 | bit/s | 06 | Risk-based calculation |
| TH-LAT-AI | AI inference timeout | 100 | ms | 05 | SLO requirement |
| TH-LAT-FB | Fallback activation | 50 | ms | 04, 05 | Safety requirement |
| TH-FAIR-P95 | Noisy neighbor impact | ≤ +5% | latency | 06 | QoS requirement |
| TH-FAIR-P99 | Noisy neighbor impact | ≤ +10% | latency | 06 | QoS requirement |
| TH-PRIV-PM0 | Privacy mode 0 MI | < 1.0 | bits/session | 07 | Privacy budget |
| TH-PRIV-PM1 | Privacy mode 1 MI | < 0.5 | bits/session | 07 | Privacy budget |
| TH-PRIV-PM2 | Privacy mode 2 MI | < 0.1 | bits/session | 07 | Privacy budget |
| TH-DEMAND | SIS demand rate increase | ≤ 10% | % | 08 | Safety requirement |
| TH-ALARM | AI alarm budget | ≤ 10% | % of total | 08 | Alarm management |

**Threshold Change Process**:
1. Propose change with rationale
2. Impact analysis across all documents
3. Security/Safety review
4. Update all affected documents atomically
5. Update test thresholds

### B.3 Leakage Budget and Data Class Policy

**Normative**: This policy applies to all documents and case studies.

#### B.3.1 Data Classification

| Class | Name | Examples | Primary Control |
|-------|------|----------|-----------------|
| A | Permanent Secrets | Private keys, root credentials | Data minimization (AI never sees) |
| B | Long-lived Credentials | API keys, certificates | Threshold + monitoring |
| C | Session Data | Tokens, temporary state | Monitoring |
| D | Public | Published data, public stats | None |

#### B.3.2 Leakage Budget Formula

```
C_threshold = Secret_value_bits / (T_acceptable × N_channels × Safety_margin)
```

#### B.3.3 Dual-Limit Enforcement

Every session must satisfy BOTH:
1. `capacity_limit` (bit/s) - instantaneous rate
2. `leakage_budget` (bits/session, bits/day) - cumulative volume

**Reference**: See 06-isolation-experiments.md Section 5.2-5.3 for full details.

### B.4 Emergent Behavior and Drift Governance

**Normative**: This policy applies to all AI advisory deployments.

#### B.4.1 Emergent Behavior Categories

| Category | Description | Detection |
|----------|-------------|-----------|
| OOD (Out of Distribution) | Input outside training distribution | Uncertainty scoring |
| Concept Drift | Gradual change in data patterns | Feature/prediction drift detectors |
| Reward Hacking | Optimizing proxy instead of goal | Guard metric divergence |
| Cross-component Hazard | Unexpected interactions | Integration testing |

#### B.4.2 Detection Requirements

1. Shadow baseline monitoring (parallel deterministic computation)
2. Feature drift detection (statistical tests)
3. Prediction drift detection (output distribution monitoring)
4. Outcome drift detection (delayed feedback analysis)
5. Leading indicators (clamp rate, fallback rate, edge bias)

#### B.4.3 Response Triggers

| Condition | Response |
|-----------|----------|
| Sustained abnormal delta | Degrade AI influence |
| High uncertainty/OOD | Use fallback |
| Severe mismatch | Quarantine + model rollback |
| Guard metrics diverge | Investigate reward hacking |

**Reference**: See 06-isolation-experiments.md Appendix J for full details.

### B.5 Control Value Test

**Normative**: Apply this test before adding any new security control.

#### B.5.1 The Five Questions

| # | Question | Required Answer |
|---|----------|-----------------|
| 1 | **Risk Linkage**: Which specific risk does this reduce? | Must identify risk ID |
| 2 | **Measurable Effect**: Is there a before/after metric? | Must be measurable |
| 3 | **Non-Duplication**: Does this duplicate existing control? | Must be "no" |
| 4 | **Operational Viability**: Fits latency/ops budget? | Must be "yes" |
| 5 | **Failure Behavior**: System remains safe if control fails? | Must be "yes" |

If any answer is "no", control goes to backlog, not production.

**Reference**: See 06-isolation-experiments.md Appendix H for full details.

### B.6 Risk Acceptance Governance

**Normative**: This policy governs all risk acceptance decisions.

#### B.6.1 Acceptance Limits

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Max acceptance period | 90 days | Force regular review |
| Max renewals | 2 (total 270 days) | Prevent indefinite deferral |
| After expiry without fix | Automatic service restriction | Enforce remediation |

#### B.6.2 Renewal Requirements

Each renewal requires:
1. New evidence (updated risk assessment)
2. Updated controls (compensating measures)
3. Executive approval (documented)
4. Remediation plan with deadline

#### B.6.3 Exception Anti-Creep

To prevent exception accumulation:

| Metric | Threshold | Action |
|--------|-----------|--------|
| Active exceptions | > 5 | Executive review required |
| Exception age | > 180 days | Mandatory escalation |
| Same risk renewed | > 2 times | Architecture review |
| Total exception risk | > budget | Service restriction |

#### B.6.4 Exception Registry

| Field | Description |
|-------|-------------|
| Exception ID | Unique identifier |
| Risk ID | Link to risk registry |
| Justification | Why exception needed |
| Compensating controls | What mitigates |
| Expiry date | When exception ends |
| Owner | Who is responsible |
| Renewal count | How many times renewed |
| Remediation plan | How to eliminate need |

---

## Appendix C: Testing Strategy

### C.1 Test Categories

| Category | Purpose | Frequency |
|----------|---------|-----------|
| Unit tests | Component correctness | Per commit |
| Integration tests | Cross-component behavior | Per PR |
| Security tests | Attack resistance | Nightly |
| Covert channel tests | Leakage measurement | Weekly/Release |
| Chaos/fault injection | Failure handling | Weekly |
| Red team exercises | Adversarial scenarios | Quarterly |

### C.2 Threat-Driven Test Catalog

Every threat in risk registry must have corresponding test(s):

| Threat ID | Test ID | Test Type | Pass Criteria |
|-----------|---------|-----------|---------------|
| RR-ISO-001 | ATK-1,5,6 | Security | 0 escapes in N attempts |
| RR-ISO-002 | CC-* | Covert channel | R_MI < threshold |
| RR-ISO-003 | SC-* | Supply chain | All signatures valid |
| ... | ... | ... | ... |

### C.3 Property-to-Test-to-Evidence Chain

```
Property (formal) → Test (executable) → Evidence (artifact)

Example:
SAFE-1 (No Escape) → ATK-1,5,6 tests → Test logs + "0 of N" bound
```

### C.4 Negative Testing

Proving AI CANNOT do something:

1. Bounded claims: "0 of N attempts" + upper confidence bound
2. Property-based testing for forbidden transitions
3. Fuzz testing for unexpected behaviors
4. Formal model checking where feasible

### C.5 Multi-Tenant Testing

Without real sensitive data:

1. Synthetic tenants with adversarial workloads
2. Canary tokens (seeded secret markers)
3. Tenant-isolated replay datasets
4. Privacy-preserving telemetry

---

## Appendix D: Operational Readiness Checklist

### D.1 Pre-Production Requirements

| Category | Requirement | Evidence |
|----------|-------------|----------|
| **Runbooks** | Fallback/quarantine/recovery documented | Runbook review |
| **Incident Response** | Roles, paging, SLA, escalation defined | IR plan review |
| **Monitoring** | Dashboards deployed, owners assigned | Dashboard walkthrough |
| **On-call** | Primary/secondary rotation, severity routing | On-call schedule |
| **Training** | Operators/security/platform trained | Training records |
| **Change Management** | MOC workflow implemented | MOC test run |

### D.2 Runbook Requirements

| Runbook | Contents |
|---------|----------|
| Fallback activation | Steps to manually trigger fallback |
| Quarantine procedure | Steps to isolate AI |
| Recovery procedure | Steps to restore from fallback |
| Model rollback | Steps to revert to previous model |
| Incident escalation | Contact tree, severity definitions |

### D.3 Monitoring Dashboard Requirements

| Dashboard | Metrics | Owner | Review Cadence |
|-----------|---------|-------|----------------|
| AI Health | RiskScore, ValueScore, fallback rate | Platform | Real-time |
| Security | Covert channel capacity, attack indicators | Security | Real-time |
| Operations | Latency, throughput, error rate | Ops | Real-time |
| Business | KPIs, efficiency metrics | Product | Daily |

### D.4 Training Matrix

| Role | Training Topics | Frequency |
|------|-----------------|-----------|
| Operator | AI modes, approval workflow, fallback procedures | Annual |
| Security | Threat model, attack detection, incident response | Annual |
| Platform | Architecture, monitoring, troubleshooting | Initial + updates |
| Management | Risk overview, escalation, governance | Annual |

### D.5 Production Readiness Criteria

- [ ] All R&D claims validated with evidence
- [ ] Operational controls in place
- [ ] Drills completed (including AI-off drills for ICS)
- [ ] Evidence pack complete
- [ ] Risk registry current
- [ ] Runbooks tested
- [ ] On-call rotation active
- [ ] Monitoring dashboards operational

---

*Document Version: 2.0*
*Last Updated: 2026-03-26*
*Authors: Kiro + Codex (AI Research Collaboration)*
