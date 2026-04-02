# Isolation Experiments: Security Boundaries for AI Agent Sandboxing

## Abstract

This document presents experimental methodology and results for AI agent isolation in deterministic systems. We define a variant hierarchy (V0-V6) with incremental security mechanisms, establish covert channel measurement protocols with data-class-specific thresholds, and document residual risks with ownership and response procedures. The experiments validate isolation guarantees while quantifying security-performance tradeoffs.

**Keywords**: isolation, sandbox, container security, covert channels, attack surface, defense in depth, microVM

---

## 1. Introduction

### 1.1 Motivation

AI agents in critical systems require strong isolation to:
1. **Prevent escape**: AI cannot break out of sandbox
2. **Contain damage**: Compromised AI has bounded impact
3. **Block exfiltration**: Sensitive data cannot leak via covert channels
4. **Ensure determinism**: Isolation doesn't break replay guarantees

### 1.2 Scope

**In-scope for this document**:
- AI process isolation mechanisms
- Covert channel measurement and mitigation
- Attack scenarios targeting isolation
- Security-performance tradeoffs
- Attacks that could compromise AI isolation guarantees

**Out-of-scope (cross-referenced)**:
- Full control-plane security remediation (see Security Hardening Guide)
- Kernel/hardware vulnerability patching (see Operations Guide)
- Supply chain security beyond image verification (see Build Security Guide)

### 1.3 Relationship to Other Documents

| Document | Relationship |
|----------|--------------|
| 01-ai-advisory-pattern | Sandbox assumptions operationalized here |
| 02-trust-boundary-model | Covert channels detailed here |
| 03-policy-enforcement-algebra | Policy reactions to isolation violations |
| 04-fallback-state-machine | Isolation degradation triggers fallback |
| 05-latency-budget-theory | Latency overhead from isolation |

---

## 2. Threat Model

### 2.1 Adversary Capabilities

| Adversary Type | Capabilities | Goals |
|----------------|--------------|-------|
| Malicious AI Output | Arbitrary syntactically valid output | Escape, exfiltration, integrity violation |
| Compromised AI Model | Adversarial weights/behavior | Covert channel, data theft |
| Insider | Access to configuration | Weaken isolation, exfiltrate |
| Supply Chain | Malicious dependencies | Backdoor, escape |
| Emergent Behavior | Non-adversarial model risk | OOD failures, drift, reward hacking |

**Note**: Emergent Behavior is not adversarial but has similar impact. See Section 2.4.

### 2.2 Attack Goals

| Goal | Description | Impact |
|------|-------------|--------|
| Escape | Break out of sandbox | Full system compromise |
| Exfiltration | Leak sensitive data | Confidentiality breach |
| Integrity Violation | Modify Core state | Safety violation |
| DoS | Exhaust resources | Availability loss |
| Cross-Tenant Leakage | Access other AI instances | Multi-tenant breach |

### 2.3 TCB for Isolation

**Definition 2.1 (Isolation TCB)**:
Components whose correctness is required for isolation guarantees.

| Component | Role | Trust Level |
|-----------|------|-------------|
| Kernel | Namespace/cgroup enforcement | Must be trusted |
| Container Runtime | Sandbox lifecycle | Must be trusted |
| Seccomp Filter | Syscall restriction | Must be trusted |
| Policy Gate | Mediation | Must be trusted |
| stdio_bus | IPC channel | Must be trusted |

**TCB Minimization Goal**: Reduce TCB surface while maintaining isolation guarantees.

### 2.4 Emergent Behavior as Threat Category

**Definition**: Non-adversarial model risk - unexpected AI behavior arising from:
1. Training data biases
2. Distribution shift in production (OOD - Out of Distribution)
3. Reward hacking (if optimization objective exists)
4. Concept drift over time
5. Unexpected cross-component interactions

**Why This Matters**: Emergent behavior is NOT malicious intent, but effects can be identical to attack:
- AI gives systematically wrong recommendations
- AI exploits loopholes in policy
- AI behavior changes subtly over time

**Threat Modeling Approach**: Treat emergent behavior as operational hazard with same rigor as cyber threats.

| Emergent Risk | Detection Method | Response |
|---------------|------------------|----------|
| OOD (Out of Distribution) | Uncertainty/OOD score monitoring | Fallback if score > threshold |
| Concept Drift | Feature drift + prediction drift detectors | Revalidation trigger |
| Reward Hacking | Guard metrics diverge from target metric | Investigate, tune objective |
| Cross-component Hazard | Integration testing, chaos engineering | Isolate, rollback |

**Key Insight**: Architecture must assume worst-case AI behavior, not rely on AI "good intentions".

---

## 3. Isolation Variant Hierarchy

### 3.1 Container Hardening Track

| Variant | Mechanisms | Security Level |
|---------|------------|----------------|
| V0 | None (baseline) | Unsafe |
| V1 | Process isolation (fork/exec, separate PID) | Minimal |
| V2 | V1 + Namespaces (PID, NET, MNT, USER, IPC) | Basic |
| V3 | V2 + Cgroups (CPU, memory, IO limits) | Moderate |
| V4 | V3 + Seccomp (syscall allowlist) + Capabilities drop | Strong |
| V5a | V4 + Read-only rootfs + No network (strict) | High |
| V5b | V4 + Read-only rootfs + Allowlist egress | High (operational) |

### 3.2 MicroVM Track

| Variant | Mechanisms | Security Level |
|---------|------------|----------------|
| V6a | Firecracker/Kata basic | Very High |
| V6b | V6a + V5 controls inside VM | Maximum |

### 3.3 Variant Comparison

```mermaid
flowchart TB
    subgraph "Container Track"
        V0[V0: No Isolation] --> V1[V1: Process]
        V1 --> V2[V2: Namespaces]
        V2 --> V3[V3: Cgroups]
        V3 --> V4[V4: Seccomp]
        V4 --> V5a[V5a: Strict No-Net]
        V4 --> V5b[V5b: Allowlist Egress]
    end
    
    subgraph "MicroVM Track"
        V6a[V6a: Basic MicroVM]
        V6b[V6b: Hardened MicroVM]
        V6a --> V6b
    end
    
    V5a -.->|"upgrade path"| V6a
    V5b -.->|"upgrade path"| V6a
    
    style V0 fill:#ff6666
    style V1 fill:#ffcc66
    style V2 fill:#ffcc66
    style V3 fill:#ffffcc
    style V4 fill:#ccffcc
    style V5a fill:#66ff66
    style V5b fill:#66ff66
    style V6a fill:#66ffcc
    style V6b fill:#00ffcc
```

### 3.4 V5b Egress Allowlist Specification

For operational deployments requiring network access:

```json
{
  "egress_allowlist": {
    "dns": {"hosts": ["internal-dns.local"], "port": 53},
    "ntp": {"hosts": ["ntp.internal"], "port": 123},
    "model": {"hosts": ["model-server.internal"], "port": 443},
    "telemetry": {"hosts": ["metrics.internal"], "port": 9090}
  },
  "default": "deny"
}
```

### 3.5 Seccomp Policy Management

**Problem**: Syscall ABI changes between kernel versions.

**Solution**:
1. Policy versioned per kernel version
2. CI matrix tests on kernels: 5.10, 5.15, 6.1, 6.6
3. Regression test: "no new syscalls allowed"
4. Policy generation from audit log (not manual)

```
seccomp_policy_v1.0_kernel5.15.json
seccomp_policy_v1.0_kernel6.1.json
seccomp_policy_v1.0_kernel6.6.json
```

---

## 4. Isolation Invariants

### 4.1 Core Invariants

**INV-ISO-1 (No Direct Core Write)**:
```
∀ AI process p: ¬can_write(p, Core)
```
AI cannot directly modify Core state.

**INV-ISO-2 (No Unauthorized Egress)**:
```
∀ AI process p, destination d: 
    egress(p, d) ⟹ d ∈ allowlist ∨ d = stdio_bus
```

**INV-ISO-3 (Bounded Resource Usage)**:
```
∀ AI process p: 
    cpu(p) ≤ cpu_limit ∧ 
    memory(p) ≤ memory_limit ∧
    io(p) ≤ io_limit
```

**INV-ISO-4 (Fail-Closed on Sandbox Error)**:
```
sandbox_error ⟹ terminate(AI) ∧ enter(FallbackOnly)
```

**INV-ISO-5 (No Cross-Tenant Data Flow)**:
```
∀ AI instances p1, p2: p1 ≠ p2 ⟹ ¬data_flow(p1, p2)
```

### 4.2 Invariant-to-Acceptance-Gate Traceability

