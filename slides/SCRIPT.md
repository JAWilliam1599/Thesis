# Speaking Script — 20-Minute Thesis Defence

**Title:** Research and Build a SysSecOps System Process for a Hybrid Cloud Environment
**Speakers:** Nguyễn Chính Thông (22125102) · Huỳnh Tuấn Minh (22125055)
**Total speaking budget:** ~19:45, then Q&A

## How to use this script

- Each section corresponds to one slide in [slides/presentation.md](slides/presentation.md), in order.
- **Say:** is the spoken text, written to be read aloud at roughly 140 words per minute.
- **Do not read the tables aloud.** Where a slide has a table, the script says only what the table cannot say for itself.
- *(Cue)* lines are stage directions — pointing, pausing, advancing — not spoken.
- Suggested split: **Speaker A** takes slides 1–17 (problem, process, risk engine); **Speaker B** takes slides 18–28 (prototype, evaluation, closing). The handover line is written into slide 18.

---

## Part 0 — Opening (1:00)

### Slide 1 — Title (0:30)

**Say:**
> Good morning. Thank you, Chair, and thank you to the committee for your time today.
>
> Our thesis is titled *Research and Build a SysSecOps System Process for a Hybrid Cloud Environment*. I am Nguyễn Chính Thông, and this is Huỳnh Tuấn Minh. The work was supervised by PhD. Tran Trung Dung and MSc. Chung Thuy Linh, in the Advanced Program in Computer Science at the University of Science, VNU-HCM.
>
> We will present for about twenty minutes and then take your questions.

*(Cue: advance immediately — do not linger on the title.)*

---

### Slide 2 — Roadmap (0:30)

**Say:**
> Here is where we are going.
>
> First, the problem: why hybrid cloud operations break security. Second, the process we propose — a SysSecOps workflow with a decision gate placed *before* deployment. Third, the risk engine that turns many separate tools into one explainable decision. Fourth, what we actually built. Fifth, the results, organised as three research questions and three separate bodies of evidence. And finally, limitations and future work.
>
> One thing to note up front: the evaluation maps one-to-one onto the research questions, so every claim we make has a specific place where its evidence lives.

---

## Part 1 — Problem and positioning (3:30)

### Slide 3 — Motivation (0:45)

**Say:**
> Organisations adopt hybrid cloud because they want two things at once: the elasticity of public cloud, and the control of infrastructure they own. That combination is now the default operating model, not an edge case.
>
> But it comes at a price. A hybrid estate has two provisioning mechanisms, two security models, and two identity domains. The dominant failure mode stops being a novel exploit and becomes configuration drift and misconfiguration — small inconsistencies that accumulate across two environments that were never designed to be governed together.
>
> And in practice, provisioning, administration, delivery and security assessment are run by separate teams with separate tools. So the flexibility is real — and so is the coordination cost.

---

### Slide 4 — Four operational challenges (0:45)

**Say:**
> We group that cost into four challenges.
>
> *(Cue: point, do not read the table.)*
>
> **C1**, managing heterogeneous infrastructure — the same policy has to hold across on-premises, private and public resources that do not share a description language.
>
> **C2**, integrating continuous security into the lifecycle. Security is typically applied late, which makes remediation both expensive and delayed.
>
> **C3**, assessing findings and prioritising risk. Many tools, many output formats, and no consistent way to say which finding matters more.
>
> **C4**, establishing an integrated process at all. SysAdmin, development and security operate as silos, so decisions are made without traceability.

---

### Slide 5 — Research gaps (0:45)

**Say:**
> These challenges correspond to four gaps in the literature.
>
> **G1** — there are limited operational frameworks for hybrid cloud security. The NIST reference architecture defines *what* the components are; it does not define *how* to operate them together.
>
> **G2** — continuous security largely stops at CI/CD. It is rarely extended across infrastructure operations in heterogeneous environments.
>
> **G3** — there is little orchestration of heterogeneous security tools. Research categorises tools; far less work consolidates their outputs into a single decision.
>
> **G4** — there is limited empirical validation. Conceptual architectures dominate; executable and evaluated processes are scarce.
>
> Each of these is anchored to published work, so the framing is not our opinion.

