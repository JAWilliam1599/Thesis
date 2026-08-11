# Presentation Script — English
**Research and Build a SysSecOps System Process for a Hybrid Cloud Environment**
Total budget: ~19:45 + Q&A. Matches the slide order in `presentation.md` and the timing in `OUTLINE.md`.

---

## 1. Title (0:30)
Good morning/afternoon, members of the committee. My name is Nguyễn Chính Thông, and together with my colleague Huỳnh Tuấn Minh, we will present our thesis: "Research and Build a SysSecOps System Process for a Hybrid Cloud Environment." This work was carried out under the supervision of Dr. Tran Trung Dung and MSc. Chung Thuy Linh, in the Advanced Program in Computer Science at the University of Science, VNU-HCM.

## 2. Roadmap (0:30)
Our presentation has five parts. First, the problem: why hybrid-cloud operations tend to break security guarantees. Second, our proposed process — a SysSecOps workflow built around a security gate placed before deployment. Third, the risk-scoring engine that turns the output of many heterogeneous tools into a single, explainable decision. Fourth, the prototype we actually built. And fifth, our results, organized around three research questions, followed by limitations and future work.

## 3. Motivation: hybrid cloud raises the stakes (0:45)
Modern organizations increasingly combine the elasticity of the public cloud with the control that private, on-premises infrastructure offers. Hybrid cloud is no longer a niche configuration — it is fast becoming the default operating model. But this combination multiplies the operational surface an organization must secure: two provisioning mechanisms, two security models, two identity domains to reconcile. Configuration drift and misconfiguration become the dominant failure mode, because the same policy has to be expressed and enforced twice, in two different technical vocabularies. In practice, provisioning, system administration, software delivery, and security assessment are usually carried out by separate teams, using separate tools, with no shared decision path. The flexibility hybrid cloud offers is real — so is the coordination cost it imposes.

## 4. Four operational challenges (0:45)
We distill this tension into four concrete challenges. **C1**: managing heterogeneous infrastructure leads to inconsistent policy across on-premises, private, and public-cloud targets. **C2**: security integrated only at the CI/CD stage is applied too late, so remediation becomes expensive and delayed. **C3**: security assessment today produces many findings, in many formats, from many tools, with no consistent way to prioritize them. **C4**: without an integrated SysSecOps process, system-administration, development, and security teams remain siloed, with communication gaps and no end-to-end traceability of decisions.

## 5. Research gaps in the literature (0:45)
These challenges map onto four gaps in the literature. **G1**: existing frameworks, such as the NIST Reference Architecture, define what the components of a hybrid-cloud security system should be, not how to operate them together. **G2**: continuous-security research largely stops at the CI/CD boundary, rarely extending across infrastructure operations in genuinely hybrid environments. **G3**: prior work tends to categorize security tools individually; far less work consolidates their outputs into a single, usable decision. **G4**: empirical validation of integrated processes is limited — most proposals remain conceptual architectures, with few executable, evaluated implementations. Each gap is grounded in the cited literature: Myrbakken and Colomo-Palacios, Rajapakse et al., Zhao et al., and Liu et al.

## 6. Contributions (0:30)
This thesis makes three contributions. **C1**: a SysSecOps operational process for hybrid cloud, integrating system administration, continuous security, and software delivery into one workflow, with a common decision path shared by public and private infrastructure. **C2**: a unified security-assessment mechanism that normalizes and deduplicates findings from multiple heterogeneous tools and combines them with cost, live compliance, and a learned code-risk signal into one explainable score. **C3**: a working prototype and a reproducible evaluation framework, with separate acceptance criteria per research question, so a successful command and a deliberate, correct rejection are never confused with one another.

## 7. Core idea: gate before deploy (0:45)
The central design decision is *where* the security decision is made. We take it on the **synthesized artefact** — the CloudFormation template, or the fully resolved Ansible play — rather than on the prompt or the high-level source code. 

This is the last representation before any real resource exists, and the first point at which every resource and property is fully known. Just as important: we use **one engine** for the whole hybrid environment — identical weights, deduplication rules, and thresholds, whether the target is an AWS account or an on-premises host. 

Six design goals guide this: gate before deploy, one engine for both sides, graceful degradation, auditability, feedback-driven remediation, and observability.

## 8. Three-zone reference architecture (0:50)
The architecture has three loosely coupled zones. 

**Zone 1** — AI-assisted local IaC development: a prompt produces generated code, locally validated (`cdk synth`, `cdk diff`, syntax check). 

**Zone 2** — the IaC security gate: multi-scanner analysis, cross-source deduplication, risk scoring, and the deploy decision. 

**Zone 3** — hybrid infrastructure and operations monitoring: provisions AWS and on-premises resources, publishes telemetry, runs the drift-and-remediation loop. 

