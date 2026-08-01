"""Semantic configuration rules for the on-premises (Ansible) gate path.

The CDK path carries a set of resource heuristics that read the *meaning* of a
template -- a security group open to 0.0.0.0/0, an IAM policy granting ``*``, an
unencrypted volume.  The on-prem path had no equivalent: ansible-lint judges
style, checkov's Ansible framework covers few checks, and the secret scanner
only looks for credentials.  A playbook could therefore open SSH to the internet
or grant passwordless root and score zero.

This adapter closes that asymmetry by applying the same *classes* of check to
playbook tasks, emitting findings under the same dedup categories and severities
the CDK heuristics use, so that a weakness expressed on either side of the
hybrid boundary is scored comparably.

Status values (consistent with the other scanner adapters):
    "ok" | "skipped" | "error"
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import yaml

_SKIPPED_STATUS = "skipped"
_OK_STATUS = "ok"
_ERROR_STATUS = "error"

# Source specifications that mean "from anywhere".
_OPEN_SOURCES = {"0.0.0.0/0", "0.0.0.0", "::/0", "any", "all", "*"}

# Ports whose exposure to the internet is treated as critical rather than high,
# matching the CDK path's distinction between sg_ssh_open and sg_public_ingress.
_ADMIN_PORTS = {"22", "23", "3389", "5985", "5986"}

_FIREWALL_MODULES = {"iptables", "ufw", "firewalld"}
_PERMISSION_MODULES = {"file", "copy", "template", "unarchive", "assemble"}
_FILESYSTEM_MODULES = {"filesystem", "mount", "parted", "lvol"}
_COMMAND_MODULES = {"command", "shell", "raw"}

# Any of these in a module argument is taken as evidence that storage
# encryption was configured, which suppresses the unencrypted-storage rules for
# that file.  Deliberately matched against parsed argument values only: a
# comment or a task name mentioning LUKS must not silence the rule.
_ENCRYPTION_HINT = re.compile(
    r"luks|cryptsetup|dm[-_]crypt|crypttab|/dev/mapper/|encrypted\s*[:=]\s*(?:true|yes)",
    re.IGNORECASE,
)

# Unrestricted passwordless sudo, in a sudoers line wherever it is written.
_NOPASSWD_ALL = re.compile(r"NOPASSWD\s*:\s*ALL", re.IGNORECASE)

# mkfs invoked through command/shell.
_MKFS = re.compile(r"\bmkfs(?:\.\w+)?\b", re.IGNORECASE)

# A device mount line written into /etc/fstab.
_FSTAB_DEVICE = re.compile(r"^\s*(?:/dev/\S+|UUID=\S+|LABEL=\S+)\s+\S+\s+\S+", re.IGNORECASE)

# Symbolic modes that grant write to group, other, or all.
_SYMBOLIC_WORLD_WRITE = re.compile(r"[goa][goa]*\+[rwxXst]*w")


def _new_finding(
    severity: str, message: str, resource_id: str, template: str, category: str
) -> dict[str, Any]:
    return {
        "severity": severity,
        "source": "ansible-rules",
        "message": message,
        "resource_id": resource_id,
        "template": template,
        "category": category,
    }


def _iter_mappings(node: yaml.Node) -> Iterator[yaml.MappingNode]:
    if isinstance(node, yaml.MappingNode):
        yield node
        for _, value in node.value:
            yield from _iter_mappings(value)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            yield from _iter_mappings(item)


def _iter_scalars(node: yaml.Node) -> Iterator[yaml.ScalarNode]:
    if isinstance(node, yaml.ScalarNode):
        yield node
    elif isinstance(node, yaml.MappingNode):
        for _, value in node.value:
            yield from _iter_scalars(value)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            yield from _iter_scalars(item)


def _iter_pairs(node: yaml.Node) -> Iterator[tuple[yaml.ScalarNode, yaml.Node]]:
    for mapping in _iter_mappings(node):
        for key, value in mapping.value:
            if isinstance(key, yaml.ScalarNode):
                yield key, value


def _encryption_configured(node: yaml.Node) -> bool:
    """True when some module argument in the document sets up encrypted storage.

    Descriptive keys are excluded so that a task *named* after the absence of
    encryption cannot silence the rule that would flag it.
    """
    descriptive: set[int] = set()
    for key, value in _iter_pairs(node):
        if str(key.value) in {"name", "when", "tags", "register"}:
            descriptive.update(id(scalar) for scalar in _iter_scalars(value))

    for scalar in _iter_scalars(node):
        if id(scalar) in descriptive:
            continue
        if _ENCRYPTION_HINT.search(str(scalar.value)):
            return True
    return False


def _args_of(value_node: yaml.Node) -> dict[str, str]:
    """Flatten a module's argument node into a string map.

    A free-form invocation (``command: mkfs.ext4 /dev/sdb1``) is stored under
    the ``_raw`` key so command rules can inspect it uniformly.
    """
    args: dict[str, str] = {}
    if isinstance(value_node, yaml.MappingNode):
        for key, val in value_node.value:
            if isinstance(key, yaml.ScalarNode) and isinstance(val, yaml.ScalarNode):
                args[str(key.value)] = str(val.value)
    elif isinstance(value_node, yaml.ScalarNode):
        args["_raw"] = str(value_node.value)
    return args


def _is_open(source: str | None) -> bool:
    return source is not None and source.strip().lower() in _OPEN_SOURCES


def _ingress_severity(port: str | None) -> tuple[str, str]:
    """Return (severity, category) for a rule exposed to the whole internet."""
    if port and port.strip() in _ADMIN_PORTS:
        return "critical", "sg_ssh_open"
    return "high", "sg_public_ingress"


def _check_firewall(module: str, args: dict[str, str], loc: tuple[str, str]) -> list[dict[str, Any]]:
    resource_id, template = loc

    if module == "iptables":
        jump = args.get("jump", "").strip().upper()
        if jump in {"DROP", "REJECT"} or "policy" in args:
            return []
        if not _is_open(args.get("source") or args.get("src")):
            return []
        port = args.get("destination_port") or args.get("to_ports")
        severity, category = _ingress_severity(port)
        target = f"port {port}" if port else "all ports"
        return [
            _new_finding(
                severity,
                f"Firewall rule accepts traffic on {target} from any address (0.0.0.0/0).",
                resource_id,
                template,
                category,
            )
        ]

    if module == "ufw":
        if args.get("rule", "").strip().lower() != "allow":
            return []
        source = args.get("src") or args.get("from_ip") or args.get("from")
        # ufw treats an omitted source as "from anywhere".
        if source is not None and not _is_open(source):
            return []
        port = args.get("port") or args.get("to_port")
        severity, category = _ingress_severity(port)
        target = f"port {port}" if port else "all ports"
        return [
            _new_finding(
                severity,
                f"Host firewall allows {target} from any address.",
                resource_id,
                template,
                category,
            )
        ]

    if module == "firewalld":
        rich_rule = args.get("rich_rule", "")
        source = args.get("source")
        enabled = args.get("state", "").strip().lower() in {"enabled", "present"}
        open_rich = any(cidr in rich_rule for cidr in ("0.0.0.0/0", "::/0"))
        if not (open_rich or _is_open(source) or (enabled and args.get("zone", "").lower() == "public")):
            return []
        port = args.get("port", "").split("/")[0] or args.get("service")
        severity, category = _ingress_severity(port)
        return [
            _new_finding(
                severity,
                "firewalld exposes a service to an unrestricted source.",
                resource_id,
                template,
                category,
            )
        ]

    return []


def _mode_is_world_writable(mode: str) -> bool:
    """True when *mode* grants write permission to group or other.

    Numeric modes follow Ansible's own interpretation: a leading zero means
    octal, and a bare number is decimal (which is why ``mode: 777`` is not the
    same as ``mode: '0777'``).
    """
    text = mode.strip().strip("'\"")
    if not text:
        return False

    if text.isdigit():
        if text.startswith("0"):
            digits = text[-3:]
        else:
            digits = oct(int(text))[2:][-3:]
        return any(int(d) & 0o2 for d in digits[1:])

    return bool(_SYMBOLIC_WORLD_WRITE.search(text))


def _check_permissions(args: dict[str, str], loc: tuple[str, str]) -> list[dict[str, Any]]:
    mode = args.get("mode")
    if mode is None or not _mode_is_world_writable(mode):
        return []
    resource_id, template = loc
    path = args.get("path") or args.get("dest") or "target"
    return [
        _new_finding(
            "high",
            f"Filesystem permissions on {path} grant write access beyond the owner (mode {mode}).",
            resource_id,
            template,
            "file_world_writable",
        )
    ]


def _check_storage(
    module: str, args: dict[str, str], loc: tuple[str, str], encrypted: bool
) -> list[dict[str, Any]]:
    if encrypted:
        return []
    resource_id, template = loc

    if module in {"filesystem", "parted", "lvol"} or (
        module in _COMMAND_MODULES and _MKFS.search(args.get("_raw", "") or args.get("cmd", ""))
    ):
        return [
            _new_finding(
                "high",
                "A filesystem is created without an encryption layer (no LUKS/dm-crypt).",
                resource_id,
                template,
                "storage_encryption",
            )
        ]

    if module == "mount":
        return [
            _new_finding(
                "medium",
                "A volume is mounted without encryption.",
                resource_id,
                template,
                "storage_mount_encryption",
            )
        ]

    if module == "lineinfile" and "fstab" in (args.get("path") or args.get("dest") or ""):
        if _FSTAB_DEVICE.match(args.get("line", "")):
            return [
                _new_finding(
                    "medium",
                    "A persistent mount is added to /etc/fstab without encryption.",
                    resource_id,
                    template,
                    "storage_mount_encryption",
                )
            ]

    return []


def _scan_document(node: yaml.Node, template: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    encrypted = _encryption_configured(node)

    for scalar in _iter_scalars(node):
        if _NOPASSWD_ALL.search(str(scalar.value)):
            line = scalar.start_mark.line + 1
            findings.append(
                _new_finding(
                    "critical",
                    "Unrestricted passwordless sudo is granted (NOPASSWD: ALL).",
                    f"{template}:{line}",
                    template,
                    "iam_wildcard",
                )
            )

    for mapping in _iter_mappings(node):
        for key_node, value_node in mapping.value:
            if not isinstance(key_node, yaml.ScalarNode):
                continue
            module = str(key_node.value).split(".")[-1].strip().lower()
            loc = (f"{template}:{key_node.start_mark.line + 1}", template)
            args = _args_of(value_node)

            if module in _FIREWALL_MODULES:
                findings.extend(_check_firewall(module, args, loc))
            if module in _PERMISSION_MODULES:
                findings.extend(_check_permissions(args, loc))
            if module in _FILESYSTEM_MODULES or module in _COMMAND_MODULES or module == "lineinfile":
                findings.extend(_check_storage(module, args, loc, encrypted))

    return findings


def run_ansible_rules(
    files: list[Path],
    *,
    enabled: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """Apply semantic configuration rules to *files* and return (findings, status).

    Files that cannot be parsed as YAML are skipped rather than failing the
    scan; ansible's own syntax check is responsible for rejecting those.
    """
    if not enabled:
        return [], _SKIPPED_STATUS

    findings: list[dict[str, Any]] = []
    for file_path in files:
        path = Path(file_path)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        try:
            documents = list(yaml.compose_all(text))
        except yaml.YAMLError:
            continue
        for document in documents:
            if document is None:
                continue
            findings.extend(_scan_document(document, path.name))

    # One finding per (resource_id, category) so a task matched by several rule
    # branches is not counted twice.
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for finding in findings:
        unique.setdefault((finding["resource_id"], finding["category"]), finding)
    return list(unique.values()), _OK_STATUS
