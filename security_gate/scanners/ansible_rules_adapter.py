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
_SERVICE_MODULES = {"service", "systemd", "systemd_service", "sysvinit"}
_CONTAINER_MODULES = {"docker_container", "podman_container", "lxc_container"}
# Modules that place a configuration file (or a line of one) on the host.  The
# body-reading rules are dispatched only for these, so that the recursive walk
# does not also treat a nested ``content:`` key as a module and report the same
# body twice.
_CONTENT_MODULES = _PERMISSION_MODULES | {"lineinfile", "blockinfile", "replace", "ini_file"}
_TRANSPORT_MODULES = {
    "get_url",
    "uri",
    "apt_repository",
    "yum_repository",
    "git",
    "pip",
    "npm",
    "maven_artifact",
}

# Module arguments that carry a configuration file body rather than a value.
# Several rules below have to read these because the artifact under review
# expresses the weakness inside a file it writes, not in a module argument:
# an sshd directive, a systemd unit, an export table.  Nothing is inferred from
# a body that is *absent* — every rule keys on an explicit insecure statement.
_TEXT_ARGS = ("content", "line", "block", "_raw", "cmd")

# Argument values meaning "off".
_FALSE_VALUES = {"false", "no", "0", "off", "none"}

# --- CWE-306: authentication that can be satisfied without a credential ---
_SSH_EMPTY_PASSWORD = re.compile(
    r"^\s*PermitEmptyPasswords\s+yes\b", re.IGNORECASE | re.MULTILINE
)
_PAM_ALWAYS_ALLOW = re.compile(
    r"^\s*auth\s+\S+\s+(?:\S*\bpam_permit\.so|\S+.*\bnullok\b)",
    re.IGNORECASE | re.MULTILINE,
)
_ANONYMOUS_ACCESS = re.compile(
    r"^\s*(?:anonymous_enable|anon_upload_enable|allow_anonymous)\s*=\s*(?:yes|true|1)\b",
    re.IGNORECASE | re.MULTILINE,
)

# --- CWE-778: the record of what happened is switched off or discarded ---
_LOG_DAEMONS = {
    "auditd",
    "audit",
    "rsyslog",
    "rsyslogd",
    "syslog",
    "syslog-ng",
    "systemd-journald",
    "journald",
}
_DISABLED_STATES = {"stopped", "absent", "masked"}
_JOURNAL_DISCARDS = re.compile(
    r"^\s*Storage\s*=\s*none\b", re.IGNORECASE | re.MULTILINE
)
_ROTATE_DISCARDS = re.compile(r"^\s*rotate\s+0\s*$", re.IGNORECASE | re.MULTILINE)
_SSH_LOG_QUIET = re.compile(r"^\s*LogLevel\s+QUIET\b", re.IGNORECASE | re.MULTILINE)
_AUDIT_RULES_CLEARED = re.compile(r"\bauditctl\b[^\n]*(?:\s-D\b|\s-e\s*0\b)")

# --- CWE-552: a share whose client specification names no client ---
_EXPORT_TO_EVERY_HOST = re.compile(
    r"^\s*/\S+\s+(?:\*|0\.0\.0\.0/0|::/0)\s*\(", re.MULTILINE
)

# --- CWE-770: a ceiling the platform would impose is explicitly removed ---
_UNIT_LIMIT_REMOVED = re.compile(
    r"^\s*(?:Limit(?:NOFILE|NPROC|CORE|AS|MEMLOCK)|TasksMax|MemoryMax|MemoryLimit)"
    r"\s*=\s*(?:infinity|unlimited)\b",
    re.IGNORECASE | re.MULTILINE,
)
_LIMITS_CONF_REMOVED = re.compile(
    r"^\s*\S+\s+(?:soft|hard|-)\s+(?:nofile|nproc|as|memlock|core|stack)\s+unlimited\b",
    re.IGNORECASE | re.MULTILINE,
)
_ULIMIT_REMOVED = re.compile(r"\bulimit\s+-\w+\s+unlimited\b", re.IGNORECASE)

