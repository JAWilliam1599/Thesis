# Improved Slide Outline — 20-Minute Thesis Defence

**Title:** Research and Build a SysSecOps System Process for a Hybrid Cloud Environment
**Budget:** 26 slides, ~18 min speaking + ~2 min buffer, then Q&A

## What changed from the original outline

1. **Added a per-slide time budget** so the talk actually fits 20 minutes.
2. **Compressed the problem framing.** The original spent 4 slides (Background, Challenges, Gaps, Objectives) on setup. Now it is Motivation → Challenges → Gaps → one *mapping table* (Gap → Objective → RQ → Contribution). This removes repetition and makes the logic auditable at a glance.
3. **Moved the research questions forward**, next to the objectives, so the results section maps 1:1 onto them. The original introduced RQs only at slide 10.
4. **Replaced generic headings** ("Overall Workflow", "Technology Stack", "Communication Between Components") with the concrete artefact-and-decision flow that *is* the contribution.
5. **Added the risk-score equation, the severity weights and the decision thresholds**, plus a worked example. This is the most defensible technical detail and it was missing entirely.
6. **Split "Experimental Results" into one slide per RQ**, so every claim is traceable to its evidence, and moved the classifier detail next to RQ3 instead of a separate "Security Assessment Results" slide.
7. **Added an explicit Limitations / Threats to Validity slide.** Examiners will ask; owning it first is far stronger than being caught by it.
8. **Added backup slides** for anticipated questions.

## Part 0 — Opening (1.5 min)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 1 | Title | 0:30 | Title, students + IDs, advisors, department, date |
| 2 | Roadmap | 0:30 | Problem → Proposed process → Risk engine → Prototype → Results |

## Part 1 — Problem and positioning (3.5 min)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 3 | Motivation | 0:45 | Hybrid cloud adoption; public flexibility + private control; complexity is the price |
| 4 | Four operational challenges | 0:45 | C1 heterogeneous infra · C2 late security · C3 fragmented findings · C4 SysAdmin/Dev/Sec silos |
| 5 | Research gaps | 0:45 | G1 few end-to-end frameworks · G2 continuous security stops at CI/CD · G3 no tool orchestration · G4 weak empirical validation |
| 6 | Objectives ↔ RQs (mapping table) | 0:45 | Gap → Objective → RQ → Contribution in one table |
| 7 | Contributions | 0:30 | Process · unified risk mechanism · prototype + evaluation framework |

## Part 2 — Proposed process and architecture (4.5 min)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 8 | Core idea: gate before deploy | 0:45 | Decide on the *synthesized* artefact; one engine for both sides; six design goals |
| 9 | Three-zone architecture | 1:00 | Zone 1 generation · Zone 2 gate · Zone 3 hybrid infra + ops; regeneration feedback loop |
| 10 | End-to-end artefact flow | 1:00 | prompt → code → template → findings → score → report → deploy → telemetry; three stable contracts |
| 11 | Hybrid topology | 0:50 | AWS + on-prem Linux; pluggable secure channel; SSM hybrid activation |
| 12 | Governance and enforcement | 0:45 | pass/review/reject, approval + rejection records, graceful degradation |

## Part 3 — Unified security assessment and risk scoring (4 min)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 13 | Why severity-only fails | 0:40 | Ignores blast radius and cost; per-tool blind spots; AI code fails by misconfiguration |
| 14 | Multi-scanner assessment | 0:50 | Checkov, cfn-lint, ansible-lint, secret regex, Infracost, AWS Config, Bandit+Semgrep; normalise + deduplicate |
| 15 | Additive score + thresholds | 0:50 | `S = Σw(sev) + c(Δ) + 5v + round(p·20)`; pass ≤ 20, review 21–80, reject > 80 |
| 16 | ML code-risk model | 0:50 | SecurityEval vs click/rich/typer; 11 features; logistic regression; train/inference parity |
| 17 | Worked example | 0:50 | 20 + 10 + 5 + 0 = 35 → review; breakdown directs remediation |

## Part 4 — Implementation and evaluation (5 min)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 18 | Prototype | 0:45 | Python modules; CLI + Streamlit share one orchestration path |
| 19 | Evaluation methodology | 0:45 | RQ → method → evidence → measures; a rejection is *not* a failure |
| 20 | RQ1 results | 0:50 | 16/17 terminal = 94.1 %; 18 pass / 4 review / 2 reject; 0 policy violations; 5/5 degraded |
| 21 | RQ2 results | 0:45 | 15 Ansible branches; gate enforced 15/15; 6/7 deployments; named evidence gaps |
| 22 | RQ3 results | 1:00 | Acc 0.8710, F1 0.8667, ROC-AUC 0.8792; CM 14/2/2/13; coefficients; boundary check |
| 23 | Limitations | 0:45 | Small sample · Python-only scope · reference-secure labels · uncalibrated weights · fail-open risk |

## Part 5 — Closing (1.5 min)

| # | Slide | Time | Key content |
|---|-------|------|-------------|
| 24 | Conclusion | 0:45 | Security as an explicit, auditable operational decision |
| 25 | Future work | 0:30 | Controlled campaign · larger corpus · calibration + ablation · more platforms |
| 26 | Thank you / Questions | 0:15 | — |

## Backup slides (not presented)

- B1 Full scanner → risk-dimension table
- B2 Gate report JSON schema
- B3 Full logistic-regression coefficient table
- B4 Connectivity options comparison
- B5 Comparison with NIST RA, CloudCAMP, ADOC, industrial IaC practice
- B6 Dataset construction and filtering rules
