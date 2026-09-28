from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from epick_engine.source_collection.contracts import SourceType
from epick_engine.source_collection.source_onboarding_contracts import RegistrationMetadata
from epick_engine.source_collection.source_onboarding_policy import (
    ApprovedRuleVersion,
    _path_matches,
    _query_is_allowed,
    load_source_runtime_approval,
    match_approved_rule,
)

RULE_ID = UUID("00000000-0000-4000-8000-00000000a201")
COMPANY_ID = UUID("00000000-0000-4000-8000-00000000a202")
SOURCE_ID = UUID("00000000-0000-4000-8000-00000000a203")
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def _metadata() -> RegistrationMetadata:
    return RegistrationMetadata(
        schema_version="w1.private.w2-source-registration-lookup.v1",
        status="AVAILABLE",
        command_id=uuid4(),
        execution_fence=1,
        owner_deletion_epoch=0,
        company_id=COMPANY_ID,
        source_id=SOURCE_ID,
        canonical_url="https://careers.company.test/jobs",
        w1_source_type="JOB_POSTING",
        registration_input_version="input-v1",
        company_official_domain="company.test",
        company_legal_name="Synthetic Company",
        company_legal_identifiers=["corp:sub:x"],
        company_identity_evidence_refs=["evidence:company"],
    )


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


def test_segment_prefix_does_not_match_a_sibling_path() -> None:
    assert _path_matches("/careers", "/careers", mode="SEGMENT_PREFIX")
    assert _path_matches("/careers/engineering", "/careers", mode="SEGMENT_PREFIX")
    assert not _path_matches("/careers-old", "/careers", mode="SEGMENT_PREFIX")


def test_exact_path_does_not_match_a_descendant() -> None:
    assert _path_matches("/jobs", "/jobs", mode="EXACT")
    assert not _path_matches("/jobs/1", "/jobs", mode="EXACT")


@pytest.mark.parametrize(
    "candidate",
    [
        "/jobs/../admin",
        "/jobs/%2e%2e/admin",
        "/jobs%2fadmin",
        "/jobs/%2fadmin",
        "/jobs/%252e%252e/admin",
    ],
    ids=[
        "dot-segment",
        "encoded-dot-segment",
        "encoded-separator",
        "encoded-descendant-separator",
        "double-encoded-dot",
    ],
)
def test_segment_prefix_denies_ambiguous_or_encoded_path_structure(candidate: str) -> None:
    assert not _path_matches(candidate, "/jobs", mode="SEGMENT_PREFIX")


def test_query_is_denied_until_the_exact_form_is_approved() -> None:
    assert not _query_is_allowed("", ())
    assert _query_is_allowed("", ("",))
    assert _query_is_allowed("team=platform", ("team=platform",))
    assert not _query_is_allowed("team=platform&page=2", ("team=platform",))


def test_approved_rule_version_is_an_immutable_value() -> None:
    version = ApprovedRuleVersion(
        approval_rule_id=RULE_ID,
        revision=1,
        company_id=COMPANY_ID,
        company_official_domain="company.test",
        company_legal_identifiers=("corp:company",),
        company_identity_evidence_refs=("evidence:company",),
        exact_host="careers.company.test",
        path_mode="SEGMENT_PREFIX",
        path_value="/jobs",
        allowed_query_strings=("",),
        source_type=SourceType.JOB_POSTING,
        official_status="verified",
        access_class="public",
        collection_permission="allowed",
        excerpt_storage_permission="allowed",
        body_storage_permission="denied",
        redistribution_permission="denied",
        evidence_refs=("policy:evidence",),
        policy_version="policy-v1",
        robots_permission="allowed",
        result_version=1,
        language="ko",
        redirect_robots_permissions=(),
        limits={
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
        },
    )

    with pytest.raises(FrozenInstanceError):
        version.revision = 2  # type: ignore[misc]


def test_rule_match_denies_malformed_stored_company_domain() -> None:
    session = Mock(spec=Session)
    session.scalars.return_value = [
        SimpleNamespace(company_official_domain="bad domain"),
    ]

    assert match_approved_rule(session, _metadata()) is None
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_runtime_approval_denies_ambiguous_stored_company_identifier_kind() -> None:
    limits = _limits()
    source = SimpleNamespace(
        source_id=SOURCE_ID,
        company_id=COMPANY_ID,
        canonical_url="https://careers.company.test/jobs",
        source_type=SourceType.JOB_POSTING.value,
    )
    approval = SimpleNamespace(
        approval_rule_id=RULE_ID,
        approval_rule_revision=1,
        policy_revision=1,
        robots_permission="allowed",
        result_version=1,
        language="ko",
        redirect_robots_permissions=[],
        limits=limits,
    )
    company = SimpleNamespace(
        identity_status="verified",
        official_domains=["company.test"],
        legal_identifiers={"corp:sub": "x"},
        identity_evidence=["evidence:company"],
    )
    rule = SimpleNamespace(
        approval_rule_id=RULE_ID,
        revision=1,
        company_id=COMPANY_ID,
        company_official_domain="company.test",
        company_legal_identifiers=["corp:sub:x"],
        company_identity_evidence_refs=["evidence:company"],
        exact_host="careers.company.test",
        path_mode="SEGMENT_PREFIX",
        path_value="/jobs",
        allowed_query_strings=[""],
        source_type=SourceType.JOB_POSTING.value,
        official_status="verified",
        access_class="public",
        collection_permission="allowed",
        excerpt_storage_permission="allowed",
        body_storage_permission="denied",
        redistribution_permission="denied",
        evidence_refs=["policy:evidence"],
        checked_at=NOW,
        policy_version="policy-v1",
        robots_permission="allowed",
        result_version=1,
        language="ko",
        redirect_robots_permissions=[],
        limits=limits,
    )
    policy = SimpleNamespace(
        revision=1,
        official_status="verified",
        access_class="public",
        collection_permission="allowed",
        excerpt_storage_permission="allowed",
        body_storage_permission="denied",
        redistribution_permission="denied",
        evidence_refs=["policy:evidence"],
        checked_at=NOW,
        policy_version="policy-v1",
    )
    session = Mock(spec=Session)
    session.scalar.side_effect = [source, rule, policy]
    session.get.side_effect = [approval, company]

    assert load_source_runtime_approval(session, SOURCE_ID) is None
    session.add.assert_not_called()
    session.flush.assert_not_called()