| Invariant | Acceptance Gate | Verification Method |
|-----------|-----------------|---------------------|
| INV-ISO-1 | AG-1 (no escape) | Attack suite ATK-1,5,6 |
| INV-ISO-2 | AG-4 (network isolation) | Attack suite ATK-4 |
| INV-ISO-3 | AG-3 (resource limits) | Attack suite ATK-2 |
| INV-ISO-4 | AG-7 (fallback functional) | Failure injection |
| INV-ISO-5 | AG-5 (cross-tenant) | Cross-tenant tests CT-1..4 |

---

## 5. Covert Channel Analysis

### 5.1 Measurement Methodology

**Unified Protocol for All Channel Types**:

1. Sender encodes bit sequence `B` (PRBS with fixed seed)
2. Receiver observes channel-specific signal `Y` (latency/size/order/contention/error)
3. Receiver decodes `B'`
4. Calculate metrics:
   - `BER = Hamming(B, B') / |B|`
   - `Throughput = |B'_correct| / T`
   - `Goodput = Throughput × (1 - BER)`

**Primary Metric**: Empirical mutual information rate
```
R_MI = I(B;Y) / T  (bits/second)
```

This accounts for noise better than raw throughput.

**Estimator Selection**:
- Primary: Discretization + plug-in MI (binning) - stable, reproducible
- Secondary: KSG (Kraskov-Stögbauer-Grassberger) - sensitivity check

### 5.2 Risk-Based Leakage Budget Model

**Problem with Fixed Thresholds**: A fixed threshold (e.g., 0.1 bit/s) is not scientifically justified. The appropriate threshold depends on:
- Value of the secret being protected
- Acceptable exposure window
- Number of potential channels
- Required safety margin

**Leakage Budget Formula**:
```
C_threshold = Secret_value_bits / (T_acceptable × N_channels × Safety_margin)

where:
- Secret_value_bits = entropy of the secret (e.g., 256 bits for Bitcoin private key)
- T_acceptable = maximum acceptable exposure window
- N_channels = number of potential covert channels
- Safety_margin = 1.5-2.0 (conservative factor)
```

**Example Calculation (Bitcoin Private Key)**:
```
Secret_value_bits = 256 bits
T_acceptable = 3600 seconds (1 hour minimum safety)
N_channels = 3 (timing, size, contention)
Safety_margin = 2.0

C_threshold = 256 / (3600 × 3 × 2.0) = 0.012 bit/s
```

This is 8× stricter than a naive 0.1 bit/s threshold.

**Effective Capacity Estimation**:
```
C_effective = max(UCB_lab, UCB_staging, UCB_prod)

where UCB = Upper Confidence Bound (not mean!)
```

**Important**: Use maximum of upper bounds, not minimum. Minimum underestimates risk.

### 5.3 Data Class Policy

| Data Class | Symbol | Threshold | Leakage Budget | Primary Control |
|------------|--------|-----------|----------------|-----------------|
| Class A (Permanent Secrets) | C_A | < 0.01 bit/s | < 1 bit/session | **Data Minimization** (AI never sees) |
| Class B (Long-lived Credentials) | C_B | < 0.1 bit/s | < 100 bits/day | Threshold + Monitoring |
| Class C (Session Tokens) | C_C | < 1 bit/s | < 1000 bits/session | Monitoring |
| Class D (Public) | C_D | No limit | No limit | None |

**Critical Principle**: For Class A secrets, the primary control is **data minimization** (AI never has access), not leakage thresholds. Thresholds are secondary controls.

**Dual-Limit Enforcement**:
Every session must satisfy BOTH:
1. `capacity_limit` (bit/s) - instantaneous rate
2. `leakage_budget` (bits/session, bits/day) - cumulative volume

### 5.4 Session Classification Policy

**High-Water Mark Rule**: If session processes any Class A/B data, entire session evaluated against that class threshold until:
- Session ends, OR
- T_clear (5 minutes) elapsed since last sensitive operation

**Rationale**: Stateful channels can leak data processed earlier in session.

### 5.5 Channel Types and Measurement

#### 5.4.1 Timing Channels

**Mechanism**: AI modulates response time to encode bits.

**Measurement Protocol**:
1. Baseline: Run without sender modulation (noise floor)
2. Modulation: OOK (On-Off Keying) with short/long delays
3. Compare inter-event interval distributions

**Statistical Tests**:
- Kolmogorov-Smirnov (distribution distinguishability)
- ROC/AUC for bit decoder
- Permutation test for robustness

**Mitigation**: stdio_bus adds jitter, but residual capacity exists.

#### 5.4.2 Size Channels

**Mechanism**: AI modulates message size to encode bits.

**Measurement**: Same protocol, Y = message size.

**Mitigation**: Padding to fixed sizes (reduces capacity but adds overhead).

#### 5.4.3 Order Channels

**Mechanism**: AI reorders responses to encode bits.

**Measurement**: Y = response ordering relative to request ordering.

**Mitigation**: Strict FIFO enforcement in stdio_bus.

#### 5.4.4 Contention Channels

**Mechanism**: AI modulates CPU/memory load, receiver measures latency.

**Experiment Design**:
1. Sender: CPU burst / memory thrash by bits
2. Receiver: Measure latency/IPC/cache-miss proxy
3. Decode and calculate BER, R_MI

**Important Controls**:
- Fix CPU pinning and cgroup quotas
- Test shared-core vs isolated-core modes
- For memory: page cache pressure, allocator contention

#### 5.4.5 Error Channels

**Mechanism**: AI generates specific error patterns to encode bits.

**Measurement**: Y = error type/frequency.

**Mitigation**: Error normalization (all errors → generic error).

### 5.6 Channel Composition

**Problem**: Multiple channels may be used simultaneously.

**Approach**:
1. Measure each channel independently: R_timing, R_size, R_order, etc.
2. Measure joint channel: R_joint (sender modulates all simultaneously)
3. Upper bound: R_total ≤ R_joint + margin (10%)

**Super-Additivity Detection**: If R_joint > Σ(R_individual) + margin, investigate correlation and increase margin or tighten controls.

### 5.7 Covert Channel Response Matrix

| Measured Capacity | Data Class | Response |
|-------------------|------------|----------|
| < threshold | Any | PASS (green) |
| threshold to 10× | Class A/B | WARNING - enhanced monitoring |
| > 10× threshold | Class A/B | FAIL - trigger Quarantine |
| > threshold | Class C | WARNING → FAIL if sustained >5 min |

**Link to Fallback (doc 04)**:
```
covert_channel_breach(Class_A, >0.1 bit/s) → SecurityEvent → Quarantine
covert_channel_breach(Class_B, >1.0 bit/s) → SecurityEvent → F2 (Safe Default)
```

### 5.8 Infiltration/C2 Channel Risk

**Problem**: Covert channels are bidirectional. Beyond exfiltration (data out), consider infiltration (commands in).

**Infiltration Threat**: Attacker sends control signals to AI through covert channel:
- Trigger specific behaviors
- Modify AI decision patterns
- Coordinate with external attack

**Infiltration Controls**:
1. Strict determinism of input interface
2. Rate/shape limits on input events
3. Detection of encoded control patterns
4. Quarantine on suspected C2 channel

---

## 6. Attack Scenarios and Experiments

### 6.1 Container Track Attacks (V1-V5)

| ID | Attack | Method | Target Variant | Expected Result |
|----|--------|--------|----------------|-----------------|
| ATK-1 | Namespace Escape | /proc manipulation, symlink attacks, mount propagation | V2+ | Blocked |
| ATK-2 | Cgroup Bypass | Fork bomb, memory balloon, OOM trigger | V3+ | Limited |
| ATK-3 | Seccomp Evasion | Direct syscall, ptrace, eBPF injection | V4+ | Blocked |
| ATK-4 | Network Exfiltration | DNS tunneling, ICMP covert, HTTP to allowed host | V5a/V5b | Blocked/Allowlist only |
| ATK-5 | Filesystem Escape | Remount, overlay manipulation, /dev writes | V5+ | Blocked |

### 6.2 MicroVM Track Attacks (V6)

| ID | Attack | Method | Expected Result |
|----|--------|--------|-----------------|
| ATK-6 | VM Escape | Virtio exploitation, hypercall abuse | Isolated |
| ATK-7 | Side-Channel via Hypervisor | Cache timing, memory bus contention | Measure residual capacity |

### 6.3 Cross-Cutting Attacks