---

### Slide 6 — Gaps → Objectives → RQs → Contributions (0:45)

**Say:**
> This table is the logical spine of the thesis, so let me walk one row end to end.
>
> Gaps one and four — no operational framework, and weak empirical validation. The objective that follows is to *design* a SysSecOps process that integrates infrastructure management, assessment, enforcement and deployment. The research question that tests it is **RQ1**: does the system reach the decision it should, and does that decision actually constrain what happens next. And the contribution is the process itself.
>
> Every other row follows the same pattern. Gap two gives us **RQ2**, cross-boundary enforcement. Gap three gives us **RQ3**, unified risk evaluation. Nothing in the evaluation exists without a gap behind it.

---

### Slide 7 — Contributions (0:30)

**Say:**
> Three contributions, one sentence each.
>
> **C1** — a SysSecOps operational process for hybrid cloud, which puts system administration, continuous security and software delivery on one workflow with a *common decision path* for both public and private targets.
>
> **C2** — a unified security assessment mechanism, which normalises and deduplicates findings from heterogeneous tools and combines them with cost, live compliance and a learned code-risk signal into one explainable score.
>
> **C3** — a working prototype and a reproducible evaluation framework, with separate acceptance criteria per research question.

---

## Part 2 — Proposed process and architecture (3:55)

### Slide 8 — Core idea: gate before deploy (0:45)

**Say:**
> If you remember one design decision from this talk, make it this one.
>
> The security decision is taken on the **synthesized artefact** — the CloudFormation template, or the resolved Ansible play. Not on the prompt, and not on the high-level source code. That is deliberate: the synthesized artefact is the last representation before any resource exists, and it is the first point at which every resource and every property is fully known. Deciding earlier means deciding on incomplete information; deciding later means deciding after the risk has already been taken.
>
> Second: one engine for the whole hybrid. Identical weights, identical deduplication rules, identical thresholds on both sides of the trust boundary.
>
> Those two choices, plus graceful degradation, auditability, feedback-driven remediation and observability, are the design goals the architecture has to satisfy.

---

### Slide 9 — Three-zone reference architecture (0:50)

**Say:**
> The architecture has three zones.
>
> **Zone 1** is AI-assisted generation and local validation — code is produced from a prompt and checked locally with `cdk synth`, `cdk diff`, or a syntax check.
>
> **Zone 2** is the security gate. Multi-scanner analysis, cross-source deduplication, risk scoring, and the deploy decision. This zone is the contribution.
>
> **Zone 3** is the hybrid infrastructure and operations monitoring — provisioning on AWS and on-premises, telemetry, and the drift and remediation loop.
>
> *(Cue: point at the dashed feedback edge.)*
>
> Note this edge. When generated code is rejected, the findings are injected back into the next prompt and the code is regenerated. Remediation is part of the loop, not a manual afterthought.
>
> The zones are loosely coupled: Zone 1 knows nothing about the scoring rules, and Zone 3 knows nothing about how the decision was reached.

---

### Slide 10 — End-to-end artefact flow (0:50)

**Say:**
> This is the same system viewed as a flow of artefacts. A prompt or an existing project becomes generated code; generated code becomes a synthesized template; the template becomes a set of normalized findings; the findings become a score and a decision; the decision becomes a gate report; and only then does anything deploy and emit telemetry. If the decision is *reject*, we go back and regenerate.
>
> Each stage turns its input into a strictly more concrete representation.
>
> What holds it together is three stable data contracts. The **gate report** carries the score, the decision, the per-component breakdown, the deduplicated findings, and a status for every scanner. The **execution result** means every external command returns the same shape — a return code and its output. And the **gate-decision event** is published to SSM Parameter Store and EventBridge.
>
> Because these contracts are stable, the generator, the scanner set and the monitoring stack can each evolve independently.

---

### Slide 11 — Hybrid deployment topology (0:45)

