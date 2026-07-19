# generated_cdk — CDK Deployment Target

## Purpose

`generated_cdk/` is the working CDK project that the pipeline synthesizes, gates, and
deploys. The `app.py` here is **rewritten in place** by the code-generation module
(`generation/run_cdk_regen.py`) on every generation run — the version checked into the repo is a
minimal reference example (a single encrypted, versioned S3 bucket).

> Treat `app.py` as generated output. Manual edits made in the UI's *Review & Edit* sub-tab
> are also written here before the gate re-runs.

## Files

| File | Role |
|---|---|
| `app.py` | The CDK app (generated/edited). Must contain exactly one `Stack` and call `app.synth()` |
| `cdk.json` | CDK config: `{"app": "../.venv/bin/python app.py"}` |
| `cdk.context.json` | CDK context cache (queried VPC/AMI/AZ values); currently `{}` |
| `requirements.txt` | `aws-cdk-lib>=2.0.0`, `constructs>=10.0.0` |
| `command_logs/` | Archived `cdk synth` output (`synth_<timestamp>.log`) from generation runs |

## Lifecycle

```mermaid
flowchart LR
    G[generation/run_cdk_regen.py] -->|writes| APP[app.py]
    APP -->|cdk synth| OUT[cdk.out/*.template.json]
    OUT -->|gate| GATE[security_gate.iac_security_gate]
    GATE -->|pass / review+approve| DEP[cdk deploy]
    DEP -->|attach| MON[monitoring.stack_monitor]
```

1. `generation/run_cdk_regen.py` writes generated code to `app.py`.
2. `pipeline/cdk_pipeline.py::clear_cdk_out()` purges stale templates, then runs `cdk synth`.
3. `security_gate/iac_security_gate.py` scores the synthesized templates in `cdk.out/`.
4. If the gate allows it, `cdk deploy` runs and `monitoring/stack_monitor.py` attaches monitoring.

## Generation Contract

Generated `app.py` must:

- declare **exactly one** `Stack` subclass (multi-stack output inflates the template count
  and the gate score);
- call `app.synth()` at module scope;
- contain no `input()` calls at import time or inside `Stack.__init__`;
- use safe, non-interactive defaults (`CfnParameter`, env vars, constructor args).

The generation prompt in `generation/run_cdk_regen.py` also enforces least-privilege IAM, default
encryption (S3/RDS/EBS), no public SSH/RDP, and `RemovalPolicy.RETAIN` for stateful resources.

## Setup

```bash
cd generated_cdk
pip install -r requirements.txt   # if not already installed in the project venv
cdk synth                          # manual synth (optional)
```

See [`../generation/README.md`](../generation/README.md) and [`../security_gate/README.md`](../security_gate/README.md).