| ID | Attack | Method | Expected Result |
|----|--------|--------|-----------------|
| ATK-8 | Supply Chain | Image tampering, dependency confusion | Blocked by verification |
| ATK-9 | Configuration Weakness | Misconfigured seccomp, missing capability drop | Detected by policy-as-code |
| ATK-10 | IPC Protocol Abuse | Frame smuggling, oversized payloads, desync | Blocked by stdio_bus |
| ATK-11 | Secret Exfil via Logs | Leak through stderr/telemetry | Blocked by log sanitization |
| ATK-12 | Cross-Tenant Leakage | Shared cache/tmp/runtime artifacts | Blocked by isolation |
| ATK-13 | TOCTOU on Mounts | Race between check and use | Blocked by atomic operations |
| ATK-14 | Capability Abuse | Verify no_new_privs/cap-drop enforced | Verified |
| ATK-15 | Policy Timing Inference | Probe policy boundaries via timing | Mitigated by time bucketing |
| ATK-15 | Policy Timing Inference | Measure policy gate response time to infer rules | Mitigated by time bucketing |

### 6.3.1 ATK-15: Policy Timing Inference (Detail)

**Threat**: AI (or attacker controlling AI) probes policy gate to learn policy rules.

**Method**:
1. AI makes series of requests with varying parameters
2. Measures response time for each request
3. Different code paths in policy evaluation produce timing differences
4. Statistical analysis reveals policy boundaries

**Example**: AI wants to learn fee threshold. Sends requests with fee values [10, 20, 30, 40, 50]. If policy has branch at 35, timing may differ for values above/below.

**Defenses (Combined)**:
1. **Path normalization**: Same pipeline for allow/deny where possible
2. **Time bucketing**: Responses in fixed slots (5/10/20ms buckets)
3. **Bounded jitter**: Small random delay on top of bucket
4. **Rate limiting**: Cap similar queries per time window
5. **Behavioral detection**: Flag scan-like patterns → degrade/quarantine
6. **Generic error surface**: Same error format for similar rejections

**Formal Property**:
```
PolicyTimingLeakage ≤ threshold (not "0 leakage")
```

**Test**: Attacker success rate in reconstructing policy boundaries ≤ random + ε

**Policy Gate Fuzzing Requirements**:
- Parser fuzzing (malformed inputs)
- Property-based fuzzing for predicate combinations
- Differential fuzzing between policy versions
- Static analysis for unreachable/conflicting rules

### 6.4 AI-Specific Attacks

| ID | Attack | Method | Expected Result |
|----|--------|--------|-----------------|
| ATK-AI-1 | Prompt Injection → Tool Misuse | Adversarial prompt causing unsafe tool calls | Blocked by policy gate |
| ATK-AI-2 | Resource DoS | Excessive token/compute abuse | Limited by cgroups |
| ATK-AI-3 | Semantic Covert Channel | Exfil via "allowed" advisory fields | Detected by output analysis |

### 6.5 MITRE ATT&CK Mapping

| Attack | MITRE Technique |
|--------|-----------------|
| ATK-1,5,6 | T1611 (Escape to Host) |
| ATK-2 | T1499 (Resource Hijacking) |
| ATK-3 | T1068 (Exploitation for Privilege Escalation) |
| ATK-4 | T1048 (Exfiltration Over Alternative Protocol) |
| ATK-8 | T1195 (Supply Chain Compromise) |
| ATK-11 | T1537 (Transfer Data to Cloud Account) |

### 6.6 Combined Attack Scenarios

| Scenario | Attacks Combined | Rationale |
|----------|------------------|-----------|
| COMB-1 | ATK-1 + ATK-2 | Escape + resource exhaustion |
| COMB-2 | ATK-4 + ATK-11 | Exfiltration + log channel |
| COMB-3 | ATK-9 + ATK-3 | Config drift + seccomp evasion |

### 6.7 DNS Tunneling Detection (ATK-4 Detail)

Even through legitimate DNS, tunneling is possible. Detection:
- Label length/entropy analysis
- NXDOMAIN frequency
- Unusual query rate / unique subdomain churn
- Egress policy: only resolver allowlist + DNS over fixed proxy
- DLP rules on domain patterns
- Hard caps: qps/session + bytes/session

### 6.8 Policy Timing Inference (ATK-15 Detail)

**Attack**: AI (or attacker) probes policy boundaries by measuring response time.

**Method**:
1. AI makes series of requests with varying parameters
2. Measures response time for each
3. Infers policy rules from timing patterns
4. Maps policy boundaries statistically

**Example**: Fee recommendation policy has different code paths for different ranges. Timing reveals thresholds.

**Defenses**:
1. **Path normalization**: Same pipeline for allow/deny where possible
2. **Time bucketing**: Responses in fixed slots (5/10/20ms buckets)
3. **Bounded jitter**: Small noise on top of bucket
4. **Rate limiting**: Query budget on similar requests
5. **Behavioral detection**: Scan patterns trigger quarantine
6. **Generic error surface**: Same error codes/formats for similar failures

**Latency Impact**: Time bucketing adds latency. Budget T_policy_hardened in doc 05.

**Property**:
```
PolicyTimingLeakage <= threshold
```
Not "0 leakage", but bounded leakage.

**Test**: Attacker success rate in reconstructing policy boundaries ≤ acceptable level.

---

## 7. Experimental Protocol

### 7.1 Statistical Requirements

| Experiment Type | Minimum Repetitions | Rationale |
|-----------------|---------------------|-----------|
| Performance smoke | 30 | Central limit theorem |
| Stochastic attacks | 100 | Power for rare events |
| Covert channels | 100-300 | Low-bandwidth detection |
| Escape probability bounds | 1000-3000 | Rule of three (see 7.6) |

**Confidence Intervals**: 95% CI mandatory for all metrics.

**Effect Size**: Report Cohen's d or equivalent.

**Multiple Testing**: Apply Benjamini-Hochberg correction.

### 7.2 Environment Control

| Parameter | Requirement |
|-----------|-------------|
| Kernel | Pinned version (5.15 LTS or 6.1 LTS) |
| CPU Governor | Performance (not powersave) |
| CPU Isolation | Isolated cores for AI process (cpuset) |
| Memory | No swap, fixed cgroup limit |
| Network | Isolated veth or no network |

### 7.3 Measurement Protocol

```mermaid
sequenceDiagram
    participant E as Experiment
    participant S as System
    participant M as Metrics
    
    E->>S: Warm-up (30s)
    S->>M: Discard metrics
    E->>S: Baseline (60s)
    S->>M: Record baseline
    E->>S: Test phase (variable)
    S->>M: Record test metrics
    E->>S: Cool-down (10s)
    S->>M: Discard metrics
    E->>E: Repeat N times
```

### 7.4 Metrics Collection

| Metric | Source | Precision |
|--------|--------|-----------|
| Latency | clock_gettime(CLOCK_MONOTONIC) | Microsecond |
| CPU | /proc/stat or perf counters | Per-core |
| Memory | /proc/meminfo, cgroup memory.stat | Per-cgroup |
| Network | iptables counters, tcpdump | Per-packet |
| Syscalls | Seccomp audit log | Per-call |

### 7.5 Reproducibility Requirements

1. All experiments runnable from single script
2. Docker/Podman image with pinned versions
3. Random seeds fixed and documented
4. Hardware spec documented (CPU model, RAM, etc.)
5. Environment fingerprint recorded (see Appendix B)

### 7.6 Rule of Three for Escape Probability

For "0 of N" results, upper 95% confidence bound ≈ 3/N.

| N | Upper Bound | Use Case |
|---|-------------|----------|
| 1000 | < 0.3% | Standard testing |
| 3000 | < 0.1% | High-impact domains |
| 10000 | < 0.03% | Critical infrastructure |

**Business Risk Target**: Select N based on acceptable residual risk.

### 7.7 Bimodal Distribution Handling

For metrics with bimodal distributions (e.g., cache hit/miss):
1. Report p50/p95/p99/p999 (not just mean/std)
2. Report mode split ratio
3. Separate analysis per mode
4. Use Hartigan's dip test or KDE visualization

### 7.8 Covert Channel Duration

| Test Type | Duration | Purpose |
|-----------|----------|---------|
| CI (fast) | 5-10 min | Regression guard |
| Nightly | 1-4 hours | Statistical confidence |
| Release | Up to 24 hours | Critical channel validation |

### 7.9 Negative Results Documentation

Negative results (attack failed) are first-class artifacts:
- Attack hypothesis
- Preconditions
- Execution evidence/log hashes
- Why failed (blocked by X / inconclusive)
- Confidence bound ("0 of N" → upper bound)

### 7.10 Preregistered Experiment Sheet

Before each experiment, document:
- Metric to measure
- Threshold for pass/fail
- Stop condition
- Expected outcome

This prevents post-hoc rationalization.

---

## 8. Results Template

### 8.1 Per-Variant Results