**Say:**
> Concretely, the public side is AWS: CDK synthesises CloudFormation for VPC, EC2, S3 and RDS, with SSM, EventBridge, CloudWatch, CloudTrail, a Lambda ops-loop and SNS for the operational layer.
>
> The private side is on-premises Linux nodes configured by Ansible and registered through SSM hybrid activation, where they appear as `mi-` managed instances.
>
> There is **no public inbound administrative access**. The control plane traverses the encrypted link.
>
> And that link is a pluggable concern. We used a mesh overlay VPN, but a site-to-site IPsec VPN, Direct Connect, Transit Gateway, or SSM over public endpoints are all valid substitutes. The point is that the choice changes nothing in the gate, the scoring, or the governance behaviour — connectivity is orthogonal to the contribution.

---

### Slide 12 — Governance and enforcement (0:45)

**Say:**
> The decision has three outcomes. **Pass** deploys automatically. **Review** blocks deployment until an explicit approval record exists. **Reject** does not deploy at all — the change is regenerated or returned to its author.
>
> Every decision is persisted as an immutable record carrying the acting identity, so the audit trail is append-only.
>
> There is also a graceful degradation contract. If a scanner binary is missing, or a credential is absent, that source degrades to a well-defined `skipped` status. The gate still produces a decision, and the report records *which* sources actually ran — so a weakly-evidenced decision is visible rather than silent. We will come back to that, because it is where one of our two negative findings lives.
>
> Finally, credentials are never passed as command-line arguments; they are resolved through provider chains and injected via the environment.

---

## Part 3 — Unified security assessment and risk scoring (3:40)

### Slide 13 — Why severity-only scoring is not enough (0:40)

**Say:**
> Why build a score at all, instead of just using severity labels?
>
> Three reasons. First, severity ignores blast radius and cost. The same open security-group rule on an internet-facing load balancer and on an isolated subnet carry the same severity label and completely different exposure.
>
> Second, every single tool has blind spots. A policy scanner, a template linter, a cost estimator, a live-compliance service and a code model each see a different slice of the same change. Relying on any one of them produces systematic false negatives.
>
> Third, AI generation shifts the risk profile. The dominant failure mode of generated infrastructure code is not a novel exploit — it is a *plausible misconfiguration*. So a learned probability that the code is insecure is as useful as any single hand-written rule.

---

### Slide 14 — Multi-scanner assessment and normalisation (0:45)

**Say:**
> So the gate runs seven sources across four risk dimensions.
>
> *(Cue: point down the column, do not read every row.)*
>
> For **misconfiguration**: `cfn-lint` for CloudFormation validity, Checkov for policy-as-code, `ansible-lint` for the private side, and a regex secret scanner for hard-coded credentials. For **cost**: Infracost, giving an estimated monthly delta. For **compliance**: AWS Config, giving a count of non-compliant live rules. And for **code risk**: Bandit and Semgrep features fed into a logistic regression.
>
> Their outputs are normalised into one finding format and then deduplicated on the key `(resource_id, template, category)`. Colliding findings merge, keeping the highest severity and unioning the source labels.
>
> Deduplication is not cosmetic. Without it, an issue reported by three tools contributes three times, and that alone can push an otherwise acceptable change across a threshold.

---

### Slide 15 — The additive risk score (0:50)

**Say:**
> The score is a sum of four components.
>
> The **severity** term sums a weight over the deduplicated findings — critical is twenty points, high is ten, medium five, low one. The **cost** term is a banded function of the estimated delta. The **compliance** term is five points per non-compliant live rule. And the **machine-learning** term is the model's probability, scaled to twenty points.
>
> Cost is banded rather than continuous, deliberately — that keeps the score stable against estimation noise rather than jittering with every price change.
>
> The thresholds: twenty or below passes, twenty-one to eighty goes to review, above eighty is rejected.
>
> I want to be explicit about one thing. This additive form is a deliberate *simplification* of a general multi-factor risk model. We chose it for transparency and reproducibility — because it is additive, every single point is attributable to a component, and that is what makes the report explainable.

---

### Slide 16 — Machine-learning code-risk component (0:45)