Zone 1 knows nothing about Zone 2's scoring rules; 
Zone 3 knows nothing about how the decision was reached. Critically, there is a feedback edge: on rejection, Zone 2's findings are injected back into the prompt so Zone 1 can regenerate a corrected version.

## 9. End-to-end artefact flow (0:50)
Tracing an artefact through the system: 
a prompt or existing project produces generated code; 
the code is synthesized into a template; 
the template is scanned and findings normalized; 
findings are scored into a decision; 
on pass or approved review, the change deploys and telemetry flows back; 
on reject, findings instead regenerate the code, closing the loop. 

Three stable contracts hold the pipeline together, letting each module evolve independently. 
The **gate report** always carries a score, a decision, a component breakdown, deduplicated findings, and a scanner-status record. 
The **execution result** — for every external command — is always `{return_code, output}`. 
The **gate-decision event** — target, score, decision, timestamp — is published to SSM Parameter Store and EventBridge, so downstream monitoring and governance can react.

## 10. Hybrid deployment topology (0:45)
On the public side, we provision AWS resources — VPC, EC2, S3, RDS — via CDK synthesizing CloudFormation, alongside SSM, EventBridge, CloudWatch, CloudTrail, a Lambda ops-loop, and SNS. 

On the private side, on-premises Linux nodes are configured with Ansible and registered via SSM hybrid activation. 

There is no public inbound administrative access — the control plane always traverses the encrypted link. 

That link is a pluggable concern: a mesh overlay VPN (Tailscale/WireGuard), an AWS Site-to-Site IPsec VPN, Direct Connect, a Transit Gateway, or SSM over public endpoints. The choice of connectivity changes nothing about the gate, the scoring, or the governance behaviour — it is orthogonal to our contribution.

## 11. Multi-scanner assessment and normalisation (0:45)
We assess infrastructure using seven signal sources, each covering a different risk dimension: 

`cfn-lint` for CloudFormation validity and best practice; 

Checkov for policy-as-code on templates; 

`ansible-lint` for best practice and security on plays; 

a regex scanner for hard-coded credentials; 

Infracost for estimated cost and cost delta; 

AWS Config for the count of non-compliant live rules; 

and Bandit plus Semgrep features feeding a logistic-regression model that estimates the probability the generated code is insecure. 

All findings are normalized into one schema, then deduplicated by the key **(resource_id, template, category)**: colliding findings keep the highest severity and union the source labels. Without this, a single real issue reported by three tools would count three times and could push an acceptable change over the rejection threshold.

## 12. The additive risk score (0:50)
The final score is additive, with four components. **Severity** sums a fixed weight per deduplicated finding — 20 for critical, 10 for high, 5 for medium, 1 for low. **Cost** is a banded function of the estimated cost delta — banded, not continuous, so the score stays stable against estimation noise. **Compliance** adds 5 points per currently non-compliant live AWS Config rule. **ML** adds the rounded, exponentially-weighted probability from the code-risk model. The score maps onto three bands: **pass** at 20 or below (auto-deploy); **review** between 21 and 80 (manual approval required); **reject** above 80 (blocks deployment, returns for regeneration). The additive form is deliberate: every point is attributable to a component, so the report stays explainable to whoever must act on it.

## 13. Machine-learning code-risk component (0:45)
The code-risk component is a logistic-regression classifier. Its positive class comes from SecurityEval — CWE-labelled insecure Python; its negative class is sampled from maintained open-source projects: click, rich, typer. We extract an 11-dimensional feature vector per file — Bandit severity, Bandit confidence, Semgrep severity, and two totals. The model uses an 80/20 stratified split, standardized features, balanced class weights, and — critically — training and inference share the same analysers, the same grouping, and the same persisted scaler, so there is no train/inference skew. Across multiple files, we take the **maximum** predicted probability — the worst file wins — so one risky file can never be masked by averaging against many benign ones. If the model or an analyser is unavailable, the component is marked skipped and contributes zero points. Scope statement: this model estimates **detector-visible** insecurity — what Bandit and Semgrep can see — not semantic flaws outside their reach.

## 14. Prototype (0:45)
The prototype has seven Python modules. 

`generation` abstracts over code-generation providers — Bedrock and OpenRouter — and implements the CDK regeneration loop. 

`security_gate` implements scanner adapters, deduplication, risk scoring, and report assembly — this is Zone 2. 

`execution` is the subprocess backbone giving every external command the same stable result contract. 

`pipeline` orchestrates synth-gate-diff-deploy and keeps the approval/rejection audit trail together with credential handling. 

`monitoring` implements CloudTrail, CloudWatch, the ops-loop Lambda, and on-premises SSM registration. 

`risk_scoring` trains and evaluates the code-risk model. 