# --- CWE-319: traffic carried without transport protection ---
_CERT_CHECK_ARGS = {"validate_certs", "validate_cert", "verify_ssl", "ssl_verify"}
_URL_ARGS = {"url", "uri", "repo", "baseurl", "mirrorlist", "chart_repo_url"}
_PLAINTEXT_URL = re.compile(r"^\s*http://", re.IGNORECASE)
_TRANSPORT_DISABLED = re.compile(
    r"^\s*(?:sslmode|ssl_mode)\s*[:=]\s*(?:disable|disabled|off|allow)\s*$"
    r"|^\s*(?:ssl|tls|use_tls|use_ssl|require_ssl|ssl_verify|tls_required)"
    r"\s*[:=]\s*(?:false|no|off|0)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# --- CWE-250: a workload installed with more authority than its job needs ---
_UNIT_RUNS_AS_ROOT = re.compile(
    r"^\s*User\s*=\s*(?:root|0)\s*$", re.IGNORECASE | re.MULTILINE
)
_UNIT_EXTRA_CAPABILITIES = re.compile(
    r"^\s*(?:AmbientCapabilities|CapabilityBoundingSet)\s*=.*"
    r"\bCAP_(?:SYS_ADMIN|SYS_MODULE|SYS_PTRACE|SYS_RAWIO|DAC_OVERRIDE|NET_ADMIN|SETUID)\b",
    re.IGNORECASE | re.MULTILINE,
)
_UNIT_ESCALATION_ALLOWED = re.compile(
    r"^\s*NoNewPrivileges\s*=\s*(?:false|no|0)\s*$", re.IGNORECASE | re.MULTILINE
)

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


def _text_bodies(args: dict[str, str]) -> list[str]:
    """Return the configuration-file bodies a task writes to the host.

    A playbook rarely states a weakness in its own vocabulary; it states it in
    the vocabulary of the file it installs.  These are the arguments that carry
    such a body, so the rules below can read the sshd directive, the unit
    stanza or the export line that the task will place on the host.
    """
    return [args[key] for key in _TEXT_ARGS if args.get(key)]


def _is_false(value: str | None) -> bool:
    return value is not None and value.strip().strip("'\"").lower() in _FALSE_VALUES


def _check_authentication(args: dict[str, str], loc: tuple[str, str]) -> list[dict[str, Any]]:
    """CWE-306: access to a function is granted without proving identity."""
    resource_id, template = loc
    findings: list[dict[str, Any]] = []
    for body in _text_bodies(args):
        if _SSH_EMPTY_PASSWORD.search(body):
            findings.append(
                _new_finding(
                    "critical",
                    "Remote login is permitted with an empty password "
                    "(PermitEmptyPasswords yes), so no credential is required.",
                    resource_id,
                    template,
                    "ssh_empty_password",
                )
            )
        if _PAM_ALWAYS_ALLOW.search(body):
            findings.append(
                _new_finding(
                    "critical",
                    "An authentication stack entry succeeds unconditionally "
                    "(pam_permit / nullok).",
                    resource_id,
                    template,
                    "missing_authentication",
                )
            )
        if _ANONYMOUS_ACCESS.search(body):
            findings.append(
                _new_finding(
                    "high",
                    "A service is configured to accept anonymous access.",
                    resource_id,
                    template,
                    "missing_authentication",
                )
            )
    return findings


def _check_audit_logging(
    module: str, args: dict[str, str], loc: tuple[str, str]
) -> list[dict[str, Any]]:
    """CWE-778: activity on the host is not recorded, or is not retained."""
    resource_id, template = loc
    findings: list[dict[str, Any]] = []

    if module in _SERVICE_MODULES:
        name = str(args.get("name", "")).strip().strip("'\"")
        if name.removesuffix(".service").lower() in _LOG_DAEMONS:
            state = str(args.get("state", "")).strip().lower()
            turned_off = (
                state in _DISABLED_STATES
                or _is_false(args.get("enabled"))
                or str(args.get("masked", "")).strip().lower() in {"true", "yes"}
            )
            if turned_off:
                findings.append(
                    _new_finding(
                        "high",
                        f"The logging service {name} is disabled, so activity on the "
                        "host is not recorded.",
                        resource_id,
                        template,
                        "audit_logging",
                    )
                )

    for body in _text_bodies(args):
        if _AUDIT_RULES_CLEARED.search(body):
            findings.append(
                _new_finding(
                    "high",
                    "Audit rules are cleared or auditing is switched off.",
                    resource_id,
                    template,
                    "audit_logging",
                )
            )
        if _JOURNAL_DISCARDS.search(body):
            findings.append(
                _new_finding(
                    "high",
                    "The journal is configured to keep no storage, so log records "
                    "do not survive.",
                    resource_id,
                    template,
                    "audit_logging",
                )
            )
        if _ROTATE_DISCARDS.search(body):
            findings.append(
                _new_finding(
                    "medium",
                    "Log rotation keeps no previous copies (rotate 0), so records "
                    "are discarded rather than retained.",
                    resource_id,
                    template,
                    "log_retention",
                )
            )
        if _SSH_LOG_QUIET.search(body):
            findings.append(
                _new_finding(
                    "medium",
                    "The SSH daemon is set to LogLevel QUIET, so authentication "
                    "attempts are not logged.",
                    resource_id,
                    template,
                    "audit_logging",
                )
            )
    return findings


def _check_external_exposure(args: dict[str, str], loc: tuple[str, str]) -> list[dict[str, Any]]:
    """CWE-552: a directory is shared with a client list that names no client."""
    resource_id, template = loc
    for body in _text_bodies(args):
        if _EXPORT_TO_EVERY_HOST.search(body):
            return [
                _new_finding(
                    "high",
                    "A filesystem export names no client restriction, so any host "
                    "that can reach this one may read the data.",
                    resource_id,
                    template,
                    "nfs_world_export",
                )
            ]
    return []


def _check_resource_limits(args: dict[str, str], loc: tuple[str, str]) -> list[dict[str, Any]]:
    """CWE-770: a ceiling the platform would otherwise impose is removed."""
    resource_id, template = loc
    for body in _text_bodies(args):
        if (
            _UNIT_LIMIT_REMOVED.search(body)
            or _LIMITS_CONF_REMOVED.search(body)
            or _ULIMIT_REMOVED.search(body)
        ):
            return [
                _new_finding(
                    "medium",
                    "A resource ceiling is explicitly removed (infinity / unlimited), "
                    "so the workload can consume the host without bound.",
                    resource_id,
                    template,
                    "missing_resource_limit",
                )
            ]
    return []


def _check_transport(args: dict[str, str], loc: tuple[str, str]) -> list[dict[str, Any]]:
    """CWE-319: data crosses the network without transport protection."""
    resource_id, template = loc
    findings: list[dict[str, Any]] = []

    for key in _CERT_CHECK_ARGS:
        if key in args and _is_false(args[key]):
            findings.append(
                _new_finding(
                    "high",
                    f"Certificate validation is disabled ({key}), so the peer on the "
                    "other end of the connection is not verified.",
                    resource_id,
                    template,
                    "insecure_transport",
                )
            )
            break

    for key in _URL_ARGS:
        value = args.get(key)
        if value and _PLAINTEXT_URL.match(str(value)):
            findings.append(
                _new_finding(
                    "high",
                    "A resource is retrieved over plaintext HTTP, so its contents are "
                    "readable and alterable in transit.",
                    resource_id,
                    template,
                    "insecure_transport",
                )
            )
            break

    for body in _text_bodies(args):
        if _TRANSPORT_DISABLED.search(body):
            findings.append(
                _new_finding(
                    "high",
                    "A service connection is configured with transport protection "
                    "switched off, so credentials and records cross the network in "
                    "the clear.",
                    resource_id,
                    template,
                    "insecure_transport",
                )
            )
            break

    return findings


def _check_privileges(
    module: str, args: dict[str, str], loc: tuple[str, str]
) -> list[dict[str, Any]]:
    """CWE-250: a workload is installed with more authority than it needs."""
    resource_id, template = loc
    findings: list[dict[str, Any]] = []

    if module in _CONTAINER_MODULES:
        if str(args.get("privileged", "")).strip().lower() in {"true", "yes"}:
            findings.append(
                _new_finding(
                    "critical",
                    "A container is run in privileged mode, giving it the host's "
                    "full capability set.",
                    resource_id,
                    template,
                    "privileged_container",
                )
            )
        if str(args.get("user", "")).strip().strip("'\"").lower() in {"root", "0", "0:0"}:
            findings.append(
                _new_finding(
                    "high",
                    "A container is run as root.",
                    resource_id,
                    template,
                    "runs_as_root",
                )
            )

    for body in _text_bodies(args):
        if _UNIT_RUNS_AS_ROOT.search(body):
            findings.append(
                _new_finding(
                    "high",
                    "A service unit runs as root rather than as a dedicated account.",
                    resource_id,
                    template,
                    "runs_as_root",
                )
            )
        if _UNIT_EXTRA_CAPABILITIES.search(body):
            findings.append(
                _new_finding(
                    "high",
                    "A service unit is granted administrative Linux capabilities.",
                    resource_id,
                    template,
                    "unnecessary_privileges",
                )
            )
        if _UNIT_ESCALATION_ALLOWED.search(body):
            findings.append(
                _new_finding(
                    "medium",
                    "A service unit permits privilege escalation "
                    "(NoNewPrivileges=false).",
                    resource_id,
                    template,
                    "unnecessary_privileges",
                )
            )

    return findings


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
            if module in _CONTENT_MODULES:
                findings.extend(_check_authentication(args, loc))
                findings.extend(_check_external_exposure(args, loc))
            if module in _CONTENT_MODULES or module in _COMMAND_MODULES:
                findings.extend(_check_resource_limits(args, loc))
            if module in _CONTENT_MODULES or module in _COMMAND_MODULES:
                findings.extend(_check_privileges(module, args, loc))
            if module in _CONTENT_MODULES or module in _SERVICE_MODULES or module in _COMMAND_MODULES:
                findings.extend(_check_audit_logging(module, args, loc))
            if module in _CONTENT_MODULES or module in _TRANSPORT_MODULES:
                findings.extend(_check_transport(args, loc))
            if module in _CONTAINER_MODULES:
                findings.extend(_check_privileges(module, args, loc))

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