**Say:**
> The learned component in one minute.
>
> Positives come from **SecurityEval**, which is CWE-labelled insecure Python. Negatives are sampled from maintained projects — `click`, `rich` and `typer`. Features are an eleven-dimensional count vector: Bandit severity and confidence counts, Semgrep severity counts, and two totals. The model is a logistic regression on an eighty-twenty stratified split with standardised features and balanced class weights.
>
> Training and inference use the same analysers, the same grouping, and the same persisted scaler — so there is no train-serve skew.
>
> At inference, the probability is the **maximum** over files, not the mean. The worst file wins, so one risky file cannot be diluted by many benign ones.
>
> And I should volunteer the scope statement: this model estimates **detector-visible** insecurity. It does not detect semantic flaws that Bandit and Semgrep cannot see. Roughly half of the original SecurityEval samples contain exactly such logic errors; retaining them capped recall near 0.46, which is why they were excluded and why the claim is scoped this way.

---

### Slide 17 — Worked example (0:40)

**Say:**
> A concrete case. A change produces one high and two medium deduplicated findings, lands in the medium cost band, has one non-compliant live rule, and the model returns a probability of zero.
>
> Severity gives ten plus five plus five, so twenty. Cost gives ten. Compliance gives five. The model gives nothing. Total: thirty-five. That is above twenty and below eighty, so the decision is **review**, and it is routed to a human approver whose decision enters the audit trail.
>
> But look at what the approver actually receives. The breakdown — severity twenty, cost ten, compliance five, model zero — tells them the open administrative port and the cost increase are what dominate. That directs remediation precisely, instead of handing over an opaque number. This is our answer to "why not just use a black-box model".

---

## Part 4 — Implementation and evaluation (6:10)

### Slide 18 — Prototype (0:45)

**Say (handover):**
> Thank you. I will take over for the implementation and the results.
>
> The prototype is a Python system of seven modules. `generation` handles provider-abstracted code generation over Bedrock or OpenRouter, plus the regeneration loop. `security_gate` holds the scanner adapters, deduplication, scoring and report assembly. `execution` is the subprocess backbone with the stable result contract. `pipeline` orchestrates synth, gate, diff and deploy, and owns the approval audit trail and credential handling. `monitoring` covers CloudTrail, CloudWatch, the ops-loop Lambda and on-premises SSM registration. `risk_scoring` trains and evaluates the code-risk model. And `ui` and `scripts` are the Streamlit operator console and the CLI.
>
> One property matters more than the module list: the console and the CLI invoke **the same orchestration logic**. A GUI operation follows the identical generate, assess, approve, deploy sequence — the interface cannot bypass the gate.

---

### Slide 19 — Evaluation methodology (0:45)

**Say:**
> The evaluation is a pre-registered campaign, and the word *pre-registered* is doing real work.
>
> The scenarios, their expected decisions and their replicate counts were fixed in a version-controlled specification **before any reported run executed**, and every statistic on the following slides is computed from the persisted records by a single analysis program. So there was no freedom, after the fact, to choose which runs to count.
>
> RQ1 is answered by 30 declared scenarios over 106 offline runs, ten of which deliberately remove one scanner. RQ2 runs the same engine against an on-premises Linux node, and adds a separate 24-scenario, 72-run coverage arm that is executed twice. RQ3 is a held-out classifier evaluation plus controlled boundary cases.
>
> Thirty calibrated fixtures — six band fixtures and twelve matched pairs, eleven weakness classes plus one compliant control — with live pricing and live account state disabled; in the pilot those alone moved a *reject* fixture from 114 to 119.
>
> And one convention: a security rejection is **not** a pipeline failure. A valid *reject* that blocks a deployment is *correct* execution. We report denominators rather than confidence intervals throughout.

---

### Slide 20 — RQ1: conformance and enforcement (0:50)