| Variant | ATK-1 | ATK-2 | ATK-3 | ATK-4 | ATK-5 | Covert R_MI | Pass/Fail |
|---------|-------|-------|-------|-------|-------|-------------|-----------|
| V0 | FAIL | FAIL | FAIL | FAIL | FAIL | N/A | FAIL |
| V1 | FAIL | FAIL | FAIL | FAIL | FAIL | N/A | FAIL |
| V2 | PASS | FAIL | FAIL | FAIL | FAIL | High | FAIL |
| V3 | PASS | PASS | FAIL | FAIL | FAIL | High | FAIL |
| V4 | PASS | PASS | PASS | FAIL | FAIL | Medium | FAIL |
| V5a | PASS | PASS | PASS | PASS | PASS | Low | PASS |
| V5b | PASS | PASS | PASS | PARTIAL | PASS | Low | CONDITIONAL |
| V6a | PASS | PASS | PASS | PASS | PASS | Very Low | PASS |
| V6b | PASS | PASS | PASS | PASS | PASS | Minimal | PASS |

### 8.2 Covert Channel Results

| Channel Type | V4 R_MI | V5a R_MI | V6b R_MI | C_secret Threshold |
|--------------|---------|----------|----------|-------------------|
| Timing | TBD | TBD | TBD | < 0.1 bit/s |
| Size | TBD | TBD | TBD | < 0.1 bit/s |
| Order | TBD | TBD | TBD | < 0.1 bit/s |
| Contention | TBD | TBD | TBD | < 0.1 bit/s |
| Error | TBD | TBD | TBD | < 0.1 bit/s |
| Joint | TBD | TBD | TBD | < 0.1 bit/s |

### 8.3 Performance Overhead

| Variant | Latency Overhead | Throughput Impact | Memory Overhead |
|---------|------------------|-------------------|-----------------|
| V4 | +2% | -1% | +5 MB |
| V5a | +5% | -3% | +10 MB |
| V5b | +5% | -3% | +10 MB |
| V6a | +12% | -8% | +50 MB |
| V6b | +15% | -10% | +60 MB |


---

## 9. Residual Risk Documentation

### 9.1 Risk Registry Format

| Field | Description |
|-------|-------------|
| Risk ID | Unique identifier (RR-ISO-XXX) |
| Risk Title | Short description |
| Asset | What is at risk |
| Threat | What could exploit this |
| Likelihood | Low/Medium/High + frequency band |
| Impact | Low/Medium/High + rationale |
| Current Controls | What mitigates now |
| Residual Risk Level | After controls |
| Owner | Primary + Co-owners |
| Detection Method | How we know if exploited |
| Response Trigger | What activates response |
| Mandatory Action | What must happen |
| Fallback Mapping | Link to doc 04 state |
| Review Cadence | How often to reassess |
| Acceptance Expiry | Date when acceptance invalid |
| Evidence Links | Tests/logs/reports |

### 9.2 Risk Registry

#### RR-ISO-001: Kernel 0-day Escape

| Field | Value |
|-------|-------|
| Asset | Host system integrity |
| Threat | Unknown kernel vulnerability |
| Likelihood | Low (<10⁻⁴/day) |
| Impact | Critical (full compromise) |
| Controls | Seccomp, namespaces, regular patching |
| Residual | Medium (0-day always possible) |
| Owner | Security Team (Primary), Platform Team (Co-owner) |
| Detection | Host IDS, anomaly detection |
| Trigger | Unexpected process on host |
| Action | Isolate host, forensics, incident response |
| Fallback | → Quarantine |
| Review | Monthly + after any kernel CVE |
| Expiry | 90 days from last review |
| Evidence | Kernel patch status, IDS logs |

#### RR-ISO-002: Covert Channel Residual Capacity

| Field | Value |
|-------|-------|
| Asset | Data confidentiality |
| Threat | AI exfiltrating via timing/size channels |
| Likelihood | Medium (demonstrated in research) |
| Impact | Medium (limited bandwidth) |
| Controls | Thresholds, monitoring, V5/V6 isolation |
| Residual | Low (within acceptable thresholds) |
| Owner | Platform Team (Primary), Security Team (Co-owner) |
| Detection | Continuous covert channel monitoring |
| Trigger | Threshold breach |
| Action | Quarantine, investigate, tune controls |
| Fallback | → F2 (Safe Default) or Quarantine |
| Review | Quarterly |
| Expiry | 90 days |
| Evidence | Covert channel test results |

#### RR-ISO-003: Supply Chain Compromise

| Field | Value |
|-------|-------|
| Asset | System integrity |
| Threat | Malicious base image or dependency |
| Likelihood | Low (requires sophisticated attacker) |
| Impact | Critical (backdoor) |
| Controls | Image signing, SBOM, CVE scanning |
| Residual | Low |
| Owner | Platform Security (Primary), DevEx/Build Infra (Co-owner) |
| Detection | Signature verification, vulnerability scan |
| Trigger | Signature mismatch, critical CVE |
| Action | Block deployment, investigate |
| Fallback | → Block deployment |
| Review | Per release + monthly |
| Expiry | Per release |
| Evidence | SBOM, signature logs, CVE scan results |

#### RR-ISO-004: Third-Party Model API Trust

| Field | Value |
|-------|-------|
| Asset | AI output integrity |
| Threat | Compromised external model API |
| Likelihood | Low (vendor security) |
| Impact | High (adversarial behavior) |
| Controls | Output validation, rate limiting, egress logging, fallback to local |
| Residual | Medium (partial coverage) |
| Owner | AI Platform Team (Primary), Security Team (Co-owner) |
| Detection | Output anomaly detection, vendor SLA monitoring |
| Trigger | Anomalous output patterns, vendor incident |
| Action | Switch to fallback, investigate |
| Fallback | → F1 (Degraded) with local model |
| Review | Quarterly + after vendor incidents |
| Expiry | 90 days |
| Evidence | Vendor attestations, output logs |

#### RR-ISO-005: Configuration Drift

| Field | Value |
|-------|-------|
| Asset | Isolation integrity |
| Threat | Seccomp/capabilities/mount policy drift |
| Likelihood | Medium (operational changes) |
| Impact | High (weakened isolation) |
| Controls | Policy-as-code, hash verification, drift detection |
| Residual | Low |
| Owner | Platform Team |
| Detection | Config hash mismatch |
| Trigger | Hash mismatch detected |
| Action | Block deployment, remediate |
| Fallback | → Block deployment |
| Review | Per deployment |
| Expiry | Per deployment |
| Evidence | Config hashes, drift detection logs |

### 9.3 Risk Ownership Rules

1. Every risk MUST have Primary Owner
2. Cross-cutting risks MUST have Co-owners
3. Owner responsible for:
   - Monitoring risk status
   - Triggering response when needed
   - Updating registry on changes
   - Quarterly review

### 9.4 Risk Acceptance Governance

- Max acceptance period: 90 days
- Max renewals: 2 (total 270 days max)
- After expiry without fix: automatic service restriction
- Renewal requires: new evidence, updated controls, executive approval

---

## 10. Data Minimization Architecture

### 10.1 Principle

**Primary Control for Class A Secrets**: AI never sees Class A data. Data minimization is the first line of defense, not leakage thresholds.

