# Evaluation fixtures

Controlled inputs for the RQ1/RQ2 evaluation campaign. Each fixture is a
self-contained project that the hybrid pipeline can be pointed at, carrying a
**declared expected decision** so that observed gate behaviour can be scored for
conformance rather than merely described.

Nothing here is part of the deployable system; these directories exist only to
exercise it.

## Layout

```
eval-fixtures/
  ansible/{pass,review,reject}/   on-prem fixtures, one per decision band
  cdk/{pass,review,reject}/       public-cloud fixtures, one per decision band
  parity/<pair-id>/{cdk,ansible}/ paired fixtures encoding the same weakness
                                  on both sides of the hybrid boundary
  ansible/verify.yml              post-apply assertions for the live-target arm
  ansible/deploy-inventory.ini    generated; points at the Multipass VM
```

## Declared expectations

Expectations live in [`expectations.yaml`](expectations.yaml) and are the single
source of truth consumed by the campaign harness. A fixture whose observed
decision differs from its declared decision is a **conformance failure** and is
reported as such — it is never silently re-labelled.

## Calibration

Absolute scores depend on scanner versions, so the fixtures are calibrated to
sit near the *middle* of their band rather than on a boundary:

| Band   | Score range | Fixture target |
| ------ | ----------- | -------------- |
| pass   | 0 – 20      | 0              |
| review | 21 – 80     | ~35 – 60       |
| reject | > 80        | > 100          |

Re-run `python -m evaluation.calibrate` after a scanner upgrade to confirm every
fixture still lands in its declared band.

## Parity fixtures (`parity/`)

The band fixtures above answer "does the gate grade severity correctly?". The
parity fixtures answer a different question, and the one RQ2 actually turns on:
**does the same weakness receive the same treatment on both sides of the hybrid
boundary?**

Each pair encodes exactly one weakness class twice — once as cloud
infrastructure-as-code (`<pair>/cdk/`) and once as on-premises configuration
(`<pair>/ansible/`):

| Pair                    | Cloud expression                        | On-premises expression                          |
| ----------------------- | --------------------------------------- | ----------------------------------------------- |
| `open-ingress`          | security group allowing SSH from `0.0.0.0/0` | `iptables` rule accepting SSH from `0.0.0.0/0` |
| `plaintext-secret`      | credential in a Lambda environment variable | credential in `group_vars`                  |
| `overprivileged-access` | IAM policy with `Action: "*"`, `Resource: "*"` | `NOPASSWD: ALL` sudoers entry, mode `0777` dir |
| `unencrypted-storage`   | unencrypted S3 bucket and EBS volume    | ext4 filesystem mounted with no encryption layer |

Everything else in each fixture is deliberately unremarkable, so a difference in
verdict is attributable to the boundary rather than to incidental differences in
the surrounding code.

Every fixture uses `ansible.builtin` modules only. External collections are
deliberately avoided so the campaign runs from a clean checkout without a
`ansible-galaxy install` step, which would otherwise make results depend on
whatever collections happen to be present.

### These fixtures are not tuned to agree

The `expect_decision` recorded for a parity fixture is **descriptive** — it is
the band measured during calibration, not a target the fixture was adjusted to
hit. Tuning them until both sides agreed would manufacture the very result RQ2
is supposed to test. Disagreements are reported as parity gaps.

### Baseline arm: before the semantic rules

The first parity measurement was taken when the on-premises path had no scanner
with semantic security coverage — `ansible-lint` enforces style, Checkov's
Ansible framework returned no findings on any of these fixtures, and the regex
secret scan only matches credential-shaped strings:

| Pair                    | On-prem score | Band | What the score came from                    |
| ----------------------- | ------------- | ---- | ------------------------------------------- |
| `open-ingress`          | 0             | pass | **nothing — the `0.0.0.0/0` source is invisible** |
| `plaintext-secret`      | 20            | pass | regex secret scan (detected, but at the pass ceiling) |
| `overprivileged-access` | 0             | pass | **nothing — neither weakness is detected**  |
| `unencrypted-storage`   | 10            | pass | a style rule, **not** the missing encryption |

All four landed in `pass` while all four cloud counterparts reached `review`:
zero agreement across the four pairs. This arm is reproducible at any time by
passing `--no-ansible-rules`, and is registered in `scenarios.yaml` as the
`*-baseline` scenarios.