**Say:**
> RQ1. Across 106 runs over 30 scenarios, decision conformance was **one hundred percent** — and it was 1.0 for each scenario individually, so the aggregate is not hiding a scenario that failed consistently while others compensated.
>
> The confusion matrix is **exactly diagonal**. That matters more than the percentage, because a gate can score high overall while being systematically permissive, and a single percentage would hide that. Here there is neither a permissive nor an over-blocking tendency. Replicates were bit-identical: all five `cdk-reject-block` runs scored exactly 114; all five `ans-reject-block` runs scored exactly 155.
>
> Six enforcement invariants held at rate 1.00 — every run persisted a summary, every run reported a status for every scanner, unapproved reviews halted, approvals wrote records, and rejections both blocked and recorded.
>
> Two honest qualifications. First, the **denominators are not comparable**: 1.00 over ten approved-review runs is a far weaker statement than 1.00 over 106. Read the last four rows as "the mechanism works when exercised", not as a failure-rate estimate. Second, conformance is measured against a specification this same work authored — it shows the implementation satisfies its own spec, not that the spec grades real infrastructure correctly.
>
> On cost: the gate takes a median of 102.5 seconds on the cloud branch, about seventy percent of run wall-clock, against 7 seconds on-premises. Under two minutes on the slower branch — acceptable for a pre-deployment check.

---

### Slide 21 — Finding 1: the score fails open (0:45)

**Say:**
> Now the first of two negative findings, which we are foregrounding deliberately rather than burying.
>
> Ten scenarios removed exactly one scanner from an otherwise identical run. Every resulting decision matched the arithmetic prediction, so the gate degrades *predictably*. That is precisely the problem.
>
> *(Cue: point at the Checkov review row.)*
>
> Remove Checkov from a review-band CDK change and the score drops from 54 to 9 — the decision becomes **pass**. Remove the secret scanner from the Ansible reject fixture and it loses 80 of its 155 points.
>
> The gate conformed to its specification on every one of these rows. But the specification permits a change to be released because the evidence that would have held it was never collected. **An absent scanner and a scanner that found nothing contribute identically.**
>
> The scanner-status record makes this visible to an auditor afterwards, but nothing in the decision function acts on it. This is a design deficiency inherent to any purely additive score — not an implementation defect. Chapter 6 proposes an assurance penalty as the remedy, and these degradation scenarios are already the test cases for it.

---

### Slide 22 — RQ2: checkpoint attainment (0:45)

**Say:**
> RQ2 asks whether the same enforcement holds across the trust boundary.
>
> Sixty-five Ansible-branch runs: 59 offline, plus a six-run live arm against a disposable Ubuntu 22.04 virtual machine. Attainment counts only *attempted* checkpoints — a reject never reaches a dry run, and scoring that as a failure would penalise correct behaviour.
>
> No attempted checkpoint failed in either arm. Three results from the live arm carry more weight than the rates, because the offline campaign structurally could not produce them.
>
> First, apply is not just a zero exit code. **Nine assertions** read state back off the host — directory modes, file modes, the service account's shell, the loopback binding — and they assert against literal expected values, not against the fixture's own variables. Asserting against the same variables that produced the state would accept a wrong value as correct. Zero assertion failures.
>
> Second, all three repeat applies recorded `changed=0`, so convergence is stable.
>
> Third, all three `ans-reject-deploy-blocked` runs stopped at `ansible.gate`. No dry run, no apply — against a live, reachable, credential-verified host.
>
> The concession: those last four rows rest on three runs each, against one host from one fresh image.

---

### Slide 23 — Finding 2: unequal detection (0:45)