**Architecture**:
```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA MINIMIZATION ARCHITECTURE                │
│                                                                 │
│  ┌─────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │  Raw Data   │───▶│  Sanitization    │───▶│  AI Advisory  │  │
│  │  (Class A)  │    │  Gateway (TCB)   │    │  (sees only   │  │
│  │             │    │                  │    │  features)    │  │
│  └─────────────┘    └──────────────────┘    └───────────────┘  │
│                              │                                   │
│                              │ transforms                        │
│                              ▼                                   │
│                     ┌─────────────────┐                          │
│                     │  Feature Store  │                          │
│                     │  (Class B/C/D)  │                          │
│                     └─────────────────┘                          │
│                                                                 │
│  Invariant: AI never has access to Raw Data zone                │
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 Sanitization Gateway

**Role**: Trusted component that transforms raw data into AI-safe features.

**Requirements**:
1. Minimal code (reduce attack surface)
2. Strict interface (allowlist features)
3. Property-based tests
4. Code review mandatory
5. Reproducible builds

**TCB Status**: Gateway is part of TCB. Compromise = access to raw data.

### 10.3 Feature Engineering for Privacy

**Bitcoin Example**:
- Raw: Private keys, full transaction graphs, addresses
- Features for AI: Fee rate buckets, mempool congestion stats, confirmation SLA class
- AI does NOT need raw transaction details for fee estimation

**ICS Example**:
- Raw: Safety parameters, commercial recipes, exact sensor values
- Features for AI: Trend statistics, spectral features, anomaly scores, normalized buckets
- AI does NOT need exact values for predictive maintenance

### 10.4 Feature Leakage Assessment

**Problem**: Even aggregated features can leak information (differential privacy problem).

**Assessment Methods**:
1. Mutual information tests (MI between features and secrets)
2. Membership inference attacks on feature outputs
3. Reconstruction attacks

**Mitigation**: Differential privacy for Class A-derived features (optional but recommended).

### 10.5 Gateway Security

**Threats**:
1. Bug in gateway code → secrets leak
2. Gateway compromise → attacker accesses raw data
3. Feature correlation → indirect secret inference

**Controls**:
1. Privilege separation (gateway has read-only access to raw store)
2. Tamper-evident audit
3. Dual-control for transform changes
4. Runtime integrity checks
5. Raw data store behind additional barriers (not "directly behind gateway")

### 10.6 Classification Ownership

**Who classifies data?**
- Policy-defined classes from domain/security owners (manual governance)
- Automated tagging/enforcement in pipeline (schema/rules/DLP)
- Periodic review + incident-driven corrections

**Responsibility**: Data owner + security team define class. System enforces.

### 10.7 Control Value Test

**Purpose**: Filter new controls to avoid complexity bloat.

Add control ONLY if all 5 answers are "yes":

1. **Risk linkage**: Which specific top-risk does it reduce (ID from risk registry)?
2. **Measurable effect**: Is there a metric before/after (Δrisk, Δincident rate, Δleakage)?
3. **Non-duplication**: Does it duplicate existing control with same effect?
4. **Operational viability**: Does it fit latency/ops budget without alert fatigue?
5. **Failure behavior**: If this control breaks, does system remain safe (fail-closed)?

If any answer is "no", control goes to backlog, not production.

**Rationale**: Complexity itself is a security risk. More code = more bugs = more attack surface.

---

## 11. Isolation Health Monitoring

### 10.1 Health Metrics

| Metric | Source | Threshold | Severity | Action |
|--------|--------|-----------|----------|--------|
| Seccomp violations | Audit log | > 0 | Critical | Alert + investigate |
| Namespace integrity | /proc checks | Any breach | Critical | Quarantine |
| Cgroup limit hits | Cgroup stats | > 90% sustained | High | Throttle/warn |
| Covert channel capacity | Continuous measurement | Per data class | Variable | Per threshold |
| Process count | Cgroup | > limit | Medium | Deny fork |
| File descriptor count | /proc/fd | > limit | Medium | Deny open |
| Network connections | Conntrack | > 0 (V5a) | Critical | Quarantine |

### 10.2 Monitoring Architecture

```mermaid
flowchart TB
    subgraph "Isolated Environment"
        AI[AI Process]
        Canary[Canary Process]
    end
    
    subgraph "Host Level"
        Collector[Collector Agent]
        Watchdog[Independent Watchdog]
    end
    
    subgraph "Analysis"
        Analyzer[Analyzer Service]
        FSM[Fallback State Machine]
    end
    
    AI -->|metrics| Collector
    Canary -->|integrity check| Collector
    Collector -->|signed metrics| Analyzer
    Watchdog -->|heartbeat check| Analyzer
    Analyzer -->|state transition| FSM
    
    Watchdog -.->|cross-check| Collector
```

### 10.3 Collector Placement

**Requirement**: Collector NOT in same trust domain as AI.

**Implementation**:
- Host-level agent (preferred)
- If sidecar: separate cgroup/namespace, no shared writable IPC with AI

### 10.4 Monitoring Overhead Budget

| Mode | CPU Overhead | Rationale |
|------|--------------|-----------|
| Continuous | ≤ 2% | Normal operation |
| Diagnostic | ≤ 5% | Warning investigation |

This is an SLO for the monitoring system itself.

### 10.5 Alert Severity Mapping

| Severity | Response Time | Escalation | Fallback Transition |
|----------|---------------|------------|---------------------|
| Critical | Immediate (auto) | Quarantine + page | → Quarantine |
| High | < 5 min | F2 + alert | → F2 |
| Medium | < 1 hour | Log + ticket | → F1 (if sustained) |
| Low | Next business day | Log only | None |

### 10.6 Monitor Health as Failure Mode

**If monitoring degrades**:
- Collector silent > 30s → assume compromised → Quarantine
- Analyzer unavailable → FallbackOnly mode
- Watchdog-Collector mismatch → investigate immediately

### 10.7 Canary Process

**Purpose**: Active verification of isolation controls from inside sandbox.

**Properties**:
- No extra privileges
- Runs periodically or on-demand
- Results signed and verified by host
- Checks: namespace boundaries, capability restrictions, filesystem access

### 10.8 Data Pipeline Integrity

- Signed metrics (HMAC with rotating keys)
- Monotonic counters (detect replay/drop)
- Anti-replay window

### 11.8 Multi-Metric Guardrail with Delayed Feedback

**Problem**: Ground truth for AI quality is often delayed (minutes to days). How to monitor in real-time?

**Solution**: Two-channel monitoring:

**Channel 1: Fast Risk Score (online proxies)**
- Distribution drift
- Uncertainty/OOD score
- Policy clamp rate
- Edge-of-envelope bias
- Constraint pressure

**Channel 2: Slow Value Score (delayed outcomes)**
- Actual vs predicted
- Baseline comparison
- Risk events

**Decision Logic**:
```
AI_influence = f(RiskScore, ValueScore)

