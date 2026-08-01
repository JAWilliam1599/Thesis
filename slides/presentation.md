---
marp: true
theme: default
paginate: true
size: 16:9
header: 'SysSecOps for Hybrid Cloud'
footer: 'University of Science, VNU-HCM · APCS · 2026'
style: |
  section { font-size: 26px; }
  h1 { font-size: 44px; color: #123a75; }
  h2 { font-size: 34px; color: #123a75; }
  table { font-size: 21px; }
  code { font-size: 21px; }
  section.lead { text-align: center; }
  .small { font-size: 20px; color: #555; }
---

<!-- _class: lead -->
<!-- _paginate: false -->
<!-- _header: '' -->

# Research and Build a SysSecOps System Process for a Hybrid Cloud Environment

**Nguyễn Chính Thông** — 22125102
**Huỳnh Tuấn Minh** — 22125055

Advisors: **PhD. Tran Trung Dung** · **MSc. Chung Thuy Linh**

Advanced Program in Computer Science
University of Science, VNU-HCM — 2026

<!--
0:30. Greet the committee, state the title, introduce both authors and the advisors.
-->

---

## Roadmap

1. **Problem** — why hybrid cloud operations break security
2. **Proposed process** — a SysSecOps workflow with a gate before deploy
3. **Risk engine** — turning many tools into one explainable decision
4. **Prototype** — what was actually built
5. **Results** — three research questions, three bodies of evidence
6. **Limitations & future work**

<!--
0:30. One sentence per bullet. Signal that the evaluation maps 1:1 onto the research questions.
-->

---

## Motivation: hybrid cloud raises the stakes

- Organisations combine **public-cloud elasticity** with **private-infrastructure control**
- Hybrid is now the default operating model, not an edge case
- But the combination **multiplies operational surface**:
  - two provisioning mechanisms, two security models, two identity domains
  - configuration drift and misconfiguration become the dominant failure mode
- Provisioning, administration, delivery and security assessment are typically run by **separate teams with separate tools**

> The flexibility is real — so is the coordination cost.

<!--
0:45. Set up the tension: hybrid buys flexibility and pays in complexity.
-->

---

## Four operational challenges

| | Challenge | Consequence |
|---|---|---|
| **C1** | Managing heterogeneous infrastructure | Inconsistent policy across on-prem, private and public cloud |
| **C2** | Integrating continuous security into the lifecycle | Security applied late → expensive, delayed remediation |
| **C3** | Assessing findings and prioritising risk | Many tools, many formats, no consistent prioritisation |
| **C4** | Establishing an integrated SysSecOps process | SysAdmin / Dev / Sec silos, communication gaps, no traceability |

<!--
0:45. Do not read the table. Name each challenge and give one concrete consequence.
-->

---

## Research gaps in the literature

- **G1 — Limited operational frameworks for hybrid cloud security**
  NIST RA defines *what* the components are, not *how* to operate them together
- **G2 — Continuous security stops at CI/CD**
  Rarely extended across infrastructure operations in heterogeneous environments
- **G3 — Little orchestration of heterogeneous security tools**
  Research categorises tools; far less work consolidates their outputs into one decision
- **G4 — Limited empirical validation of integrated processes**
  Conceptual architectures dominate; executable, evaluated processes are scarce

<span class="small">Myrbakken & Colomo-Palacios (2017) · Rajapakse et al. (2021) · Zhao et al. (2024) · Liu et al. (2011)</span>

<!--
0:45. Anchor each gap to a citation so the framing is not opinion.
-->

---

## Gaps → Objectives → Research questions → Contributions

| Gap | Objective | RQ | Contribution |
|---|---|---|---|
| G1, G4 | Design a SysSecOps operational process integrating infra management, assessment, enforcement and deployment | **RQ1** Operational feasibility and reliability | **C1** SysSecOps operational process |
| G2 | Extend continuous security across *both* sides of the hybrid | **RQ2** Hybrid infrastructure applicability | **C1 / C3** |
| G3 | Establish a unified security assessment mechanism over heterogeneous tools | **RQ3** Unified risk-evaluation capability | **C2** Unified risk mechanism |
| G4 | Implement and evaluate a prototype | RQ1–RQ3 | **C3** Prototype + evaluation framework |

<!--
0:45. This is the logical spine of the thesis. Walk one row end to end, then say the rest follows the same pattern.
-->

---

## Contributions

**C1 — A SysSecOps operational process for hybrid cloud**
Integrates system administration, continuous security and software delivery into one workflow, with a *common decision path* across public and private targets.

**C2 — A unified security assessment mechanism**
Normalises and deduplicates findings from multiple heterogeneous tools, combines them with cost, live compliance and a learned code-risk signal into one explainable score.

**C3 — A working prototype and reproducible evaluation framework**
End-to-end implementation plus separate acceptance criteria per research question, so a successful command or an intentional rejection is never mistaken for evidence of a broader claim.

<!--
0:30. Say each contribution in one sentence; do not read the paragraph.
-->

---

## Core idea: gate **before** deploy

- The decision is taken on the **synthesized artefact** — the CloudFormation template or the resolved Ansible play — not on the prompt or the high-level source
  → the last representation before any resource exists, and the first point where every resource and property is fully known
- **One engine for the whole hybrid**: identical weights, deduplication rules and thresholds on both sides of the trust boundary

**Design goals:** gate-before-deploy · one engine · graceful degradation · auditability · feedback-driven remediation · observability

<!--
0:45. Emphasise "synthesized artefact" — it is the single most important design decision in the architecture.
-->

---

## Three-zone reference architecture

| Zone | Name | Responsibility |
|---|---|---|
| **1** | AI + IaC local development | Generate IaC from a prompt; local validation (`cdk synth`, `cdk diff`, `--syntax-check`) |
| **2** | **IaC security gate** | Multi-scanner analysis, cross-source deduplication, risk scoring, deploy decision |
| **3** | Hybrid infrastructure & ops monitoring | Provision AWS + on-prem; publish telemetry; drift / remediation loop |

```
Zone 1 ──templates──▶ Zone 2 ──pass / approved──▶ Zone 3
   ▲                     │
   └──reject: inject findings back into the prompt◀─┘
```

Zones are **loosely coupled**: Zone 1 knows nothing of the scoring rules, Zone 3 knows nothing of how the decision was reached.

<!--
1:00. Zone 2 is the contribution. Point out the dashed feedback edge: rejected generated code is regenerated with the findings injected into the next prompt.
-->

---

## End-to-end artefact flow

```
prompt / project ──▶ generated code ──▶ synthesized template ──▶ normalized findings
                                                                        │
                          telemetry ◀── deploy ◀── gate report ◀── score & decision
                                                                        │
                              └────────── reject: regenerate ───────────┘
```

**Three stable data contracts hold the system together**

- **Gate report** — `score`, `decision`, `components`, deduplicated `findings`, `scanner_status`
- **Execution result** — every external command returns `{return_code, output}` (streams merged to preserve ordering)
- **Gate-decision event** — `(target, score, decision, timestamp)` → SSM Parameter Store + EventBridge

<!--
1:00. Each stage transforms its input into a more concrete representation. The contracts are why the generator, the scanner set and the monitoring stack can evolve independently.
-->

---

## Hybrid deployment topology

- **Public side** — AWS: CDK → CloudFormation (VPC, EC2, S3, RDS), SSM, EventBridge, CloudWatch, CloudTrail, Lambda ops-loop, SNS
- **Private side** — on-premises Linux nodes configured by **Ansible**, registered via **SSM hybrid activation** as `mi-*` managed instances
- **No public inbound administrative access**: the control plane traverses the encrypted link

**Connectivity is a pluggable concern** — mesh overlay VPN (Tailscale/WireGuard) · AWS Site-to-Site VPN (IPsec) · Direct Connect · Transit Gateway · SSM over public endpoints

> The choice of link changes nothing in the gate, the scoring or the governance behaviour.

<!--
0:50. Stress the portability argument: connectivity is orthogonal to the contribution.
-->

---

## Governance and enforcement

- **pass** → auto-deploy · **review** → deployment blocked until an explicit approval record exists · **reject** → not deployed; regenerate or return to the author
- Every decision persisted as an **immutable record with the acting identity** (append-only audit trail)
- **Graceful degradation contract** — a missing scanner binary or absent credential degrades to a well-defined `skipped` status; the gate still produces a decision, and the report records *which* sources actually ran
- Credentials are **never** passed as command-line arguments — resolved through provider chains, injected via the environment

<!--
0:45. Note that the "skipped" status is recorded in the report, so a weakly-evidenced decision is visible rather than silent.
-->

---

## Why severity-only scoring is not enough

- **Severity ignores blast radius and cost.** The same open security-group rule on an internet-facing load balancer and on an isolated subnet share a severity label but not an exposure.
- **Every single tool has blind spots.** A policy scanner, a template linter, a cost estimator, a live-compliance service and a code model each see a different slice — relying on one yields systematic false negatives.
- **AI generation shifts the risk profile.** The dominant failure mode is not a novel exploit but a *plausible misconfiguration*, so a learned probability of insecurity is as useful as any single rule.

<!--
0:40. This slide justifies why a purpose-built score exists at all instead of reusing CVSS.
-->

---

## Multi-scanner assessment and normalisation

| Tool | Signal | Dimension |
|---|---|---|
| `cfn-lint` | CloudFormation validity & best practice | misconfiguration |
| Checkov | Policy-as-code findings on templates | misconfiguration |
| `ansible-lint` | Best-practice & security findings on plays | misconfiguration |
| Regex secret scanner | Hard-coded credentials | misconfiguration |
| Infracost | Estimated monthly cost / delta | cost |
| AWS Config | Count of non-compliant live rules | compliance |
| Bandit + Semgrep → logistic regression | P(code is insecure) | code risk |

**Deduplication key:** `(resource_id, template, category)` — colliding findings merge, keeping the highest severity and unioning the source labels.

<!--
0:50. Without deduplication, an issue reported by three tools triples its contribution and can push an acceptable change over a threshold.
-->

---

## The additive risk score

$$
S \;=\; \underbrace{\sum_{f \in F} w(\mathrm{sev}(f))}_{\text{severity}}
\;+\; \underbrace{c(\Delta)}_{\text{cost}}
\;+\; \underbrace{5v}_{\text{compliance}}
\;+\; \underbrace{\mathrm{round}(p \cdot 20)}_{\text{ML code risk}}
$$

| Severity | Points | | Decision | Band | Action |
|---|---|---|---|---|---|
| Critical | 20 | | **Pass** | $S \le 20$ | Auto-deploy |
| High | 10 | | **Review** | $21 \le S \le 80$ | Manual approval required |
| Medium | 5 | | **Reject** | $S > 80$ | Do not deploy; regenerate |
| Low | 1 | | | | |

Cost is **banded**, not continuous — this keeps the score stable against estimation noise.
The additive form is what makes the report **explainable**: every point is attributable to a component.

<!--
0:50. Say explicitly: the additive form is a deliberate simplification of a general multi-factor risk model, chosen for transparency and reproducibility.
-->

---

## Machine-learning code-risk component

- **Corpus** — positives from **SecurityEval** (CWE-labelled insecure Python); negatives sampled from maintained projects (`click`, `rich`, `typer`)
- **Features** — 11-dimensional count vector: Bandit severity ×3, Bandit confidence ×3, Semgrep severity ×3, two totals
- **Model** — logistic regression, 80/20 stratified split, standardised features, balanced class weights
- **Inference/training parity** — same analysers, same grouping, **same persisted scaler**
- $p = \max_{k \in \text{files}} \sigma(\mathbf{w}^\top \mathbf{x}_k + b)$ — worst file wins, so one risky file cannot be masked by many benign ones
- Unavailable model or analyser → `skipped`, contributes **0 points**

<span class="small">Scope statement: the model estimates **detector-visible** insecurity, not semantic flaws invisible to Bandit and Semgrep.</span>

<!--
0:50. Volunteer the scope statement. Roughly half of the original SecurityEval samples contain logic errors the analysers cannot see; retaining them capped recall near 0.46.
-->

---

## Worked example: traceability in practice

A change with **1 high** + **2 medium** deduplicated findings, a **medium cost band**, **1 non-compliant live rule**, and model output $p = 0$:

$$
S = \underbrace{(10 + 5 + 5)}_{20} + \underbrace{10}_{\text{cost}} + \underbrace{5 \times 1}_{\text{compliance}} + \underbrace{0}_{\text{ML}} = 35
$$

Since $20 < 35 \le 80$ → **review**: routed to a human approver, whose decision enters the audit trail.

The per-component breakdown — severity 20, cost 10, compliance 5, ML 0 — tells the approver that the **open administrative port and the cost increase** dominate, directing remediation precisely instead of handing over an opaque number.

<!--
0:50. This is the answer to "why not just use a black-box model?" — the operator can act on the breakdown.
-->

---

## Prototype

| Module | Responsibility |
|---|---|
| `generation/` | Provider-abstracted code generation (Bedrock / OpenRouter), CDK regeneration loop |
| `security_gate/` | Scanner adapters, deduplication, risk scoring, report assembly |
| `execution/` | Subprocess backbone with a stable result contract |
| `pipeline/` | synth–gate–diff–deploy orchestration, approval audit trail, credentials |
| `monitoring/` | CloudTrail, CloudWatch, ops-loop Lambda, on-prem SSM registration |
| `risk_scoring/` | Training and evaluation of the code-risk model |
| `ui/` · `scripts/` | Streamlit operator console · CLI entry points |

The console and the CLI invoke **the same orchestration logic** — a GUI operation follows the identical generate → assess → approve → deploy sequence.

<!--
0:45. Emphasise the shared orchestration path: the UI cannot bypass the gate.
-->

---

## Evaluation methodology

| RQ | Method | Evidence | Measures |
|---|---|---|---|
| **RQ1** | End-to-end pipeline scenarios incl. a degraded-component case | Stage results, gate reports, deployment & monitoring records | Completion rate, unexpected failures, decision enforcement |
| **RQ2** | Existing on-prem Linux node via Ansible over a mesh VPN, shared risk engine | Connectivity, playbook analysis, gate reports, execution records | Integration & configuration success, policy enforcement |
| **RQ3** | Held-out classifier evaluation + controlled boundary cases | Labels, probabilities, confusion matrix, component scores | Accuracy, P/R/F1, ROC-AUC, score & decision correctness |

**A security rejection is not a pipeline failure.** A run that identifies an unacceptable change, emits a valid *reject* and blocks deployment is *correct* execution.

<!--
0:45. This definition is essential — otherwise the reliability metric would be gamed by counting rejections as errors.
-->

---

## RQ1 — Operational feasibility and reliability

| Measure | Result |
|---|---|
| Total pipeline runs | **17** |
| Runs reaching a valid terminal decision | **16** → **94.1 %** completion |
| Branch-level decisions ($n = 24$: 9 CDK, 15 Ansible) | **18 pass / 4 review / 2 reject** |
| Rejected changes incorrectly deployed | **0 of 2** |
| Review cases executed without approval | **0 of 4** |
| Degraded-component runs reaching a terminal state | **5 of 5 (100 %)** |
| Unexpected pipeline failures | **2** |

The two failures were **not** gate decisions: one invocation terminated after writing only a log header; one Ansible branch passed its gate (score 0) then returned a non-zero exit at deploy.

<!--
0:50. Own the two failures. State plainly that the sample was accumulated during iterative development, so this is an initial operational indication, not a statistically powered trial.
-->

---

## RQ2 — Hybrid infrastructure applicability

An **existing** Linux VM, reached over a **mesh-VPN** link, governed by the **same** risk engine and thresholds as the cloud side.

| Checkpoint | Result |
|---|---|
| Playbook syntax validation | Passed **15/15** |
| Security assessment & gate decision | Pass **15/15** (score 0) |
| Gate executed **before** deployment | **15/15** |
| Requested configuration applied | **6 of 7** deployment attempts |
| Operational & audit records created | **16/16** completed runs |
| Post-deployment state verification · idempotency | **Not captured** — reported as evidence gaps |

Every recorded private-side decision was a *pass*, so review/reject enforcement on this path is **inferred from the shared decision function**, not directly observed.

<!--
0:45. Reporting the gaps as gaps rather than assigning an unsupported result is a deliberate methodological choice; say so.
-->

---

## RQ3 — Unified risk-evaluation capability

**Held-out classifier performance** ($n = 31$: 16 negative, 15 positive)

| Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| **0.8710** | 0.8667 | 0.8667 | 0.8667 | **0.8792** |

| Confusion matrix | Predicted − | Predicted + | | Top coefficients | |
|---|---|---|---|---|---|
| **Actual −** | 14 | 2 | | `total_semgrep` | 1.136 |
| **Actual +** | 2 | 13 | | `bandit_conf_medium` | 1.004 |
| | | | | `semgrep_high` | 0.915 |

**Controlled gate-decision check:** $S=20 \to$ pass · $S=21 \to$ review · $S=80 \to$ review · $S=81 \to$ reject · duplicate finding across tools → **counted once**. All five cases agreed with the specification.

<!--
1:00. The model draws on both analysers, not one. The two false negatives matter operationally: labelled-insecure files that receive a lower learned contribution.
-->

---

## Limitations and threats to validity

1. **Small, informally sampled evaluation** — 17 pipeline runs and 15 Ansible branches accumulated during development; only 2 reject and 4 review outcomes
2. **Restricted implementation scope** — Python + Bandit/Semgrep; AWS CDK/CloudFormation + Ansible. No claim of transfer to other languages, providers or vulnerability classes
3. **Dataset and model validity** — 31 held-out samples from one split; undetectable categories excluded; negatives are *reference secure*, not verified secure
4. **Uncalibrated risk assumptions** — weights, cost bands and thresholds are an **operational policy**, not a universal definition of risk
5. **Fail-open risk** — a skipped scanner contributes 0 points; an assurance penalty or fail-closed mode is needed for high-risk environments

<!--
0:45. Deliver this confidently and quickly. Volunteering limitation 5 in particular pre-empts the sharpest likely question.
-->

---

## Conclusion

- Hybrid cloud fragments provisioning, administration, delivery and security; this work makes **security an explicit, auditable operational decision** inside that lifecycle
- **One process, one engine, both sides** of the hybrid — the same weights, deduplication and thresholds govern a CloudFormation template and an Ansible play
- The **additive score** converts heterogeneous tool output into a single decision *without* losing the per-component explanation
- The prototype demonstrates end-to-end feasibility on an initial operational sample: **94.1 %** completion, **0** policy violations, **0.87** classifier accuracy
- Findings establish **prototype and component feasibility**, not general operational effectiveness at scale

<!--
0:45. Restate the central proposition: security as a decision function, not a post-deployment activity.
-->

---

## Future work

- **Controlled evaluation campaign** — predetermined counts of pass / review / reject / degraded runs; instrument the orchestrator so an unattributed `deploy_failed` can be diagnosed
- **Close the RQ2 gaps** — direct target-state verification, repeated-run idempotency, deliberate review/reject scenarios on the private-side path
- **Strengthen the model** — larger multi-project corpus, project-aware partitioning, repeated cross-validation, external test set, and a retained *challenge set* of analyser-invisible flaws
- **Calibrate the score** — expert judgement, historical incidents, sensitivity and ablation analysis; configurable fail-closed behaviour
- **Broaden coverage** — more cloud providers, more languages, and an operator study on whether the breakdown genuinely aids remediation

<!--
0:30. Frame these as the concrete agenda the limitations imply, not as a wish list.
-->

---

<!-- _class: lead -->
<!-- _paginate: false -->

# Thank you

## Questions and discussion

**Nguyễn Chính Thông** · **Huỳnh Tuấn Minh**
Advisors: PhD. Tran Trung Dung · MSc. Chung Thuy Linh

<!--
0:15.
-->

---

<!-- Backup slide -->

## Backup — Connectivity options

| Method | Mechanism | Trade-offs |
|---|---|---|
| Mesh overlay VPN (Tailscale/WireGuard) | Userspace WireGuard, NAT traversal, identity ACLs | Fast, no inbound ports; depends on an agent + coordination service |
| AWS Site-to-Site VPN (IPsec) | Managed tunnels to a virtual private / transit gateway | Standards-based; needs a gateway device, bandwidth-limited per tunnel |
| AWS Direct Connect | Dedicated private circuit | Low latency, stable bandwidth; cost and lead time, usually paired with a VPN |
| Transit Gateway / VPN CloudHub | Managed hub-and-spoke routing | Scales multi-site routing; adds a managed tier and cost |
| SSM hybrid activation over public endpoints | Agent reaches SSM endpoints over TLS 443 | Simplest management-plane reach; no private data-plane connectivity |

---

<!-- Backup slide -->

## Backup — Full model coefficients

| Feature | Coefficient | | Feature | Coefficient |
|---|---|---|---|---|
| `total_semgrep` | 1.136296 | | `bandit_high` | 0.435620 |
| `bandit_conf_medium` | 1.003949 | | `bandit_low` | 0.261740 |
| `semgrep_high` | 0.914679 | | `bandit_conf_high` | 0.138912 |
| `semgrep_medium` | 0.720708 | | `bandit_conf_low` | 0.083852 |
| `total_bandit` | 0.610932 | | `semgrep_low` | 0.067123 |
| `bandit_medium` | 0.454592 | | | |

Features were standardised before training, so magnitudes indicate relative influence **within this fitted model**. Total-finding features are mathematically related to the severity counts, introducing correlated predictors — the coefficients describe the model, not causation.

---

<!-- Backup slide -->

## Backup — Dataset construction

- **Positive class** — SecurityEval, CWE-labelled insecure Python, one file per sample, label 1
- **Negative class** — files sampled from `click`, `rich`, `typer`, label 0 (*reference secure*)
- **Filtering** — exclude package initialisers and tests; admit files with 20–700 non-blank, non-comment lines (model corpus narrowed to 20–300 lines to match SecurityEval scale)
- **Exclusion** — vulnerability categories not representable by the configured Bandit/Semgrep features were removed, keeping ≈15 % as hard negatives
- **Effect** — an initial model over the unfiltered corpus reached only ≈0.73 accuracy with recall ≈0.46; the filtered corpus makes the chosen features informative
- **Result** — ≈150 samples, near-balanced; 31-file held-out partition

---

<!-- Backup slide -->

## Backup — Comparison with related approaches

| Approach | Primary emphasis | Relationship to this work |
|---|---|---|
| Traditional operations | Separately coordinated provisioning, administration, review | This work integrates the transitions; no quantitative manual baseline yet |
| NIST Reference Architecture | Vendor-neutral actors and components | Supplies context; this work adds a concrete but less vendor-neutral sequence |
| CloudCAMP | Model-driven generation, less manual scripting | Stronger platform abstraction; this work emphasises gating and traceability |
| Industrial IaC practice | Adoption, integration, maintenance challenges | Normalisation addresses heterogeneous output but creates an adapter layer to maintain |
| Continuous security (ADOC, Rajapakse et al.) | Lifecycle security, tool integration, triage | This work adds hybrid decision control and an explainable quantitative score |