**Say:**
> The second negative finding.
>
> It is tempting to demand *decision equality* across the boundary — same weakness, same band. That is the wrong property. An `iptables` rule is not a security group; they differ in blast radius and in how many defects a scanner can legitimately raise. Worse, we could satisfy equality trivially by tuning weights until the fixtures agreed, which would measure the tuning, not the system.
>
> The property that matters is weaker: a weakness class the gate can see on one side must not be **invisible** on the other.
>
> Testing that needs a set of weakness classes, and choosing that set is where such an evaluation is most easily compromised — an author who picks the classes can pick the ones the gate already covers. So the list came from MITRE's CWE-1008 view: 223 members, three mechanical filters, 38 candidates, and the eleven that can be expressed as a matched pair on both sides.
>
> We measured twice. At a **frozen gate commit**, the gate named seven of eleven classes in the cloud and five on-premises — but only **three on both**. Four were visible only in the cloud, two only on-premises, two on neither. A gate that treated the branches as interchangeable would have been wrong about **eight of eleven**.
>
> Where a class *was* named on both sides, the identifiers matched. An unrestricted firewall rule is `sg_ssh_open` whether it came from a security group or an iptables task. That shared vocabulary is the substantive result, not the counts.
>
> And one miss shows exactly why it matters. On the cloud incorrect-permissions fixture the report **did** contain a Checkov finding — "KMS key policy contains a wildcard principal". The scanner saw it. But the finding carried no category naming the class, so to the deduplicator, the risk score, the audit record and the operator it was indistinguishable from silence. We left the matcher frozen and fixed the vocabulary at the producer instead.
>
> Writing nine rule families closed nine of the ten gaps: ten of eleven in the cloud, eleven of eleven on-premises. Two caveats. That is **not a recall estimate** — it answers "were these gaps closable?", not "how much does the gate see?" And one gap was left open deliberately: a credential embedded in a CDK application sits in general-purpose Python, where no regex separates an embedded secret from the idioms that legitimately handle one. Raising the number there would have made the tool worse.

---

### Slide 24 — RQ3: unified risk-evaluation capability (0:50)

**Say:**
> RQ3. On a held-out partition of 31 files — 16 negative, 15 positive — the classifier reached an accuracy of 0.871 and a ROC-AUC of 0.879, with precision, recall and F1 all at 0.867.
>
> The confusion matrix has four errors: two false positives and two false negatives. The two false negatives are the operationally interesting ones — labelled-insecure files that receive a lower learned contribution than they should, which is exactly the direction of error that matters for a security gate.
>
> The top coefficients are worth a word. `total_semgrep`, `bandit_conf_medium` and `semgrep_high` lead, which tells us the model draws on **both** analysers rather than reducing to one of them. Features were standardised before fitting, so the magnitudes are comparable within this model — but the total-count features are mathematically related to the severity counts, so these describe the model, not causation.
>
> Separately, we ran controlled gate-decision checks on the boundaries: a score of 20 passes, 21 goes to review, 80 stays in review, 81 rejects, and a duplicate finding raised by two tools is counted once. All five agreed with the specification.

---

### Slide 25 — Limitations and threats to validity (0:45)

**Say:**
> Seven limitations, stated plainly.
>
> One — the fixtures were authored by the same work that built the gate. Pre-registration removes selection freedom; it does not remove that dependency. And the scale is modest: ten approved-review runs, sixteen rejections, three replicates per deployment checkpoint.
>
> Two — deployment evidence comes from one fresh VM on one OS image. We say nothing about host heterogeneity, concurrency or partial failure.
>
> Three — scope. Python with Bandit and Semgrep; AWS CDK and Ansible. No claim of transfer to other languages, providers or vulnerability classes.
>
> Four — the dataset: 31 held-out samples from one split, with undetectable categories excluded, and negatives that are *reference secure*, not verified secure.
>
> Five and six are the two findings you have already seen — the fail-open score, and unequal detection coverage. On six, note the residual limit: the class list is external, but the fixtures are ours, so the figures bound rule-to-CWE alignment rather than recall on real infrastructure.
>
> Seven — no manual baseline, and no measurement of operator effort, lead time, change-failure rate or remediation time.

---

## Part 5 — Closing (1:30)

### Slide 26 — Conclusion (0:45)

