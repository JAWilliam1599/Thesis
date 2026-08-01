"""Unit tests for the Ansible-side evidence helpers (RQ2 checkpoints).

These cover the parsing/classification logic that turns raw ansible-playbook
output into the structured verification, idempotency and failure-attribution
fields recorded in each run summary.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.ansible_pipeline import (  # noqa: E402
    classify_ansible_failure,
    find_verify_playbook,
    parse_play_recap,
)

RECAP_CONVERGED = """
PLAY RECAP *********************************************************************
db1                        : ok=12   changed=0    unreachable=0    failed=0    skipped=1
web1                       : ok=5    changed=0    unreachable=0    failed=0    skipped=0
"""

RECAP_CHANGED = """
PLAY RECAP *********************************************************************
db1                        : ok=12   changed=3    unreachable=0    failed=0    skipped=1
"""

RECAP_UNREACHABLE = """
fatal: [db1]: UNREACHABLE! => {"msg": "Failed to connect to the host via ssh"}

PLAY RECAP *********************************************************************
db1                        : ok=0    changed=0    unreachable=1    failed=0    skipped=0
"""

RECAP_FAILED = """
fatal: [db1]: FAILED! => {"msg": "package postgresql-16 not found"}

PLAY RECAP *********************************************************************
db1                        : ok=4    changed=1    unreachable=0    failed=1    skipped=0
"""


# --------------------------------------------------------------------------- #
# PLAY RECAP parsing
# --------------------------------------------------------------------------- #
def test_recap_aggregates_across_hosts():
    recap = parse_play_recap(RECAP_CONVERGED)
    assert recap["parsed"] is True
    assert set(recap["hosts"]) == {"db1", "web1"}
    assert recap["totals"] == {"ok": 17, "changed": 0, "unreachable": 0, "failed": 0}


def test_recap_reports_changes():
    assert parse_play_recap(RECAP_CHANGED)["totals"]["changed"] == 3


def test_missing_recap_is_flagged_rather_than_read_as_zero_changes():
    """A run that aborts before any play must not look like a converged run."""
    recap = parse_play_recap("ERROR! the playbook could not be found")
    assert recap["parsed"] is False
    assert recap["totals"]["changed"] == 0


def test_empty_output_is_safe():
    assert parse_play_recap("")["parsed"] is False
    assert parse_play_recap(None)["parsed"] is False  # type: ignore[arg-type]


def test_recap_counts_unreachable_and_failed():
    assert parse_play_recap(RECAP_UNREACHABLE)["totals"]["unreachable"] == 1
    assert parse_play_recap(RECAP_FAILED)["totals"]["failed"] == 1


# --------------------------------------------------------------------------- #
# Failure attribution
# --------------------------------------------------------------------------- #
def test_success_classifies_as_ok():
    assert classify_ansible_failure({"return_code": 0, "output": RECAP_CONVERGED}) == "ok"


def test_success_is_ok_even_with_scary_text():
    assert classify_ansible_failure({"return_code": 0, "output": "permission denied"}) == "ok"


def test_unreachable_host_is_connectivity():
    assert classify_ansible_failure(
        {"return_code": 4, "output": RECAP_UNREACHABLE}
    ) == "connectivity"


def test_unreachable_with_auth_message_is_authentication():
    output = (
        'fatal: [db1]: UNREACHABLE! => {"msg": "Invalid/incorrect password: '
        'Permission denied, please try again."}\n'
    )
    assert classify_ansible_failure({"return_code": 4, "output": output}) == "authentication"


def test_missing_sudo_password_is_authentication():
    assert classify_ansible_failure(
        {"return_code": 2, "output": 'fatal: [db1]: FAILED! => {"msg": "Missing sudo password"}'}
    ) == "authentication"


def test_task_failure_is_task_error():
    assert classify_ansible_failure({"return_code": 2, "output": RECAP_FAILED}) == "task_error"


def test_syntax_error_is_validation():
    assert classify_ansible_failure(
        {"return_code": 4, "output": "ERROR! Syntax Error while loading YAML."}
    ) == "validation"


def test_unattributable_failure_is_unknown_not_silently_ok():
    assert classify_ansible_failure({"return_code": 1, "output": "boom"}) == "unknown"


def test_missing_return_code_is_treated_as_failure():
    assert classify_ansible_failure({"output": ""}) == "unknown"


# --------------------------------------------------------------------------- #
# Verification playbook resolution
# --------------------------------------------------------------------------- #
def test_verify_playbook_autodetected(tmp_path: Path):
    (tmp_path / "verify.yml").write_text("- hosts: all\n")
    assert find_verify_playbook(tmp_path) == tmp_path / "verify.yml"


def test_verify_playbook_absent_returns_none(tmp_path: Path):
    assert find_verify_playbook(tmp_path) is None


def test_explicit_relative_verify_playbook(tmp_path: Path):
    (tmp_path / "checks").mkdir()
    (tmp_path / "checks" / "post.yml").write_text("- hosts: all\n")
    assert find_verify_playbook(tmp_path, "checks/post.yml") == tmp_path / "checks" / "post.yml"


def test_explicit_missing_verify_playbook_returns_none(tmp_path: Path):
    assert find_verify_playbook(tmp_path, "nope.yml") is None


@pytest.mark.parametrize("name", ["verify.yml", "verify.yaml", "assert.yml"])
def test_all_default_verify_names_are_probed(tmp_path: Path, name: str):
    (tmp_path / name).write_text("- hosts: all\n")
    assert find_verify_playbook(tmp_path) == tmp_path / name