RiskScore < 0.3 → AI disabled (immediate)
RiskScore 0.3-0.5 → Minimal influence, fallback primary
RiskScore 0.5-0.8 → Reduced influence, enhanced monitoring
RiskScore > 0.8 AND ValueScore > 0.7 → Full AI influence
```

**Bayesian Update for ValueScore**:
- Prior: Historical AI quality
- Evidence: New outcomes (with noise tolerance)
- Posterior: Updated quality estimate with credible intervals
- Transitions based on interval-based rules (not point estimates)

**Anti-Gaming**:
- AI does not see full health objective
- Part of metrics kept out-of-band
- Secondary constraints check for reward hacking

**Weights**: Fixed by governance (domain/safety owners), not learned online.

---

## 12. Cross-Tenant Isolation Tests

### 11.1 Threat Model for Multi-Tenant

| Threat | Description | Impact |
|--------|-------------|--------|
| Data leakage | Tenant A reads Tenant B data | Confidentiality breach |
| Resource starvation | Tenant A exhausts shared resources | DoS for Tenant B |
| Side-channel | Tenant A infers Tenant B activity | Information leakage |
| Privilege escalation | Tenant A gains Tenant B permissions | Integrity breach |

### 11.2 Isolation Mechanisms

| Mechanism | Purpose | Verification |
|-----------|---------|--------------|
| Separate namespaces | Process isolation | /proc inspection |
| Separate cgroups | Resource isolation | Cgroup hierarchy check |
| Separate network | Network isolation | iptables/netns audit |
| Separate storage | Data isolation | Mount inspection |
| Session affinity | Routing isolation | stdio_bus audit |

### 11.3 Test Scenarios

#### CT-1: Data Isolation

**Procedure**:
1. Tenant A writes secret data
2. Tenant B attempts to read
3. Verify: No access

**Pass Criteria**: 0 successful reads in N attempts

#### CT-2: Resource Isolation (Noisy Neighbor)

**Procedure**:
1. Tenant A runs CPU-intensive workload
2. Measure Tenant B latency impact

**Pass Criteria**:
- p95 ≤ +5%
- p99 ≤ +10%
- Error/timeout rate unchanged

**CI Implementation**: Synthetic load generator with deterministic stress profile.

#### CT-3: Side-Channel Isolation

**Procedure**:
1. Tenant A modulates resource usage
2. Tenant B measures timing
3. Calculate R_MI

**Pass Criteria**: R_MI < C_secret threshold (cross-tenant = always C_secret)

#### CT-4: Session Routing

**Procedure**:
1. Verify session IDs never cross tenants
2. Audit stdio_bus routing decisions

**Pass Criteria**: 100% correct routing

### 11.4 Failover/Restart Tests

**Additional scenarios**:
- State cleanup verification after restart
- Stale session/token reuse tests
- tmp/cache remnant scan after restart
- Route-table reconstruction correctness

### 11.5 Customer-Facing Guarantees (SLA Format)

| Guarantee | SLO | Measurement |
|-----------|-----|-------------|
| Tenant data isolation | 100% | Audit + testing |
| Resource fairness | p95 ≤ +5% impact | Continuous monitoring |
| Incident response | < 4 hours for critical | SLA tracking |

**Explicit Exclusions**: Covert channels not fully eliminable (bounded only).

### 11.6 Multi-Tenant Deployment Profiles

**Problem**: Different tenants have different risk profiles. One-size-fits-all isolation is either too expensive or too weak.

#### 11.6.1 Deployment Tier Definitions

| Tier | Name | Criteria | Isolation Level |
|------|------|----------|-----------------|
| Tier H | High Security | Class A data, regulated, high-value | V6 mandatory, dedicated infra |
| Tier M | Medium Risk | Class B data, enterprise | V5b + enhanced monitoring |
| Tier L | Standard | Class C/D data, general use | V5b baseline |

#### 11.6.2 Tier H (High Security) Requirements

- **Isolation**: V6 (microVM) mandatory
- **Infrastructure**: Dedicated compute, no sharing
- **Model**: Separate model instance per tenant
- **Approval**: Dual approval for high-impact actions
- **Audit**: Full decision witness, 7-year retention
- **Monitoring**: Enhanced, real-time alerting
- **Validation**: Quarterly security review

#### 11.6.3 Tier M (Medium Risk) Requirements

- **Isolation**: V5b + hardened shared infrastructure
- **Model**: Shared weights, but:
  - Separate KV cache per tenant
  - Tenant-scoped memory partition
  - Tenant-aware batching (no mixed sensitive classes)
- **Monitoring**: Standard + cross-tenant anomaly detection
- **Validation**: Semi-annual security review

#### 11.6.4 Tier L (Standard) Requirements

- **Isolation**: V5b baseline
- **Model**: Shared serving with standard isolation
- **Monitoring**: Standard
- **Validation**: Annual security review

#### 11.6.5 Tier Selection Criteria

| Factor | Tier H | Tier M | Tier L |
|--------|--------|--------|--------|
| Data classification | Class A | Class B | Class C/D |
| Regulatory requirements | Yes | Partial | No |
| Adversary model | Nation-state | Sophisticated | Opportunistic |
| Risk tolerance | Very low | Low | Moderate |
| Cost sensitivity | Low | Medium | High |

### 11.7 Shared Model Isolation Requirements

**Problem**: Shared LLM serving for multiple tenants creates specific risks.

#### 11.7.1 Shared Model Risks

| Risk | Mechanism | Impact |
|------|-----------|--------|
| KV Cache Leakage | Previous prompts influence responses | Cross-tenant data leak |
| Batching Inference | Timing/ordering in batch reveals info | Side-channel |
| Weight Contamination | Fine-tuning on mixed data | Knowledge leak |
| Attention Bleed | Attention across batch items | Direct data leak |

#### 11.7.2 Isolation Controls by Tier

| Control | Tier H | Tier M | Tier L |
|---------|--------|--------|--------|
| Separate model instance | Required | Optional | No |
| Separate KV cache | Required | Required | Recommended |
| No cross-tenant batching | Required | Required | No |
| Tenant-blind serving | N/A | Required | Recommended |
| Cache partition | Required | Required | Optional |
| Response shaping | Required | Recommended | Optional |

#### 11.7.3 Stateless Serving Requirements

For shared model (Tier M/L):
1. No persistent state between requests
2. KV cache cleared between tenants (or partitioned)
3. Batch composition tenant-aware
4. Response timing normalized

**Audit Evidence**: Quarterly attestation report.

---

## 12. Supply Chain Verification

### 12.1 Threat Model

| Threat | Vector | Impact |
|--------|--------|--------|
| Malicious base image | Compromised registry | Full compromise |
| Dependency confusion | Typosquatting, namespace hijack | Code execution |
| Build tampering | CI/CD compromise | Backdoor |
| Model poisoning | Malicious weights | Adversarial behavior |

### 12.2 Verification Mechanisms

| Mechanism | Purpose | Implementation |
|-----------|---------|----------------|
| Image signing | Authenticity | Cosign/Notary |
| SBOM | Transparency | SPDX/CycloneDX |
| Vulnerability scanning | Known CVEs | Trivy/Grype |
| Reproducible builds | Tamper detection | Deterministic build |
| Model hash verification | Model integrity | SHA-256 manifest |

### 12.3 Verification Pipeline

```mermaid
flowchart LR
    subgraph "Source"
        Git[Git Repo]
        Sign1[Signed Commits]
    end
    
    subgraph "Build"
        CI[CI/CD]
        SBOM[SBOM Generation]
        Attest[Attestation]
    end
    
    subgraph "Verify"
        Gate[Verification Gate]
        SigCheck[Signature Check]
        CVE[CVE Scan]
    end
    
    Git --> CI
    Sign1 --> CI
    CI --> SBOM
    CI --> Attest
    SBOM --> Gate
    Attest --> Gate
    Gate --> SigCheck
    Gate --> CVE
```

### 12.4 Acceptance Criteria

| Check | Requirement | Failure Action |
|-------|-------------|----------------|
| Signature valid | Must pass | Block deployment |
| SBOM present | Must exist | Block deployment |
| Critical CVE | 0 allowed | Block deployment |
| High CVE | < N (configurable) | Warning or block |
| Model hash match | Must match | Block deployment |

### 12.5 CVE Response Matrix

| CVE Severity | Exploitability | Required Action | Deadline | Runtime Mitigation |
|--------------|----------------|-----------------|----------|-------------------|
| Critical | Confirmed exploitable | Block deploys, isolate, emergency patch | < 24h | Tighten seccomp, disable risky features, restrict egress |
| Critical | Not exploitable | Block deploys unless exception, patch planned | < 72h | Compensating controls + monitoring |
| High | Confirmed exploitable | Patch priority | < 72h | Heightened alerting |
| High | Not exploitable | Scheduled remediation | < 14 days | Monitoring + config hardening |
| Medium | Confirmed exploitable | Planned remediation | < 30 days | Monitoring + localized restrictions |
| Medium | Not exploitable | Backlog with review | Next release | Baseline controls |
| Low | Any | Track and review | Quarterly | Baseline controls |
| Any | Exploit detected | Incident response | Immediate | FallbackOnly/Quarantine |

### 12.6 SBOM for AI Models

**Minimum contents**:
- Model artifact hash/version
- Tokenizer/version
- Runtime libs (CUDA, inference engine, deps)
- Serving container base image
- Preprocessing/postprocessing code

**Optional (if available)**:
- Dataset provenance
- Fine-tune lineage
- Evaluation reports

### 12.7 Third-Party Model APIs

**Acknowledgment**: External model supply chain is partially untrusted dependency.

**Compensating Controls**:
1. Strict output validation (policy gate)
2. Rate limiting
3. Egress logging with full request/response
4. Fallback to local model if API unavailable
5. Contractual SLA with vendor

### 12.8 Verification Frequency

| Trigger | Verification Scope |
|---------|-------------------|
| Build/Deploy | Full verification |
| Startup | Signature + hash check |
| Daily | Integrity scan |
| On threat intel | On-demand full scan |

---

## 13. Formal Properties

### 13.1 Safety Properties (Bad Things Don't Happen)

**SAFE-1 (No Escape)**:
```
□ (AI_process ⟹ ¬can_access(host_resources))
```
Always: AI process cannot access host resources.

**SAFE-2 (No Unauthorized Write)**:
```
□ (AI_write(x) ⟹ x ∈ allowed_paths)
```
Always: AI can only write to allowed paths.

**SAFE-3 (Bounded Resources)**:
```
□ (cpu(AI) ≤ limit ∧ mem(AI) ≤ limit)
```
Always: AI resources are bounded.

**SAFE-4a (Explicit Flow Noninterference)**:
```
□ (tenant(p1) ≠ tenant(p2) ⟹ ¬explicit_data_flow(p1, p2))
```
Always: No explicit/logical data flow between tenants.

**SAFE-4b (Bounded Covert Leakage)**:
```
□ (covert_capacity(p1, p2) ≤ threshold(data_class))
```
Always: Covert channel capacity within threshold.

### 13.2 Liveness Properties (Good Things Happen)

**LIVE-1 (Eventual Termination)**:
```
□ (timeout ⟹ ◇ terminated(AI))
```
Always: If timeout, AI will eventually terminate.

**LIVE-2 (Fallback Availability)**:
```
□ (AI_failure ⟹ ◇ fallback_active)
```
Always: If AI fails, fallback will eventually be active.

### 13.3 Fairness Properties

**FAIR-1 (No Starvation)**:
```
□ (admissible_load ⟹ ◇ tenant_served(t) for all t)
```
Always: Under admissible load, every tenant eventually gets served.

### 13.4 Verification Type Classification

| Property | Verification Type | Method |
|----------|-------------------|--------|
| SAFE-1 | Empirical | Attack testing (ATK-1,5,6) |
| SAFE-2 | Empirical | Filesystem audit |
| SAFE-3 | Empirical | Cgroup monitoring |
| SAFE-4a | Empirical | Routing audit |
| SAFE-4b | Empirical | Covert channel measurement |
| LIVE-1 | Empirical | Timeout tests |
| LIVE-2 | Empirical | Failure injection |
| FAIR-1 | Empirical | Load testing |
| Fallback FSM | Formal | TLA+ model (doc 04) |

**Honest Assessment**: Most properties verified empirically. Only Fallback FSM has formal TLA+ model.

### 13.5 Property-to-Evidence Traceability

| Property | Test | Metric | Threshold | Artifact |
|----------|------|--------|-----------|----------|
| SAFE-1 | ATK-1,5,6 | Escape count | 0 of N | Test logs |
| SAFE-2 | Filesystem audit | Unauthorized writes | 0 | Audit logs |
| SAFE-3 | Cgroup tests | Limit breaches | 0 | Cgroup stats |
| SAFE-4a | CT-1,4 | Data leakage | 0 | Routing logs |
| SAFE-4b | Covert tests | R_MI | < threshold | Measurement data |
| LIVE-1 | Timeout tests | Termination time | < T_max | Test logs |
| LIVE-2 | Fault injection | Fallback activation | < T_fb | Test logs |
| FAIR-1 | Load tests | Starvation events | 0 | Load test results |

---

## 14. Acceptance Gate

### 14.1 Acceptance Criteria

| ID | Criterion | Test | Pass Condition |
|----|-----------|------|----------------|
| AG-1 | No escape in attack suite | ATK-1,2,3,5,6 | 0 successful escapes in N attempts (N per risk target) |
| AG-2 | Covert channel within threshold | Covert channel tests | R_MI < threshold per data class |
| AG-3 | Resource limits enforced | ATK-2 (cgroup bypass) | 100% enforcement in all tests |
| AG-4 | Network isolation | ATK-4 | V5a: 0 egress; V5b: only allowlist |
| AG-5 | Cross-tenant isolation | CT-1,2,3,4 | 0 data leakage, p95 ≤ +5% latency |
| AG-6 | Supply chain verified | SBOM + signature + CVE scan | All checks pass |
| AG-7 | Fallback functional | Failure injection | Fallback activates within T_fb |
| AG-8 | Monitoring integrity | Collector/analyzer health | Signed metrics, alert path healthy |
| AG-9 | Config drift protection | Policy hash verification | Hashes match approved baseline |

### 14.2 Variant-Specific AG Profiles

| Variant | AG-4 Requirement |
|---------|------------------|
| V5a | 0 egress (any) |
| V5b | Only allowlist egress |
| V6a/V6b | 0 egress or allowlist (per config) |

### 14.3 Gate Process

```mermaid
flowchart LR
    Build[Build Artifact] --> Test[Test Suite]
    Test --> Results[Results Report]
    Results --> Gate{Gate Decision}
    Gate -->|All PASS| Deploy[Deploy]
    Gate -->|Any FAIL| Block[Block + Exception Process]