**Say:**
> To conclude.
>
> Hybrid cloud fragments provisioning, administration, delivery and security across teams and tools. This work makes security an **explicit, auditable operational decision** inside that lifecycle, rather than a review that happens somewhere alongside it.
>
> One process, one engine, both sides: the same weights, the same deduplication and the same thresholds govern a CloudFormation template and an Ansible play. The additive score converts heterogeneous tool output into a single decision without losing the per-component explanation that makes it actionable.
>
> The pre-registered campaign shows the implemented gate decides and enforces as specified — 106 out of 106 conformance, six enforcement invariants at rate 1.00.
>
> It also shows that the specification itself permits a release when evidence is missing, and that a shared decision function does not, by itself, produce equal treatment when detection coverage differs.
>
> We regard those two findings as **as much a result of this work as the conformance figures**. What we have demonstrated is internal correctness under pre-declared conditions — not operational effectiveness at scale.

---

### Slide 27 — Future work (0:30)

**Say:**
> The agenda follows directly from those findings, and the ordering is the point.
>
> First, close the fail-open condition: make the decision function consume the scanner-status record it already writes — an assurance penalty proportional to missing coverage, or a fail-closed policy that forces review below a coverage threshold. The existing degradation scenarios are ready-made test cases.
>
> Second, close the last coverage gap at source: give the cloud path a secret scan that can separate an embedded credential from the idioms that legitimately handle one — entropy and provider formats, not keywords — give the private path an equivalent learned signal or an explicit *not applicable*, and replace our hand-authored fixtures with independently written ones.
>
> Items three through six broaden the deployment evidence, validate the model on a larger multi-project corpus, calibrate the score against expert judgement and historical incidents, and extend platform coverage.
>
> Items one and two are repairs to a system that already works. The rest are extensions.

---

### Slide 28 — Thank you (0:15)

**Say:**
> That concludes our presentation. Thank you for your attention — we would be glad to take your questions.

*(Cue: leave the slide up. Do not advance into the backup slides unless a question calls for one.)*

---

## Backup slides — when to use them

| Trigger question | Go to | One-line answer |
|---|---|---|
| "Why that VPN? Would it work over Direct Connect?" | **B1 — Connectivity options** | Connectivity is pluggable; the gate, scoring and governance are unchanged by the choice. |
| "What is the model actually keying on?" | **B2 — Full coefficients** | Both analysers contribute; total-count features correlate with severity counts, so read the coefficients as describing the model, not causation. |
| "How was the dataset built? Isn't SecurityEval biased?" | **B3 — Dataset construction** | ~150 near-balanced samples; analyser-invisible categories excluded, which is why the claim is scoped to detector-visible insecurity. The unfiltered corpus gave ~0.73 accuracy at ~0.46 recall. |
| "How does this differ from NIST RA / CloudCAMP / existing practice?" | **B4 — Comparison** | NIST defines components, not sequence; CloudCAMP abstracts platforms; we contribute gating, traceability and an explainable score. No quantitative manual baseline yet. |

## Anticipated questions without a backup slide

**"Aren't the thresholds arbitrary?"**
> Yes, in the sense that they are uncalibrated — that is limitation five. They were chosen so that the severity weights produce sensible bands on the fixtures, and we state explicitly that calibration against expert judgement and historical incidents is required future work. What the thresholds *do* give us is reproducibility: because the form is additive and the weights are fixed, any two people scoring the same artefact get the same number.

**"Why not use CVSS?"**
> CVSS scores a vulnerability in isolation. Our score has to combine four incommensurable dimensions — misconfiguration, cost, live compliance and learned code risk — into one deployment decision. Slide 13 is the argument: severity alone ignores blast radius and cost.

**"Isn't 106 runs a small evaluation?"**
> It is. We report denominators rather than confidence intervals for exactly that reason, and we distinguish invariants exercised on 106 runs from those exercised on ten. The campaign establishes that the mechanism works when exercised; it does not estimate a failure rate.

**"Could the LLM just be told to write secure code instead?"**
> It can be asked, and the regeneration loop does exactly that by injecting findings into the next prompt. But asking is not a control. The gate is what makes the outcome verifiable, and it applies equally to human-authored code, which is why the decision is taken on the synthesized artefact rather than on the prompt.

**"Does the UI let an operator bypass the gate?"**
> No. The console and the CLI call the same orchestration logic — slide 18. An operator can *approve* a review, and that approval is recorded with their identity, but there is no path that reaches deploy without a decision.
