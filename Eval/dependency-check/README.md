# Dependency-Check Integration Notes

## Purpose in this repository

This folder contains resources for OWASP Dependency-Check usage as part of security assessment in the broader SysSecOps model.

In the current codebase, Dependency-Check is not yet fully wired into the CDK gate decision pipeline. It can be used as an optional supplemental scanner for dependency risk analysis.

## Suggested Usage

Run Dependency-Check against Python project dependencies and export JSON:

```bash
dependency-check --project thesis --scan . --format JSON --out logs/dependency-check
```

## Intended Future Integration

Planned path for CDK-only pipeline:
- normalize Dependency-Check findings into the same finding schema used by `Eval/iac_security_gate.py`
- map severities into existing score weights
- include component score in final pass/review/reject decision

## References

- Official docs: https://dependency-check.github.io/DependencyCheck/dependency-check-cli/index.html
- OWASP A06: https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/