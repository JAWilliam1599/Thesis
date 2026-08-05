"""Unit tests for the shared scoring/decision core of the IaC security gate.

These back the threshold and deduplication claims made in the evaluation
chapter: the boundaries are asserted here rather than inferred from run logs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security_gate.iac_security_gate import (  # noqa: E402
    COST_BANDS,
    SEVERITY_POINTS,
    THRESHOLDS,
    IaCSecurityGate,
    _decision,
    _dedupe_findings,
    _new_finding,
    _score_findings,
)


def _categories_of(resources: dict) -> set[str]:
    findings = IaCSecurityGate().analyze_template({"Resources": resources})
    return {f["category"] for f in findings}


# --------------------------------------------------------------------------- #
# Decision thresholds
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "pass"),
        (20, "pass"),      # upper edge of the pass band
        (21, "review"),    # first review score
        (80, "review"),    # upper edge of the review band
        (81, "reject"),    # first reject score
        (1000, "reject"),
    ],
)
def test_decision_band_boundaries(score, expected):
    assert _decision(score) == expected


def test_declared_thresholds_match_documented_values():
    assert THRESHOLDS == {"pass_max": 20, "review_max": 80}


def test_decision_honours_caller_supplied_thresholds():
    assert _decision(30, pass_max=50, review_max=90) == "pass"
    assert _decision(60, pass_max=50, review_max=90) == "review"
    assert _decision(91, pass_max=50, review_max=90) == "reject"


# --------------------------------------------------------------------------- #
# Score composition:  S = sum(w(sev)) + c(cost) + 5v + ml
# --------------------------------------------------------------------------- #
def _findings(*severities):
    return [
        _new_finding(sev, "test", f"finding {i}", f"res{i}", category=f"cat{i}")
        for i, sev in enumerate(severities)
    ]


def test_severity_weights_are_the_documented_ones():
    assert SEVERITY_POINTS == {"critical": 20, "high": 10, "medium": 5, "low": 1}


def test_severity_component_is_the_weight_sum():
    result = _score_findings(
        _findings("critical", "high", "medium", "low"),
        cost_delta_usd=0.0,
        config_violations=0,
    )
    assert result["severity"] == 36  # 20 + 10 + 5 + 1
    assert result["total"] == 36
    assert result["decision"] == "review"


def test_unknown_severity_defaults_to_low_weight():
    result = _score_findings(
        _findings("catastrophic"), cost_delta_usd=0.0, config_violations=0
    )
    assert result["severity"] == 1


@pytest.mark.parametrize(
    "delta,expected",
    [
        (0.0, 0),
        (COST_BANDS["med_usd"], 0),          # boundary is exclusive
        (COST_BANDS["med_usd"] + 0.01, COST_BANDS["med_points"]),
        (COST_BANDS["high_usd"], COST_BANDS["med_points"]),
        (COST_BANDS["high_usd"] + 0.01, COST_BANDS["high_points"]),
    ],
)
def test_cost_bands(delta, expected):
    result = _score_findings([], cost_delta_usd=delta, config_violations=0)
    assert result["cost"] == expected


def test_config_violations_weigh_five_each():
    result = _score_findings([], cost_delta_usd=0.0, config_violations=3)
    assert result["aws_config"] == 15


def test_negative_inputs_cannot_reduce_the_score():
    result = _score_findings(
        [], cost_delta_usd=-100.0, config_violations=-5, ml_score=-7
    )
    assert result == {
        "severity": 0, "cost": 0, "aws_config": 0, "ml_risk": 0,
        "total": 0, "decision": "pass",
    }


def test_total_is_the_sum_of_all_components():
    result = _score_findings(
        _findings("critical", "high"),          # 30
        cost_delta_usd=60.0,                    # 10
        config_violations=2,                    # 10
        ml_score=14,                            # 14
    )
    assert result["total"] == 64
    assert result["decision"] == "review"


def test_a_single_critical_plus_ml_stays_inside_pass_only_when_under_threshold():
    """One critical finding (20) sits exactly on the pass edge; any ML mass tips it."""
    assert _score_findings(_findings("critical"), cost_delta_usd=0.0,
                           config_violations=0)["decision"] == "pass"
    assert _score_findings(_findings("critical"), cost_delta_usd=0.0,
                           config_violations=0, ml_score=1)["decision"] == "review"


# --------------------------------------------------------------------------- #
# Cross-scanner deduplication
# --------------------------------------------------------------------------- #
def _cat_finding(severity, source, resource_id, category, template="t.json"):
    f = _new_finding(severity, source, f"{source}:{category}", resource_id, category)
    f["template"] = template
    return f


def test_same_resource_and_category_collapses_to_one_finding():
    deduped = _dedupe_findings([
        _cat_finding("high", "heuristic", "SG1", "open_ssh"),
        _cat_finding("high", "checkov", "SG1", "open_ssh"),
    ])
    assert len(deduped) == 1
    assert set(deduped[0]["source"].split("+")) == {"heuristic", "checkov"}


def test_dedup_keeps_the_highest_severity():
    deduped = _dedupe_findings([
        _cat_finding("medium", "checkov", "SG1", "open_ssh"),
        _cat_finding("critical", "heuristic", "SG1", "open_ssh"),
    ])
    assert len(deduped) == 1
    assert deduped[0]["severity"] == "critical"
    assert "heuristic" in deduped[0]["source"]


def test_lower_severity_duplicate_is_discarded_not_merged_upward():
    deduped = _dedupe_findings([
        _cat_finding("critical", "heuristic", "SG1", "open_ssh"),
        _cat_finding("low", "checkov", "SG1", "open_ssh"),
    ])
    assert len(deduped) == 1
    assert deduped[0]["severity"] == "critical"


def test_different_resources_are_never_merged():
    deduped = _dedupe_findings([
        _cat_finding("high", "checkov", "SG1", "open_ssh"),
        _cat_finding("high", "checkov", "SG2", "open_ssh"),
    ])
    assert len(deduped) == 2


def test_different_templates_are_never_merged():
    deduped = _dedupe_findings([
        _cat_finding("high", "checkov", "SG1", "open_ssh", template="a.json"),
        _cat_finding("high", "checkov", "SG1", "open_ssh", template="b.json"),
    ])
    assert len(deduped) == 2


def test_uncategorised_findings_fall_back_to_message_identity():
    a = _new_finding("high", "checkov", "message A", "SG1")
    b = _new_finding("high", "cfn-lint", "message B", "SG1")
    assert len(_dedupe_findings([a, b])) == 2
    assert len(_dedupe_findings([a, dict(a)])) == 1


def test_dedup_lowers_the_score_it_feeds():
    raw = [
        _cat_finding("critical", "heuristic", "SG1", "open_ssh"),
        _cat_finding("critical", "checkov", "SG1", "open_ssh"),
        _cat_finding("critical", "cfn-lint", "SG1", "open_ssh"),
    ]
    assert _score_findings(raw, cost_delta_usd=0.0, config_violations=0)["total"] == 60
    deduped = _dedupe_findings(raw)
    assert _score_findings(deduped, cost_delta_usd=0.0, config_violations=0)["total"] == 20


# --------------------------------------------------------------------------- #
# Template rules added for the remediated arm of the coverage evaluation
#
# As on the on-premises side, each weakness is expressed through a different
# resource type from the one the evaluation fixture uses, and each is paired
# with the secure form of the same construct.
# --------------------------------------------------------------------------- #
def test_function_url_without_an_authorizer_is_missing_authentication():
    assert _categories_of(
        {"Url": {"Type": "AWS::Lambda::Url", "Properties": {"AuthType": "NONE"}}}
    ) == {"api_auth_none"}


def test_api_method_behind_an_authorizer_is_not_flagged():
    assert (
        _categories_of(
            {
                "Method": {
                    "Type": "AWS::ApiGateway::Method",
                    "Properties": {"HttpMethod": "POST", "AuthorizationType": "COGNITO_USER_POOLS"},
                }
            }
        )
        == set()
    )


def test_cors_preflight_without_an_authorizer_is_not_flagged():
    # OPTIONS carries the CORS preflight, which cannot itself be authenticated.
    assert (
        _categories_of(
            {
                "Preflight": {
                    "Type": "AWS::ApiGateway::Method",
                    "Properties": {"HttpMethod": "OPTIONS", "AuthorizationType": "NONE"},
                }
            }
        )
        == set()
    )


def test_bucket_policy_open_to_every_principal_is_permissive():
    assert _categories_of(
        {
            "BucketPolicy": {
                "Type": "AWS::S3::BucketPolicy",
                "Properties": {
                    "PolicyDocument": {
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": "s3:GetObject",
                                "Resource": "*",
                            }
                        ]
                    }
                },
            }
        }
    ) == {"permissive_resource_policy"}


def test_deny_to_every_principal_is_not_flagged():
    # The deny-unless-TLS statement names a wildcard principal in order to
    # protect the resource, not to open it.
    assert (
        _categories_of(
            {
                "QueuePolicy": {
                    "Type": "AWS::SQS::QueuePolicy",
                    "Properties": {
                        "PolicyDocument": {
                            "Statement": [
                                {
                                    "Effect": "Deny",
                                    "Principal": "*",
                                    "Action": "sqs:*",
                                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                                }
                            ]
                        }
                    },
                }
            }
        )
        == set()
    )


def test_wildcard_principal_scoped_by_a_condition_is_not_flagged():
    assert (
        _categories_of(
            {
                "TopicPolicy": {
                    "Type": "AWS::SNS::TopicPolicy",
                    "Properties": {
                        "PolicyDocument": {
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Principal": {"AWS": "*"},
                                    "Action": "sns:Publish",
                                    "Condition": {
                                        "StringEquals": {"aws:PrincipalOrgID": "o-abc123"}
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        )
        == set()
    )


def test_batch_job_with_added_capabilities_is_unnecessary_privilege():
    assert _categories_of(
        {
            "Job": {
                "Type": "AWS::Batch::JobDefinition",
                "Properties": {
                    "ContainerProperties": {
                        "Image": "example/job:1",
                        "LinuxParameters": {"Capabilities": {"Add": ["SYS_ADMIN"]}},
                    }
                },
            }
        }
    ) == {"unnecessary_privileges"}


def test_task_running_as_a_named_user_is_not_flagged():
    assert (
        _categories_of(
            {
                "Task": {
                    "Type": "AWS::ECS::TaskDefinition",
                    "Properties": {
                        "ContainerDefinitions": [
                            {"Image": "example/app:1", "User": "appsvc", "Privileged": False}
                        ]
                    },
                }
            }
        )
        == set()
    )