### Rules arm: `ansible-rules`

That gap motivated `security_gate/scanners/ansible_rules_adapter.py`, which
applies the same *classes* of check the CDK path already had, under the same
dedup categories and severities:

| Category                    | Severity | What it matches                                       |
| --------------------------- | -------- | ----------------------------------------------------- |
| `sg_ssh_open`               | critical | firewall rule exposing 22/23/3389/5985/5986 to any source |
| `sg_public_ingress`         | high     | any other port exposed to any source                  |
| `iam_wildcard`              | critical | `NOPASSWD: ALL` in a sudoers entry, wherever written  |
| `file_world_writable`       | high     | a mode granting write beyond the owner                |
| `storage_encryption`        | high     | a filesystem created with no LUKS/dm-crypt layer      |
| `storage_mount_encryption`  | medium   | a persistent mount added without encryption           |

Re-measured with those rules enabled:

| Pair                    | On-prem score | Band   | Cloud band | Agree |
| ----------------------- | ------------- | ------ | ---------- | ----- |
| `open-ingress`          | 20            | pass   | review     | no    |
| `plaintext-secret`      | 20            | pass   | review     | no    |
| `overprivileged-access` | 30            | review | review     | yes   |
| `unencrypted-storage`   | 25            | review | review     | yes   |

Two pairs now agree. The two that still disagree both sit at exactly 20, the
`pass` ceiling, and their cloud counterparts clear it only because of the
`ml_risk` component — 4 points for `open-ingress` and 19 for `plaintext-secret`
— which is computed from Python source and does not apply to playbooks. The
residual gap is therefore no longer a *detection* gap but a *scoring* asymmetry
in the risk engine itself.

> These `ml_risk` figures were measured under the earlier linear mapping
> (`round(p * 20)`). The component is now convex (`round(p ** 2.5 * 85)`), which
> widens the same asymmetry rather than closing it; the campaign must be re-run
> to re-measure.

The rules were written to cover the weakness classes the pairs express, and
their severities mirror the existing CDK heuristics. They were not adjusted
afterwards to move any pair across a threshold; `open-ingress` and
`plaintext-secret` were left sitting on the boundary rather than nudged over it.

## Live target (`ansible/verify.yml`, `ansible/deploy-inventory.ini`)

Most of the campaign runs offline, which leaves the RQ2 checkpoints that only a
real host can evidence — reachability, apply, post-apply verification and
repeated-run idempotency — unattempted. The `ans-pass-deploy` and
`ans-reject-deploy-blocked` scenarios close them against a throwaway Multipass
VM. They are gated behind `--allow target-host` and never run by default.

```bash
scripts/setup_multipass_target.sh          # launch the VM, write the inventory
.venv/bin/python -m evaluation.run_campaign \
    --scenario ans-pass-deploy --scenario ans-reject-deploy-blocked \
    --allow target-host --campaign-id rq2_deploy
scripts/setup_multipass_target.sh --destroy
```

Two details are load-bearing:

- **The inventory is a file with an `[appservers]` group, not `--target-host`.**
  `--target-host H` builds the inline inventory `H,`, which puts the host in
  `all`/`ungrouped`. The fixture playbooks declare `hosts: appservers`, so
  nothing would match — and `ansible-playbook` exits 0 with an empty PLAY RECAP
  when nothing matches, so a deployment that applied nothing would be recorded
  as a successful apply.
- **`verify.yml` sits above the fixtures, not inside one.** The gate scans every
  YAML file under the project it is pointed at, so adding it to `ansible/pass/`
  would change that fixture's calibrated score of 0. Its expected values are
  hard-coded rather than read from `group_vars`: asserting against the same
  variables that produced the state would accept a wrong variable value as
  correct.

`deploy-inventory.ini` and the generated key pair under `.eval-target/` are
gitignored; [`deploy-inventory.ini.example`](ansible/deploy-inventory.ini.example)
records the expected shape.

## Safety

The `review`, `reject`, and `parity` fixtures contain **deliberately insecure
configuration and fake credentials**. The credential-shaped strings are
syntactically valid but non-functional placeholders. Do not copy these patterns
into real projects, and do not deploy these fixtures to any host you care about.