`ui` and `scripts` provide a Streamlit console and CLI entry points. 

Architecturally: the console and the CLI invoke exactly the same orchestration logic — a GUI operation follows the identical generate-assess-approve-deploy sequence as a CLI call. There is no path by which the graphical interface can bypass the gate.

## 15. Evaluation methodology — a pre-registered campaign (0:45)
Our evaluation is organized around three research questions, each with its own method and measures. 

**RQ1** — decision conformance and enforcement correctness — answered with 30 declared scenarios across 106 offline runs, including 10 that remove one scanner at a time. 

**RQ2** — cross-boundary enforcement equivalence — answered by running the same engine on an on-premises Linux node over a mesh VPN, expressing 11 catalogued weakness classes twice, before and after remediation. 

**RQ3** — unified risk-evaluation capability — answered with a held-out classifier evaluation plus controlled boundary cases. Two methodological points matter. 

First: everything was declared first — scenarios, expected decisions, and replicate counts were fixed in a version-controlled specification before any reported run executed; every statistic here comes from persisted records via one analysis program, so there was no freedom to choose afterward which runs to report.
Second: a security rejection is not a pipeline failure — a valid reject that blocks a bad deployment is *correct* execution, and we report denominators explicitly instead of confidence intervals, since these are small, pre-declared samples, not a random sample from a larger population.

## 16. RQ1 — Decision conformance and enforcement correctness, plus Finding 1 (0:50)
Across all 106 runs, six enforcement invariants each held at rate **1.00**: every run produced a persisted summary; every gate report stated a status for every scanner; every unapproved review halted (all 43 times); every approved review wrote an approval record (all 10 times); every reject both blocked deployment and wrote a rejection record (all 16 times). 

Read these carefully — the last four rows have very different denominators, so a rate of 1.00 over 10 runs is a much weaker statement than 1.00 over 106; this shows the mechanism works whenever exercised, not a general failure-rate estimate. 

Conformance is measured against a specification we ourselves authored, so it shows the implementation satisfies its own spec — not that the spec correctly grades real infrastructure. 

Still on this slide, we report a deliberately negative finding: ten scenarios removed exactly one scanner from an otherwise identical run, and every resulting decision matched the arithmetic prediction exactly — the gate degrades *predictably*, and that predictability is the problem. 

Removing Checkov from a CDK review scenario dropped the score from 54 to 9, flipping review to an auto-deployed pass; 

removing the secret scanner from an Ansible reject scenario dropped 155 to 75, flipping reject to review. 

An absent scanner and a scanner that found nothing contribute identically — zero — to the score. 

The scanner-status record makes this visible to an auditor afterward, but nothing in the decision function reacts to it. This is a structural weakness of any purely additive score, not an implementation defect, and we return to it in future work.

## 17. RQ2 — Cross-boundary equivalence: checkpoint attainment (0:45)
We ran 65 Ansible-branch executions: 59 offline, plus a 6-run live arm against a disposable, freshly imaged Ubuntu 22.04 VM. We measure attainment only over checkpoints actually attempted — a reject correctly never reaches a dry run, and scoring that as failure would penalize correct behaviour. 

Offline, syntax validation and the security gate each passed 59/59, and dry run passed all 31 times attempted. 

On the live target, all seven checkpoints — reachability, syntax, gate, dry run, apply, post-apply verification, idempotency — passed every time attempted. Nine assertions read state directly off the live host, with zero failures across every apply, and all three repeated applies correctly reported zero changes — true idempotency. 

In three runs where the gate correctly rejected a deliberately vulnerable play, execution stopped exactly at the gate checkpoint — no dry run, no apply — even against a live, reachable host.

## 18. Finding 2 — one decision function, unequal detection (0:45)
Decision *equality* across the boundary is the wrong property to demand — an iptables rule is not a security group. What matters is weaker but more important: a weakness class the gate can see on one side must not be invisible on the other. 

We derived 11 weakness classes from MITRE's CWE-1008, filtering its 223 members down to 38 candidates through three mechanical filters, then to the 11 expressible as a matched pair — the same weakness, once in CloudFormation, once in Ansible. 

Critically, we did not choose this list ourselves — it is external. We measured detection twice: at a frozen baseline commit, and again after a remediation pass adding nine new rule families. 

At baseline: 7/11 named on cloud, 5/11 on-premises, but only **3/11 named on both** — a gate treating the branches as interchangeable would be wrong about 8 of 11. 

After remediation: 10/11 cloud, 11/11 on-premises, **10/11 named on both**. 

What matters most is not the raw counts but that where a class is named on both sides, the identifiers match — the same identifier whether the evidence came from a security-group rule or an iptables task. One baseline miss makes the point sharply: the cloud report did contain the right finding — `CKV_AWS_33`, a wildcard IAM principal — but under a different identifier than expected, and so was indistinguishable from silence to any downstream consumer.