```

### 14.4 Canary Deployment Stage

Before full production:
1. Limited scope deployment
2. Shadow monitoring
3. Auto-rollback triggers
4. Exit criteria: No AG regressions for X hours

### 14.5 Exception Process

If criterion not passed:
1. Document specific failure
2. Risk assessment by Security Team
3. Compensating controls proposal
4. Time-bounded exception (max 30 days)
5. Mandatory remediation plan

**Exception Governance**:
- Approval: Dual (Security Owner + Platform Owner)
- High-risk: Risk committee/CISO delegate
- Max renewals: 2 (total 90 days)
- After expiry: automatic service restriction (e.g., V5a mode)

### 14.6 Flaky Test Policy

1. Classify deterministic vs stochastic tests
2. Retry budget: 2 retries
3. Quarantine flaky test with issue + owner + deadline
4. Release gate uses stable subset + nightly deep suite

### 14.7 Release Readiness Checklist

- [ ] AG-1 through AG-9 all PASS
- [ ] Canary deployment successful (X hours)
- [ ] No active exceptions OR exceptions approved with compensating controls
- [ ] Risk registry reviewed and current
- [ ] Environment fingerprint documented

---

## 15. Limitations

### 15.1 Acknowledged Limitations

1. **Kernel trust assumption**: We trust the kernel. Kernel 0-day can bypass all isolation.

2. **Covert channels not eliminated**: Residual capacity exists, only bounded.

3. **Hardware side-channels**: Spectre/Meltdown class attacks not fully mitigated in software.

4. **Supply chain partial coverage**: Third-party models (OpenAI/Anthropic) not fully verifiable.

5. **Formal verification scope**: Only state machine properties, not kernel enforcement.

6. **Multi-tenant fairness**: QoS guarantees probabilistic, not deterministic.

7. **Environment dependence**: Results sensitive to kernel/hardware/CI runner profile.

8. **Detection blind spots**: Possible false negatives in covert-channel monitoring.

9. **Operational complexity**: V5/V6 and continuous verification increase operational cost.

10. **Config drift lag**: Window between drift and detection creates risk.

11. **Statistical uncertainty**: "0 of N" is always upper bound, not absolute guarantee.

### 15.2 Novel Contributions

1. **Variant hierarchy (V0-V6)** with clear Container Track and MicroVM Track separation

2. **Data-class-specific covert channel thresholds** (C_public, C_internal, C_secret)

3. **Integrated isolation-fallback mapping** - linking isolation breaches to Fallback State Machine

4. **Residual Risk Registry format** with ownership and automated triggers

5. **Acceptance Gate framework** with statistical justification (rule of three)

6. **Integrated verification framework** combining isolation + covert capacity + fallback + acceptance gate

### 15.3 Cross-Document Mapping

| This Document | Related Document | Relationship |
|---------------|------------------|--------------|
| Covert channel thresholds | 02-trust-boundary | Confidentiality levels (C_public, C_internal, C_secret) |
| Isolation breach → Quarantine | 04-fallback-state-machine | State transitions |
| Monitoring overhead | 05-latency-budget | T_monitor budget allocation |
| Attack scenarios | 03-policy-enforcement | Policy reactions to violations |
| TCB components | 02-trust-boundary | TCB definition |
| Health metrics | 01-ai-advisory-pattern | Health levels H0-H3 |

### 15.4 Future Work

1. **Formal verification of kernel isolation** - extend TLA+ model to cover namespace/cgroup semantics

2. **Hardware-assisted isolation** - Intel TDX, AMD SEV for stronger VM isolation

3. **Automated covert channel discovery** - ML-based detection of novel channels

4. **Cross-cloud portability** - validation framework for different cloud environments

5. **Real-time threshold adaptation** - dynamic thresholds based on threat intelligence

6. **Federated isolation verification** - multi-party verification for distributed deployments

7. **Quantum-resistant considerations** - future-proofing for post-quantum threats

---

## Appendix A: Claim-Evidence Traceability

| Claim | Evidence | Section | Artifact |
|-------|----------|---------|----------|
| V5+ prevents escape | ATK-1,5,6 results | 6, 8 | Test logs |
| Covert capacity bounded | R_MI measurements | 5, 8 | Measurement data |
| Cross-tenant isolation | CT-1..4 results | 11 | Test logs |
| Supply chain verified | SBOM + signatures | 12 | Verification logs |
| Fallback functional | Fault injection | 7, 8 | Test logs |
| Monitoring healthy | Health checks | 10 | Monitoring logs |

---

## Appendix B: Environment Fingerprint Template

```json
{
  "fingerprint_version": "1.0",
  "timestamp": "ISO8601",
  "hardware": {
    "cpu_model": "string",
    "cpu_cores": "number",
    "ram_gb": "number",
    "storage_type": "string"
  },
  "software": {
    "kernel_version": "string",
    "container_runtime": "string",
    "container_runtime_version": "string",
    "seccomp_policy_hash": "sha256",
    "test_harness_commit": "git_hash"
  },
  "configuration": {
    "cpu_governor": "performance|powersave",
    "cpu_isolation": "cpuset_config",
    "memory_config": "cgroup_config",
    "network_config": "namespace_config"
  }
}
```

---

## Appendix C: Probability Threshold Glossary

| Symbol | Definition | Typical Value |
|--------|------------|---------------|
| ε | Acceptable false positive rate | 0.05 (5%) |
| BER | Bit Error Rate | Varies by channel |
| R_MI | Mutual Information Rate (bits/s) | < 0.1 for C_secret |
| N | Test repetitions | 1000-3000 |
| 3/N | Upper 95% bound for 0 successes | 0.003 for N=1000 |

---

## Appendix D: Defense-Triggered DoS Protection

To prevent attackers from causing mass fallback:

1. **Rate limit**: Max 10% of instances transition to Quarantine per minute
2. **Gradual rollout**: Isolation changes applied incrementally
3. **Circuit breaker**: If >20% in Quarantine, escalate to human review
4. **Correlation detection**: Identify coordinated attack patterns

---

## Appendix E: Monitoring Integrity Verification

**Independent Verifier Channel**:
1. Host-level watchdog (separate from Collector)
2. Cross-check: Collector metrics vs kernel audit log
3. Heartbeat with cryptographic proof of liveness
4. If Collector silent >30s: assume compromised, trigger Quarantine

---

## Appendix F: Cost-of-Security Budget

| Variant | Latency Budget | Throughput Budget | Ops Complexity |
|---------|----------------|-------------------|----------------|
| V5 | ≤ 5% overhead | ≤ 10% reduction | Moderate |
| V6 | ≤ 15% overhead | ≤ 15% reduction | High |

**Trade-off Authority**: Security + Platform + Product joint decision.

---

## Appendix G: Data Minimization Architecture

**Principle**: For Class A secrets, the primary control is preventing AI access entirely, not monitoring leakage.

### G.1 Three-Zone Data Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA MINIMIZATION ARCHITECTURE                │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              RAW ZONE (AI NEVER ACCESSES)                │   │
│  │  Class A secrets | Private keys | Raw PII | Credentials  │   │
│  │                                                          │   │
│  │  Access: TCB components only                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│                            │ Sanitization Gateway (TCB)         │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              FEATURE ZONE (AI SEES TRANSFORMED DATA)     │   │
│  │  Aggregated stats | Bucketed values | Anonymized IDs     │   │
│  │  Derived features | Normalized metrics                   │   │
│  │                                                          │   │
│  │  Access: AI advisory layer                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│                            │ Policy Gate                        │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              OUTPUT ZONE (VALIDATED RECOMMENDATIONS)     │   │
│  │  Bounded recommendations | Approved actions              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### G.2 Sanitization Gateway Requirements

The Sanitization Gateway is a TCB component that transforms raw data into AI-safe features.

| Requirement | Description |
|-------------|-------------|
| Minimal code | Small, auditable codebase |
| Strict interface | Allowlist of output features |
| Property-based tests | Verify no raw data leakage |
| Code review | Security review for all changes |
| Reproducible builds | Tamper-evident |
| Formal invariants | Key properties formally verified |

### G.3 Feature Engineering for Privacy

| Raw Data | Transformed Feature | Privacy Gain |
|----------|---------------------|--------------|
| Exact amount | Amount bucket (0-100, 100-1000, etc.) | Reduces precision |
| Timestamp | Time bucket (hour, day) | Reduces correlation |
| User ID | Hashed/anonymized ID | Prevents identification |
| Transaction graph | Aggregated flow stats | Hides structure |
| Exact balance | Balance range | Reduces precision |

### G.4 Feature Leakage Assessment

Even transformed features can leak information. Required assessments:

1. **Mutual Information test**: MI(raw, feature) < threshold
2. **Membership inference**: Can attacker determine if specific record in dataset?
3. **Attribute inference**: Can attacker infer sensitive attributes from features?
4. **Reconstruction attack**: Can attacker reconstruct raw data from features?

For Class A-derived features, consider differential privacy.

---

## Appendix H: Control Value Test

**Purpose**: Evaluate whether a new security control is worth adding.

### H.1 The Five Questions

Before adding any new control, answer these questions. If any answer is "no", the control goes to backlog, not production.

| # | Question | Required Answer |
|---|----------|-----------------|
| 1 | **Risk Linkage**: Which specific top-risk (from risk registry) does this control reduce? | Must identify specific risk ID |
| 2 | **Measurable Effect**: Is there a metric to measure before/after (Δrisk, Δincident rate, Δleakage)? | Must have measurable metric |
| 3 | **Non-Duplication**: Does this duplicate an existing control with same effect? | Must be "no" |
| 4 | **Operational Viability**: Does it fit within latency/ops budget without alert fatigue? | Must be "yes" |
| 5 | **Failure Behavior**: If this control fails, does system remain safe (fail-closed/contain)? | Must be "yes" |

### H.2 Control Prioritization

| Priority | Criteria |
|----------|----------|
| P0 (Critical) | Addresses top-3 risk, measurable, no duplication, viable, fail-safe |
| P1 (High) | Addresses top-10 risk, measurable, viable |
| P2 (Medium) | Addresses known risk, partially measurable |
| P3 (Low) | Nice-to-have, limited measurability |

### H.3 Complexity Budget

Every control adds complexity. Complexity itself is a risk.

**Rule**: If added control reduces target risk by less than it increases complexity risk, do not add.

**Complexity Indicators**:
- Lines of code added
- New dependencies
- New failure modes
- Operational burden (alerts, maintenance)
- Training requirements

---

## Appendix I: Multi-Metric Guardrail with Delayed Feedback

**Problem**: Ground truth for AI quality is often delayed (e.g., fee estimation correctness known only after confirmation).

### I.1 Two-Loop Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MULTI-METRIC GUARDRAIL                        │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              FAST LOOP (Online Proxies)                  │   │
│  │  - Distribution drift                                    │   │
│  │  - Uncertainty/OOD score                                 │   │
│  │  - Policy clamp rate                                     │   │
│  │  - Edge-of-envelope bias                                 │   │
│  │  - Divergence vs baseline                                │   │
│  │                                                          │   │
│  │  Latency: Real-time                                      │   │
│  │  Action: Immediate degrade/fallback if red               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│                            │ Feeds into                         │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              SLOW LOOP (Delayed Outcomes)                │   │
│  │  - Actual vs predicted                                   │   │
│  │  - Baseline comparison                                   │   │
│  │  - Risk events (near-miss, incident)                     │   │
│  │  - Business KPIs                                         │   │
│  │                                                          │   │
│  │  Latency: Minutes to days                                │   │
│  │  Action: Update AI quality score, adjust influence       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### I.2 Score Definitions

| Score | Source | Purpose | Update Frequency |
|-------|--------|---------|------------------|
| RiskScore | Fast loop proxies | Fail-safe control | Real-time |
| ValueScore | Delayed outcomes | AI utility assessment | Per outcome batch |

**Decision Logic**:
- RiskScore controls immediate AI influence (degrade if high)
- ValueScore controls long-term AI authority (expand/contract)

### I.3 Bayesian Update for ValueScore

To handle noise in delayed outcomes:

```
Prior: P(AI_quality) based on historical performance
Evidence: New outcome batch
Posterior: P(AI_quality | outcomes)

