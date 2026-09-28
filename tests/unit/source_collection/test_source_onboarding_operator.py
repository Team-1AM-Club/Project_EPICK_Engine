from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from epick_engine.source_collection.contracts import SourceType
from epick_engine.source_collection.source_onboarding_operator import ApprovedRuleManifest

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
RULE_ID = UUID("00000000-0000-4000-8000-00000000c301")
COMPANY_ID = UUID("00000000-0000-4000-8000-00000000c302")


def _limits() -> dict[str, int | float]:
    return {
        "site_concurrency": 1,
        "global_concurrency": 2,
        "source_ttl_seconds": 300,
        "max_response_bytes": 1_048_576,
        "max_decompressed_bytes": 2_097_152,
        "connect_timeout_seconds": 3.0,
        "read_timeout_seconds": 5.0,
        "max_redirects": 2,
        "general_retry_limit": 0,
        "retention_days": 7,
    }


def _manifest_payload() -> dict[str, object]:
    return {
        "schema_version": "w2.source-approval-rule-manifest.v1",
        "approval_rule_id": RULE_ID,
        "revision": 1,
        "company_id": COMPANY_ID,
        "company_official_domain": "company.test",
        "company_legal_identifiers": ["corp:synthetic-legal-id"],
        "company_identity_evidence_refs": ["company-evidence:synthetic"],
        "exact_host": "careers.company.test",
        "path_mode": "EXACT",
        "path_value": "/jobs",
        "allowed_query_strings": ["team=engineering"],
        "source_type": SourceType.JOB_POSTING.value,
        "official_status": "verified",
        "access_class": "public",
        "collection_permission": "allowed",
        "excerpt_storage_permission": "allowed",
        "body_storage_permission": "denied",
        "redistribution_permission": "denied",
        "evidence_refs": ["policy-evidence:synthetic"],
        "checked_at": NOW,
        "policy_version": "policy-v1",
        "robots_permission": "allowed",
        "result_version": 1,
        "language": "ko",
        "redirect_robots_permissions": [],
        "limits": _limits(),
    }


@pytest.mark.parametrize(
    "field",
    [
        "company_legal_identifiers",
        "company_identity_evidence_refs",
        "evidence_refs",
    ],
)
def test_manifest_rejects_absent_operator_evidence(field: str) -> None:
    payload = _manifest_payload()
    payload[field] = []

    with pytest.raises(ValidationError):
        ApprovedRuleManifest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("exact_host", "*.company.test"),
        ("exact_host", "careers.company.test/path"),
        ("path_value", "/jobs/../private"),
        ("path_value", "/jobs/%zz"),
        ("allowed_query_strings", ["*"]),
        ("allowed_query_strings", ["team=engineering", "team=engineering"]),
    ],
)
def test_manifest_rejects_non_exact_or_ambiguous_scope(field: str, value: object) -> None:
    payload = _manifest_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        ApprovedRuleManifest.model_validate(payload)


def test_manifest_accepts_complete_exact_synthetic_scope() -> None:
    manifest = ApprovedRuleManifest.model_validate(_manifest_payload())

    assert manifest.exact_host == "careers.company.test"
    assert manifest.path_value == "/jobs"
    assert manifest.allowed_query_strings == ("team=engineering",)
