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
- Normalize Dependency-Check findings into the gate finding schema used by `security_gate/iac_security_gate.py`:
  ```python
  {"severity": "high", "source": "dependency_check", "message": "...",
   "resource_id": "<package>", "template": "requirements.txt", "category": "vulnerable_dependency"}
  ```
- The `category` field is required for cross-source deduplication (Phase 4)
- Map CVSS severities to gate severities: CVSS ≥ 9.0 → `critical`, ≥ 7.0 → `high`, ≥ 4.0 → `medium`, < 4.0 → `low`
- Include a new `dependency_check` adapter in `security_gate/scanners/` following the existing adapter pattern
- Add component score contribution to the final pass/review/reject decision

## References

- Official docs: https://dependency-check.github.io/DependencyCheck/dependency-check-cli/index.html
- OWASP A06: https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/