Transition rules based on credible intervals, not point estimates.
```

**Benefits**:
- Uncertainty quantification
- Resistance to noise (single bad outcome doesn't trigger)
- Gradual updates instead of sudden switches

### I.4 Anti-Gaming Controls

AI must not optimize the health score directly:

1. AI does not see full health objective
2. Some metrics kept out-of-band
3. Secondary constraints (reward hacking detectors)
4. Weights fixed by governance, not learned

### I.5 Distinguishing Drift Types

| Drift Type | Indicator | Response |
|------------|-----------|----------|
| Good drift (AI improving) | Outcomes better, risk stable | Expand AI authority |
| Bad drift (AI degrading) | Outcomes worse OR risk rising | Contract AI authority |
| Reward hacking | Target metric up, guard metrics down | Investigate, tune objective |

---

## Appendix J: Emergent Behavior Detection

**Problem**: AI may exhibit unexpected behavior not from malicious intent but from:
- Out-of-distribution inputs
- Concept drift
- Reward hacking
- Cross-component interactions

### J.1 Detection Methods

| Method | What It Detects | Implementation |
|--------|-----------------|----------------|
| Shadow baseline | AI divergence from deterministic baseline | Parallel computation, delta monitoring |
| Feature drift | Input distribution change | Statistical tests on feature distributions |
| Prediction drift | Output distribution change | Statistical tests on AI outputs |
| Outcome drift | Result quality change | Delayed outcome analysis |
| OOD detection | Inputs outside training distribution | Uncertainty estimation, density models |
| Anomaly detection | Unusual patterns | Statistical/ML anomaly detectors |

### J.2 Shadow Baseline Monitoring

Run deterministic baseline in parallel with AI:

```
For each request:
  ai_recommendation = AI.recommend(input)
  baseline_recommendation = Baseline.recommend(input)
  delta = |ai_recommendation - baseline_recommendation|
  
  if delta > threshold:
    log_anomaly()
    if sustained:
      degrade_ai_influence()
```

**Note**: Baseline is not "ground truth" - it's a control line for detecting change.

### J.3 Leading Indicators

Early warning signs before outcome degradation:

| Indicator | What It Signals |
|-----------|-----------------|
| Clamp hit rate increasing | AI pushing boundaries |
| Fallback rate increasing | AI reliability declining |
| Edge-of-envelope bias | AI systematically near limits |
| Unexplained KPI change | Possible hidden issue |
| Uncertainty score rising | AI less confident |

### J.4 Response Triggers

| Condition | Response |
|-----------|----------|
| Sustained abnormal delta | Degrade AI influence |
| High uncertainty/OOD | Use fallback |
| Severe mismatch | Quarantine + model rollback |
| Guard metrics diverge | Investigate reward hacking |

---

*Document Version: 2.1*
*Last Updated: 2026-03-29*
*Authors: Kiro + Codex (AI Research Collaboration)*
*Verification: Human review and approval required for all risk acceptance decisions*
