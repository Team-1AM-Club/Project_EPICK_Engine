"""Fail-closed W2 approval-rule matching and per-Source runtime loading."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal
from urllib.parse import unquote, urlsplit
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from epick_engine.source_collection.contracts import SourceType
from epick_engine.source_collection.persistence import (
    Company,
    Source,
    SourceApprovalRuleHead,
    SourceApprovalRuleRevision,
    SourcePolicyDecision,
    SourceRuntimeApproval,
)
from epick_engine.source_collection.service import (
    canonicalize_source_url,
    normalize_company_domain,
)
from epick_engine.source_collection.source_onboarding_contracts import (
    RegistrationMetadata,
    map_w1_source_type,
)
from epick_engine.source_collection.source_runtime_input import (
    RuntimeSourceConfig,
    SourceRuntimeInputError,
)
from epick_engine.source_collection.w1_transport import W1WireContractError

type PathMode = Literal["EXACT", "SEGMENT_PREFIX"]

_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_MAX_PATH_DECODE_PASSES = 5


@dataclass(frozen=True, slots=True)
class ApprovedRuleVersion:
    """Immutable application snapshot of one append-only approval-rule revision."""

    approval_rule_id: UUID
    revision: int
    company_id: UUID
    company_official_domain: str
    company_legal_identifiers: tuple[str, ...]
    company_identity_evidence_refs: tuple[str, ...]
    exact_host: str
    path_mode: PathMode
    path_value: str
    allowed_query_strings: tuple[str, ...]
    source_type: SourceType
    official_status: str
    access_class: str
    collection_permission: str
    excerpt_storage_permission: str
    body_storage_permission: str
    redistribution_permission: str
    evidence_refs: tuple[str, ...]
    policy_version: str
    robots_permission: str
    result_version: int
    language: str | None
    redirect_robots_permissions: tuple[tuple[str, str], ...]
    limits: Mapping[str, int | float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "limits", MappingProxyType(dict(self.limits)))


@dataclass(frozen=True, slots=True)
class ApprovedRuleMatch:
    rule: ApprovedRuleVersion

    @property
    def approval_rule_id(self) -> UUID:
        return self.rule.approval_rule_id

    @property
    def approval_rule_revision(self) -> int:
        return self.rule.revision


def _path_has_safe_structure(path: str) -> bool:
    decoded = path
    for _ in range(_MAX_PATH_DECODE_PASSES):
        if (
            _INVALID_PERCENT_ESCAPE.search(decoded)
            or "\\" in decoded
            or any(segment in {".", ".."} for segment in decoded.split("/"))
        ):
            return False
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            return True
        if next_decoded.count("/") != decoded.count("/"):
            return False
        decoded = next_decoded
    return False


def _path_matches(candidate: str, approved: str, *, mode: str) -> bool:
    if not _path_has_safe_structure(candidate) or not _path_has_safe_structure(approved):
        return False
    if mode == "EXACT":
        return candidate == approved
    if mode != "SEGMENT_PREFIX":
        return False
    boundary = approved.rstrip("/")
    if not boundary:
        return candidate.startswith("/")
    return candidate == boundary or candidate.startswith(boundary + "/")


def _query_is_allowed(candidate: str, approved: tuple[str, ...]) -> bool:
    return candidate in approved


def _company_legal_identifier_refs(company: Company) -> frozenset[str]:
    refs: set[str] = set()
    for kind, raw in company.legal_identifiers.items():
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                refs.add(f"{kind}:{value}")
    return frozenset(refs)


def _version(row: SourceApprovalRuleRevision) -> ApprovedRuleVersion:
    runtime = RuntimeSourceConfig.model_validate(
        {
            "policy_revision": 1,
            "robots_permission": row.robots_permission,
            "result_version": row.result_version,
            "language": row.language,
            "redirect_robots_permissions": row.redirect_robots_permissions,
            "limits": row.limits,
        }
    )
    return ApprovedRuleVersion(
        approval_rule_id=row.approval_rule_id,
        revision=row.revision,
        company_id=row.company_id,
        company_official_domain=row.company_official_domain,
        company_legal_identifiers=tuple(row.company_legal_identifiers),
        company_identity_evidence_refs=tuple(row.company_identity_evidence_refs),
        exact_host=row.exact_host,
        path_mode=row.path_mode,  # type: ignore[arg-type]
        path_value=row.path_value,
        allowed_query_strings=tuple(row.allowed_query_strings),
        source_type=SourceType(row.source_type),
        official_status=row.official_status,
        access_class=row.access_class,
        collection_permission=row.collection_permission,
        excerpt_storage_permission=row.excerpt_storage_permission,
        body_storage_permission=row.body_storage_permission,
        redistribution_permission=row.redistribution_permission,
        evidence_refs=tuple(row.evidence_refs),
        policy_version=row.policy_version,
        robots_permission=row.robots_permission,
        result_version=row.result_version,
        language=row.language,
        redirect_robots_permissions=tuple(
            (url, permission.value) for url, permission in runtime.redirect_robots_permissions
        ),
        limits=runtime.limits.model_dump(mode="python"),
    )


def match_approved_rule(
    session: Session,
    metadata: RegistrationMetadata,
) -> ApprovedRuleMatch | None:
    """Lock and match one current rule; ambiguous or widened scopes deny."""

    if not isinstance(metadata, RegistrationMetadata) or metadata.status != "AVAILABLE":
        return None
    assert metadata.canonical_url is not None
    assert metadata.company_official_domain is not None
    assert metadata.company_legal_identifiers is not None
    assert metadata.company_identity_evidence_refs is not None
    assert metadata.w1_source_type is not None
    try:
        canonical = canonicalize_source_url(metadata.canonical_url)
        parts = urlsplit(canonical)
        if parts.port not in (None, 443):
            return None
        source_type = map_w1_source_type(metadata.w1_source_type)
        official_domain = normalize_company_domain(metadata.company_official_domain)
    except (ValueError, W1WireContractError):
        return None
    host = parts.hostname
    if host is None:
        return None

    statement = (
        select(SourceApprovalRuleRevision)
        .join(
            SourceApprovalRuleHead,
            and_(
                SourceApprovalRuleHead.approval_rule_id
                == SourceApprovalRuleRevision.approval_rule_id,
                SourceApprovalRuleHead.current_revision == SourceApprovalRuleRevision.revision,
            ),
        )
        .where(
            SourceApprovalRuleHead.is_active.is_(True),
            SourceApprovalRuleRevision.company_id == metadata.company_id,
            SourceApprovalRuleRevision.source_type == source_type.value,
            SourceApprovalRuleRevision.exact_host == host,
        )
        .with_for_update(of=SourceApprovalRuleHead)
    )
    matched: list[SourceApprovalRuleRevision] = []
    for row in session.scalars(statement):
        if (
            normalize_company_domain(row.company_official_domain) == official_domain
            and frozenset(row.company_legal_identifiers)
            == frozenset(metadata.company_legal_identifiers)
            and frozenset(row.company_identity_evidence_refs)
            == frozenset(metadata.company_identity_evidence_refs)
            and _path_matches(parts.path or "/", row.path_value, mode=row.path_mode)
            and _query_is_allowed(parts.query, tuple(row.allowed_query_strings))
        ):
            matched.append(row)
    if len(matched) != 1:
        return None
    try:
        return ApprovedRuleMatch(rule=_version(matched[0]))
    except (ValidationError, ValueError, TypeError):
        return None


def load_source_runtime_approval(
    session: Session,
    source_id: UUID,
) -> RuntimeSourceConfig | None:
    """Load only a current approval exactly bound to its Source, policy, and rule."""

    source = session.scalar(
        select(Source)
        .where(Source.source_id == source_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if source is None:
        return None
    row = session.get(SourceRuntimeApproval, source_id)
    if row is None:
        return None
    try:
        runtime = RuntimeSourceConfig.model_validate(
            {
                "policy_revision": row.policy_revision,
                "robots_permission": row.robots_permission,
                "result_version": row.result_version,
                "language": row.language,
                "redirect_robots_permissions": row.redirect_robots_permissions,
                "limits": row.limits,
            }
        )
    except (ValidationError, ValueError, TypeError):
        raise SourceRuntimeInputError("stored source runtime approval is invalid") from None

    company = session.get(Company, source.company_id)
    if company is None or company.identity_status != "verified":
        return None

    rule = session.scalar(
        select(SourceApprovalRuleRevision)
        .join(
            SourceApprovalRuleHead,
            and_(
                SourceApprovalRuleHead.approval_rule_id
                == SourceApprovalRuleRevision.approval_rule_id,
                SourceApprovalRuleHead.current_revision == SourceApprovalRuleRevision.revision,
            ),
        )
        .where(
            SourceApprovalRuleRevision.approval_rule_id == row.approval_rule_id,
            SourceApprovalRuleRevision.revision == row.approval_rule_revision,
            SourceApprovalRuleHead.is_active.is_(True),
        )
        .with_for_update(of=SourceApprovalRuleHead)
    )
    if rule is None or source.company_id != rule.company_id:
        return None

    try:
        official_domains = frozenset(
            normalize_company_domain(domain) for domain in company.official_domains
        )
        rule_official_domain = normalize_company_domain(rule.company_official_domain)
        canonical_url = canonicalize_source_url(source.canonical_url)
        parts = urlsplit(canonical_url)
        rule_runtime = RuntimeSourceConfig.model_validate(
            {
                "policy_revision": row.policy_revision,
                "robots_permission": rule.robots_permission,
                "result_version": rule.result_version,
                "language": rule.language,
                "redirect_robots_permissions": rule.redirect_robots_permissions,
                "limits": rule.limits,
            }
        )
    except (ValidationError, ValueError, TypeError):
        return None
    if (
        canonical_url != source.canonical_url
        or parts.port not in (None, 443)
        or parts.hostname != rule.exact_host
        or source.source_type != rule.source_type
        or rule_official_domain not in official_domains
        or frozenset(rule.company_legal_identifiers) != _company_legal_identifier_refs(company)
        or frozenset(rule.company_identity_evidence_refs) != frozenset(company.identity_evidence)
        or not _path_matches(parts.path or "/", rule.path_value, mode=rule.path_mode)
        or not _query_is_allowed(parts.query, tuple(rule.allowed_query_strings))
        or runtime != rule_runtime
    ):
        return None

    policy = session.scalar(
        select(SourcePolicyDecision)
        .where(SourcePolicyDecision.source_id == source_id)
        .order_by(SourcePolicyDecision.revision.desc())
        .limit(1)
    )
    if policy is None or policy.revision != row.policy_revision:
        return None
    if any(
        (
            policy.official_status != rule.official_status,
            policy.access_class != rule.access_class,
            policy.collection_permission != rule.collection_permission,
            policy.excerpt_storage_permission != rule.excerpt_storage_permission,
            policy.body_storage_permission != rule.body_storage_permission,
            policy.redistribution_permission != rule.redistribution_permission,
            tuple(policy.evidence_refs) != tuple(rule.evidence_refs),
            policy.checked_at != rule.checked_at,
            policy.policy_version != rule.policy_version,
        )
    ):
        return None
    return runtime
