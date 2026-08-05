"""Tests for the on-premises semantic configuration rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from security_gate.scanners.ansible_rules_adapter import (
    _mode_is_world_writable,
    run_ansible_rules,
)


def _write(tmp_path: Path, body: str, name: str = "site.yml") -> list[Path]:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return [path]


def _categories(findings: list[dict]) -> set[str]:
    return {f["category"] for f in findings}


def test_disabled_returns_skipped():
    findings, status = run_ansible_rules([], enabled=False)
    assert (findings, status) == ([], "skipped")


def test_no_files_is_ok():
    assert run_ansible_rules([]) == ([], "ok")


def test_iptables_admin_port_open_to_world_is_critical(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - name: Allow SSH from anywhere
      ansible.builtin.iptables:
        chain: INPUT
        protocol: tcp
        destination_port: '22'
        source: 0.0.0.0/0
        jump: ACCEPT
""")
    findings, status = run_ansible_rules(files)
    assert status == "ok"
    assert len(findings) == 1
    assert findings[0]["category"] == "sg_ssh_open"
    assert findings[0]["severity"] == "critical"
    assert findings[0]["source"] == "ansible-rules"


def test_iptables_non_admin_port_open_to_world_is_high(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.iptables:
        destination_port: '8080'
        source: 0.0.0.0/0
        jump: ACCEPT
""")
    findings, _ = run_ansible_rules(files)
    assert [f["severity"] for f in findings] == ["high"]
    assert _categories(findings) == {"sg_public_ingress"}


def test_iptables_restricted_source_is_clean(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.iptables:
        destination_port: '22'
        source: 10.0.0.0/8
        jump: ACCEPT
""")
    assert run_ansible_rules(files) == ([], "ok")


def test_iptables_default_deny_policy_is_not_a_finding(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.iptables:
        chain: INPUT
        policy: DROP
""")
    assert run_ansible_rules(files) == ([], "ok")


def test_ufw_allow_without_source_means_from_anywhere(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - community.general.ufw:
        rule: allow
        port: '22'
        proto: tcp
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"sg_ssh_open"}


def test_ufw_allow_from_private_range_is_clean(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - community.general.ufw:
        rule: allow
        port: '22'
        src: 192.168.1.0/24
""")
    assert run_ansible_rules(files) == ([], "ok")


def test_nopasswd_all_in_copied_sudoers_content(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.copy:
        dest: /etc/sudoers.d/appuser
        content: "appuser ALL=(ALL) NOPASSWD: ALL\\n"
        mode: '0440'
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"iam_wildcard"}
    assert findings[0]["severity"] == "critical"


def test_sudo_requiring_password_is_clean(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.copy:
        dest: /etc/sudoers.d/appuser
        content: "appuser ALL=(ALL) ALL\\n"
        mode: '0440'
""")
    assert run_ansible_rules(files) == ([], "ok")


def test_world_writable_directory_mode(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.file:
        path: /opt/app
        state: directory
        mode: '0777'
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"file_world_writable"}
    assert "/opt/app" in findings[0]["message"]


@pytest.mark.parametrize("mode", ["0777", "0666", "0002", "o+w", "a+w", "ug+rw", "511"])
def test_modes_granting_write_beyond_owner(mode):
    assert _mode_is_world_writable(mode) is True


@pytest.mark.parametrize("mode", ["0755", "0644", "0700", "0440", "u+w", ""])
def test_modes_restricted_to_owner(mode):
    assert _mode_is_world_writable(mode) is False


def test_unquoted_numeric_mode_uses_ansible_decimal_semantics():
    # Ansible reads a bare 511 as decimal, which is 0777.
    assert _mode_is_world_writable("511") is True
    # ...and a bare 777 as decimal 777, which is 0o1411 and not world-writable.
    assert _mode_is_world_writable("777") is False


def test_unquoted_octal_mode_parsed_as_integer_is_detected(tmp_path):
    # YAML 1.1 turns an unquoted 0777 into the integer 511.
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.file:
        path: /opt/app
        mode: 511
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"file_world_writable"}


def test_mkfs_without_encryption_is_flagged(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.command: mkfs.ext4 -F /dev/sdb1
    - ansible.builtin.lineinfile:
        path: /etc/fstab
        line: /dev/sdb1 /srv/appdata ext4 defaults 0 2
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"storage_encryption", "storage_mount_encryption"}


def test_encrypted_storage_suppresses_the_storage_rules(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - name: Open the encrypted volume
      ansible.builtin.command: cryptsetup luksOpen /dev/sdb1 appdata
    - ansible.builtin.command: mkfs.ext4 -F /dev/mapper/appdata
""")
    assert run_ansible_rules(files) == ([], "ok")


def test_a_comment_mentioning_luks_does_not_suppress_the_rule(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    # This filesystem has no encryption layer (no LUKS / dm-crypt).
    - name: Create the data filesystem without LUKS
      ansible.builtin.command: mkfs.ext4 -F /dev/sdb1
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"storage_encryption"}


