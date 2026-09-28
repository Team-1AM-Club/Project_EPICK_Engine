from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from epick_engine.source_collection.contracts import SourceType
from epick_engine.source_collection.source_onboarding_policy import (
    ApprovedRuleVersion,
    _path_matches,
    _query_is_allowed,
)

RULE_ID = UUID("00000000-0000-4000-8000-00000000a201")
COMPANY_ID = UUID("00000000-0000-4000-8000-00000000a202")


def test_segment_prefix_does_not_match_a_sibling_path() -> None:
    assert _path_matches("/careers", "/careers", mode="SEGMENT_PREFIX")
    assert _path_matches("/careers/engineering", "/careers", mode="SEGMENT_PREFIX")
    assert not _path_matches("/careers-old", "/careers", mode="SEGMENT_PREFIX")


def test_exact_path_does_not_match_a_descendant() -> None:
    assert _path_matches("/jobs", "/jobs", mode="EXACT")
    assert not _path_matches("/jobs/1", "/jobs", mode="EXACT")


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
