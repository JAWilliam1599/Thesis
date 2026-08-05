# Improved Slide Outline — 20-Minute Thesis Defence

**Title:** Research and Build a SysSecOps System Process for a Hybrid Cloud Environment
**Budget:** 28 slides, ~19:45 speaking, then Q&A

## What changed from the original outline

1. **Added a per-slide time budget** so the talk actually fits 20 minutes.
2. **Compressed the problem framing.** The original spent 4 slides (Background, Challenges, Gaps, Objectives) on setup. Now it is Motivation → Challenges → Gaps → one *mapping table* (Gap → Objective → RQ → Contribution). This removes repetition and makes the logic auditable at a glance.
3. **Moved the research questions forward**, next to the objectives, so the results section maps 1:1 onto them. The original introduced RQs only at slide 10.
4. **Replaced generic headings** ("Overall Workflow", "Technology Stack", "Communication Between Components") with the concrete artefact-and-decision flow that *is* the contribution.
5. **Added the risk-score equation, the severity weights and the decision thresholds**, plus a worked example. This is the most defensible technical detail and it was missing entirely.
6. **Split "Experimental Results" into one slide per RQ**, so every claim is traceable to its evidence, and moved the classifier detail next to RQ3 instead of a separate "Security Assessment Results" slide.
7. **Added an explicit Limitations / Threats to Validity slide.** Examiners will ask; owning it first is far stronger than being caught by it.
8. **Added backup slides** for anticipated questions.
9. **Promoted the two negative findings to slides of their own** (21 and 23). The pre-registered campaign established that the gate fails *open* when a scanner is missing, and that a shared decision function does not produce equal detection across the hybrid boundary. The thesis treats these as results rather than caveats, so the deck does too — burying them inside the RQ slides would invite the examiner to find them instead.

## Part 0 — Opening (1:00)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 1 | Title | 0:30 | Title, students + IDs, advisors, department, date |
| 2 | Roadmap | 0:30 | Problem → Proposed process → Risk engine → Prototype → Results |

## Part 1 — Problem and positioning (3:30)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 3 | Motivation | 0:45 | Hybrid cloud adoption; public flexibility + private control; complexity is the price |
| 4 | Four operational challenges | 0:45 | C1 heterogeneous infra · C2 late security · C3 fragmented findings · C4 SysAdmin/Dev/Sec silos |
| 5 | Research gaps | 0:45 | G1 few end-to-end frameworks · G2 continuous security stops at CI/CD · G3 no tool orchestration · G4 weak empirical validation |
| 6 | Objectives ↔ RQs (mapping table) | 0:45 | Gap → Objective → RQ → Contribution in one table |
| 7 | Contributions | 0:30 | Process · unified risk mechanism · prototype + evaluation framework |

## Part 2 — Proposed process and architecture (3:55)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 8 | Core idea: gate before deploy | 0:45 | Decide on the *synthesized* artefact; one engine for both sides; six design goals |
| 9 | Three-zone architecture | 0:50 | Zone 1 generation · Zone 2 gate · Zone 3 hybrid infra + ops; regeneration feedback loop |
| 10 | End-to-end artefact flow | 0:50 | prompt → code → template → findings → score → report → deploy → telemetry; three stable contracts |
| 11 | Hybrid topology | 0:45 | AWS + on-prem Linux; pluggable secure channel; SSM hybrid activation |
| 12 | Governance and enforcement | 0:45 | pass/review/reject, approval + rejection records, graceful degradation |

## Part 3 — Unified security assessment and risk scoring (3:40)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 13 | Why severity-only fails | 0:40 | Ignores blast radius and cost; per-tool blind spots; AI code fails by misconfiguration |
| 14 | Multi-scanner assessment | 0:45 | Checkov, cfn-lint, ansible-lint, secret regex, Infracost, AWS Config, Bandit+Semgrep; normalise + deduplicate |
| 15 | Additive score + thresholds | 0:50 | `S = Σw(sev) + c(Δ) + 5v + round(p·20)`; pass ≤ 20, review 21–80, reject > 80 |
| 16 | ML code-risk model | 0:45 | SecurityEval vs click/rich/typer; 11 features; logistic regression; train/inference parity |
| 17 | Worked example | 0:40 | 20 + 10 + 5 + 0 = 35 → review; breakdown directs remediation |

## Part 4 — Implementation and evaluation (6:10)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 18 | Prototype | 0:45 | Python modules; CLI + Streamlit share one orchestration path |
| 19 | Evaluation methodology | 0:45 | Pre-registered campaign: 30 fixtures, 48 scenarios, 154 offline runs; a rejection is *not* a failure |
| 20 | RQ1 — conformance and enforcement correctness | 0:50 | 106/106 conformance, diagonal matrix (26/25/8, 11/28/8); six invariants at 1.00; gate 102.50 s vs 7.04 s |
| 21 | Finding 1 — the score fails open | 0:45 | Checkov removed: review 54 → 9 → *pass*; secret scan removed: reject 155 → 75; absent ≡ found nothing |
| 22 | RQ2 — cross-boundary equivalence: checkpoint attainment | 0:45 | 65 runs (59 offline + 6 live); 7 checkpoints; 9 assertions, `changed=0`; reject blocked at a live host |
| 23 | Finding 2 — unequal detection | 0:45 | 11 CWE-1008 classes, two arms: baseline 7/11 cloud, 5/11 on-prem, **3/11 both** → remediated 10/11, 11/11, 10/11; `CKV_AWS_33` = right weakness, wrong words |
| 24 | RQ3 results | 0:50 | Acc 0.8710, F1 0.8667, ROC-AUC 0.8792; CM 14/2/2/13; coefficients; boundary check |
| 25 | Limitations | 0:45 | Seven: self-authored fixtures · narrow deployment evidence · scope · dataset · fail-open · coverage · no baseline |

## Part 5 — Closing (1:30)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 26 | Conclusion | 0:45 | Security as an explicit, auditable operational decision; both negative findings stated |
| 27 | Future work | 0:30 | Fail-open fix first · coverage gaps · deployment breadth · model · calibration · platforms |
| 28 | Thank you / Questions | 0:15 | — |

## Backup slides (not presented)

- B1 Connectivity options comparison — *in the deck*
- B2 Full logistic-regression coefficient table — *in the deck*
- B3 Dataset construction and filtering rules — *in the deck*
- B4 Comparison with NIST RA, CloudCAMP, ADOC, industrial IaC practice — *in the deck*
- B5 Full scanner → risk-dimension table — *planned, not yet written*
- B6 Gate report JSON schema — *planned, not yet written*