def test_unparseable_yaml_is_skipped_not_an_error(tmp_path):
    files = _write(tmp_path, "this: is: not: valid: yaml:\n  - [\n")
    findings, status = run_ansible_rules(files)
    assert status == "ok"
    assert findings == []


def test_findings_are_unique_per_resource_and_category(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.iptables:
        destination_port: '22'
        source: 0.0.0.0/0
        jump: ACCEPT
    - ansible.builtin.iptables:
        destination_port: '22'
        source: 0.0.0.0/0
        jump: ACCEPT
""")
    findings, _ = run_ansible_rules(files)
    # Two distinct tasks on distinct lines: both reported, neither duplicated.
    assert len(findings) == 2
    assert len({f["resource_id"] for f in findings}) == 2


# --- Rules added for the remediated arm of the coverage evaluation ------------
#
# Each weakness below is written in a *different* form from the evaluation
# fixture that motivated the rule, so a passing test is evidence that the rule
# keys on the weakness rather than on the fixture's phrasing.  Each is paired
# with the secure form of the same construct, because a rule that fired on both
# would buy coverage at the cost of specificity.


def test_pam_stack_that_always_succeeds_is_missing_authentication(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.copy:
        dest: /etc/pam.d/appsvc
        mode: '0644'
        content: |
          auth sufficient pam_permit.so
          account required pam_unix.so
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"missing_authentication"}


def test_anonymous_service_access_is_missing_authentication(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.copy:
        dest: /etc/vsftpd.conf
        mode: '0644'
        content: |
          listen=YES
          anonymous_enable=YES
""")
    findings, _ = run_ansible_rules(files)
    assert "missing_authentication" in _categories(findings)


def test_sshd_requiring_a_password_is_not_flagged(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.lineinfile:
        path: /etc/ssh/sshd_config
        line: 'PermitEmptyPasswords no'
        mode: '0600'
""")
    findings, _ = run_ansible_rules(files)
    assert findings == []


def test_removing_the_system_logger_is_insufficient_logging(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.service:
        name: rsyslog
        state: stopped
        enabled: false
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"audit_logging"}


def test_clearing_audit_rules_from_a_command_is_insufficient_logging(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.command: auditctl -e 0
""")
    findings, _ = run_ansible_rules(files)
    assert "audit_logging" in _categories(findings)


def test_journal_that_keeps_no_storage_is_insufficient_logging(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.copy:
        dest: /etc/systemd/journald.conf
        mode: '0644'
        content: |
          [Journal]
          Storage=none
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"audit_logging"}


def test_enabled_audit_daemon_is_not_flagged(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.systemd:
        name: auditd
        state: started
        enabled: true
""")
    findings, _ = run_ansible_rules(files)
    assert findings == []


def test_export_to_any_address_is_externally_accessible(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.lineinfile:
        path: /etc/exports
        mode: '0644'
        line: '/srv/share 0.0.0.0/0(rw,no_root_squash)'
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"nfs_world_export"}


def test_export_restricted_to_a_subnet_is_not_flagged(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.lineinfile:
        path: /etc/exports
        mode: '0644'
        line: '/srv/share 10.20.0.0/16(ro,root_squash)'
""")
    findings, _ = run_ansible_rules(files)
    assert findings == []


def test_ulimit_removed_from_a_shell_command_is_unbounded(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.shell: ulimit -n unlimited && exec /usr/local/bin/worker
""")
    findings, _ = run_ansible_rules(files)
    assert "missing_resource_limit" in _categories(findings)


def test_unit_with_a_stated_ceiling_is_not_flagged(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.copy:
        dest: /etc/systemd/system/worker.service
        mode: '0644'
        content: |
          [Service]
          User=worker
          LimitNOFILE=4096
          TasksMax=256
""")
    findings, _ = run_ansible_rules(files)
    assert findings == []


def test_plaintext_url_is_cleartext_transmission(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.uri:
        url: http://api.internal.example.com/v1/enrol
        method: POST
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"insecure_transport"}


def test_protected_url_with_certificate_checking_is_not_flagged(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - ansible.builtin.uri:
        url: https://api.internal.example.com/v1/enrol
        method: POST
        validate_certs: true
""")
    findings, _ = run_ansible_rules(files)
    assert findings == []


def test_privileged_container_is_unnecessary_privilege(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - community.docker.docker_container:
        name: ingest
        image: registry.example.com/ingest:1.4
        privileged: true
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"privileged_container"}


def test_container_running_as_root_is_unnecessary_privilege(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - community.docker.docker_container:
        name: ingest
        image: registry.example.com/ingest:1.4
        user: root
""")
    findings, _ = run_ansible_rules(files)
    assert _categories(findings) == {"runs_as_root"}


def test_container_running_as_a_named_account_is_not_flagged(tmp_path):
    files = _write(tmp_path, """
- hosts: all
  tasks:
    - community.docker.docker_container:
        name: ingest
        image: registry.example.com/ingest:1.4
        user: ingestsvc
        privileged: false
""")
    findings, _ = run_ansible_rules(files)
    assert findings == []