## 19. RQ3 — Unified risk-evaluation capability (0:50)
On a held-out set of **324 samples** (162 negative, 162 positive), the classifier reaches accuracy **0.9259**, precision 0.9480, recall 0.9012, F1 **0.9240**, and ROC-AUC **0.9233**. The confusion matrix is close to diagonal: 146 true negatives, 16 false positives, 8 false negatives, 154 true positives. The top three coefficients by magnitude are `bandit_low`, `bandit_conf_high`, and `total_bandit` — the model draws on both analysers, not just one. We also ran a controlled check of the decision function at exact boundary values: score 20 → pass, 21 → review, 80 → review, 81 → reject, and a finding duplicated across two tools counted only once. All five cases agreed exactly with the specification.

## 20. Limitations and threats to validity (0:45)
Seven limitations, stated directly. **1.** Self-authored fixtures: pre-registration removes selection freedom, not authorship — the same authors wrote the fixtures, and several samples are small (10 approved reviews, 16 rejections, 3 replicates per checkpoint). **2.** Narrow deployment-side evidence: apply, verification, and idempotency measured against one fresh VM, one OS image — nothing on host heterogeneity, concurrency, or partial failure. **3.** Restricted implementation scope: Python with Bandit/Semgrep; AWS CDK/CloudFormation and Ansible only — no claim of transfer to other languages, providers, or vulnerability classes. **4.** Dataset and model validity: 31 held-out samples from one split, undetectable categories excluded, negatives are reference-secure, not verified secure. **5.** Uncalibrated risk assumptions: weights, bands, thresholds are uncalibrated, and — as Finding 1 showed — missing evidence reads as low risk (fail-open). **6.** Unequal detection coverage: figures bound rule-to-CWE alignment on hand-authored fixtures, not field recall, even though the class list is external. **7.** Limited comparative measures: no manual baseline, no operator effort, lead time, change-failure rate, or remediation time measured.

## 21. Conclusion (0:45)
Hybrid cloud fragments provisioning, administration, delivery, and security across separate teams and tools; this work turns security into an explicit, auditable operational decision inside that lifecycle, rather than a separate, after-the-fact activity. One process, one engine, govern both sides of the hybrid — the same weights, deduplication, and thresholds apply to a CloudFormation template and an Ansible play alike. The additive score converts heterogeneous tool output into a single decision without losing the per-component explanation that lets a human act on it. Our pre-registered campaign shows the implemented gate decides and enforces exactly as specified: 106/106 conformance, six enforcement invariants each at rate 1.00. It also surfaces two genuine findings: the specification itself permits a release when evidence is missing, and a shared decision function does not, by itself, guarantee equal treatment when detection coverage genuinely differs across the boundary. We consider these findings just as much a result of this work as the conformance figures — internal correctness under pre-declared conditions, not proven operational effectiveness at scale.

## 22. Future work (0:30)
First priority: close the fail-open condition, by making the decision function consume the scanner-status record it already writes — an assurance penalty proportional to missing coverage, or a fail-closed policy below a coverage threshold; the existing degradation scenarios are ready-made test cases. Second: close the remaining coverage gap at its source — a smarter secret scanner for the cloud path, an equivalent learned signal for the private path, and independently authored fixtures. Beyond that: broaden deployment-side evidence to divergent prior state and concurrent targets; validate the model on a larger, project-aware, cross-validated corpus; calibrate the score against expert judgement and historical incidents; and extend platform coverage to more providers, languages, and orchestrators.

## 23. Thank you / Questions (0:15)
Thank you very much for your attention. My colleague and I are happy to take your questions.

---

## Backup slides (only if asked)

**B1 — Connectivity options.** Five options compared on mechanism and trade-offs: mesh overlay VPN, AWS Site-to-Site VPN, Direct Connect, Transit Gateway, and SSM hybrid activation over public endpoints. Key message: the choice is orthogonal to the contribution — it changes nothing about the gate, the scoring, or governance.

**B2 — Full model coefficients.** The complete 11-feature coefficient table. Because features are standardized, magnitudes describe relative influence within this fitted model, not causal importance; total-count features correlate with the severity counts, so the coefficients describe the model, not causation.

**B3 — Dataset construction.** SecurityEval positives; click/rich/typer negatives; line-count filters (20–700, narrowed to 20–300 to match SecurityEval scale); exclusion of vulnerability categories invisible to Bandit/Semgrep, keeping ~15% as hard negatives. An unfiltered corpus reached only ~0.73 accuracy with recall ~0.46; filtering makes the chosen features informative. Result: ~150 samples, near-balanced, 31-file held-out partition.
