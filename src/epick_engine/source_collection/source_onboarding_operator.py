"""Bounded W2 operator actions for approval rules and the one-time v1 import."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, NoReturn
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid5

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from epick_engine.source_collection.contracts import (
    AccessClass,
    OfficialStatus,
    Permission,
    SourceType,
)
from epick_engine.source_collection.persistence import (
    Company,
    Source,
    SourceApprovalRuleHead,
    SourceApprovalRuleRevision,
    SourcePolicyDecision,
    SourceRuntimeApproval,
    create_database_engine,
    create_session_factory,
    database_url_from_environment,
)
from epick_engine.source_collection.service import (
    canonicalize_source_url,
    normalize_company_domain,
)
from epick_engine.source_collection.source_onboarding_policy import (
    ApprovedRuleVersion,
    load_source_runtime_approval,
)
from epick_engine.source_collection.source_runtime_input import (
    RuntimeExecutionLimits,
    RuntimeSourceConfig,
    RuntimeSourceConfigFile,
    parse_runtime_source_config_json,
)

type PathMode = Literal["EXACT", "SEGMENT_PREFIX"]
type PositiveStrictInt = Annotated[int, Field(strict=True, gt=0)]
type NonEmptyStrictStr = Annotated[str, Field(strict=True, min_length=1)]

_MIGRATION_HEAD = "0014_source_onboarding"
_MAX_INPUT_BYTES = 1_048_576
_MAX_PATH_DECODE_PASSES = 5
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_LEGACY_RULE_NAMESPACE = UUID("58edf750-62bb-4c4f-9ad6-d1f704a3eb35")


class SourceOnboardingOperatorError(ValueError):
    """Fixed operator-boundary failure that carries no private input."""


class RuleRevisionConflict(SourceOnboardingOperatorError):
    """A revision is stale, skipped, or reuses a revision with another payload."""


class RuleScopeWidening(SourceOnboardingOperatorError):
    """A later revision attempts to expand or replace its approved scope."""


class LegacyConfigImportConflict(SourceOnboardingOperatorError):
    """Existing durable state conflicts with the one-time legacy import."""


def _path_has_safe_structure(path: str) -> bool:
    decoded = path
    for _ in range(_MAX_PATH_DECODE_PASSES):
        if (
            _INVALID_PERCENT_ESCAPE.search(decoded)
            or "\\" in decoded
            or any(segment in {".", ".."} for segment in decoded.split("/"))
        ):
            return False
        try:
            next_decoded = unquote(decoded, errors="strict")
        except UnicodeDecodeError:
            return False
        if next_decoded == decoded:
            return True
        if next_decoded.count("/") != decoded.count("/"):
            return False
        decoded = next_decoded
    return False


def _parse_source_type(value: object) -> object:
    if isinstance(value, str):
        try:
            return SourceType(value)
        except ValueError:
            raise ValueError("source_type must be an existing SourceType") from None
    return value


def _parse_official_status(value: object) -> object:
    if isinstance(value, str):
        try:
            return OfficialStatus(value)
        except ValueError:
            raise ValueError("official_status must be an existing OfficialStatus") from None
    return value


def _parse_access_class(value: object) -> object:
    if isinstance(value, str):
        try:
            return AccessClass(value)
        except ValueError:
            raise ValueError("access_class must be an existing AccessClass") from None
    return value


def _parse_permission(value: object) -> object:
    if isinstance(value, str):
        try:
            return Permission(value)
        except ValueError:
            raise ValueError("permission must be an existing Permission") from None
    return value


class ApprovedRuleManifest(BaseModel):
    """Strict operator-supplied payload for one immutable approval-rule revision."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["w2.source-approval-rule-manifest.v1"]
    approval_rule_id: UUID
    revision: PositiveStrictInt
    company_id: UUID
    company_official_domain: NonEmptyStrictStr
    company_legal_identifiers: Annotated[tuple[NonEmptyStrictStr, ...], Field(min_length=1)]
    company_identity_evidence_refs: Annotated[tuple[NonEmptyStrictStr, ...], Field(min_length=1)]
    exact_host: NonEmptyStrictStr
    path_mode: PathMode
    path_value: NonEmptyStrictStr
    allowed_query_strings: Annotated[tuple[str, ...], Field(min_length=1)]
    source_type: SourceType
    official_status: OfficialStatus
    access_class: AccessClass
    collection_permission: Permission
    excerpt_storage_permission: Permission
    body_storage_permission: Permission
    redistribution_permission: Permission
    evidence_refs: Annotated[tuple[NonEmptyStrictStr, ...], Field(min_length=1)]
    checked_at: datetime
    policy_version: NonEmptyStrictStr
    robots_permission: Permission
    result_version: PositiveStrictInt
    language: NonEmptyStrictStr | None
    redirect_robots_permissions: tuple[tuple[NonEmptyStrictStr, Permission], ...]
    limits: RuntimeExecutionLimits

    _source_type = field_validator("source_type", mode="before")(_parse_source_type)
    _official_status = field_validator("official_status", mode="before")(_parse_official_status)
    _access_class = field_validator("access_class", mode="before")(_parse_access_class)
    _permissions = field_validator(
        "collection_permission",
        "excerpt_storage_permission",
        "body_storage_permission",
        "redistribution_permission",
        "robots_permission",
        mode="before",
    )(_parse_permission)

    @field_validator("approval_rule_id", "company_id", mode="before")
    @classmethod
    def parse_json_uuid(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                return UUID(value)
            except ValueError:
                raise ValueError("manifest identifier must be a UUID") from None
        return value

    @field_validator("checked_at", mode="before")
    @classmethod
    def parse_json_datetime(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("checked_at must be an ISO datetime") from None
        return value

    @field_validator(
        "company_legal_identifiers",
        "company_identity_evidence_refs",
        "allowed_query_strings",
        "evidence_refs",
        mode="before",
    )
    @classmethod
    def normalize_tuple_fields(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("redirect_robots_permissions", mode="before")
    @classmethod
    def parse_redirect_permissions(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        normalized: list[tuple[object, object]] = []
        for item in value:
            if not isinstance(item, list | tuple) or len(item) != 2:
                return value
            normalized.append((item[0], _parse_permission(item[1])))
        return tuple(normalized)

    @field_validator(
        "company_legal_identifiers",
        "company_identity_evidence_refs",
        "evidence_refs",
        "allowed_query_strings",
    )
    @classmethod
    def require_unique_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("manifest list values must be unique")
        return value

    @field_validator(
        "company_legal_identifiers",
        "company_identity_evidence_refs",
        "evidence_refs",
    )
    @classmethod
    def require_nonblank_identity_and_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("manifest identity and evidence values must be nonblank")
        return value

    @field_validator("company_legal_identifiers")
    @classmethod
    def require_legal_identifier_parts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for identifier in value:
            kind, separator, identifier_value = identifier.partition(":")
            if (
                not separator
                or not kind.strip()
                or kind != kind.strip()
                or not identifier_value.strip()
                or identifier_value != identifier_value.strip()
            ):
                raise ValueError("company legal identifier kind and value must be nonblank")
        return value

    @field_validator("company_official_domain", "exact_host")
    @classmethod
    def require_exact_hostname(cls, value: str) -> str:
        if value != value.strip().lower() or any(mark in value for mark in "*/?#@:"):
            raise ValueError("host scope must be one exact normalized hostname")
        try:
            normalized = normalize_company_domain(value)
        except ValueError:
            raise ValueError("host scope must be one exact normalized hostname") from None
        if normalized != value:
            raise ValueError("host scope must be one exact normalized hostname")
        return value

    @field_validator("path_value")
    @classmethod
    def require_safe_absolute_path(cls, value: str) -> str:
        if not value.startswith("/") or not _path_has_safe_structure(value):
            raise ValueError("path scope must be one safe absolute path")
        return value

    @field_validator("allowed_query_strings")
    @classmethod
    def require_exact_queries(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any("*" in item or item.startswith("?") or "#" in item for item in value):
            raise ValueError("query scope must contain exact raw query forms")
        return value

    @field_validator("checked_at")
    @classmethod
    def require_aware_check_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_bound_scope_and_runtime(self) -> ApprovedRuleManifest:
        if not (
            self.exact_host == self.company_official_domain
            or self.exact_host.endswith("." + self.company_official_domain)
        ):
            raise ValueError("exact host is outside the approved company domain")
        RuntimeSourceConfig.model_validate(
            {
                "policy_revision": 1,
                "robots_permission": self.robots_permission,
                "result_version": self.result_version,
                "language": self.language,
                "redirect_robots_permissions": self.redirect_robots_permissions,
                "limits": self.limits,
            }
        )
        return self


def _rule_payload_from_manifest(manifest: ApprovedRuleManifest) -> tuple[object, ...]:
    return (
        manifest.company_id,
        manifest.company_official_domain,
        manifest.company_legal_identifiers,
        manifest.company_identity_evidence_refs,
        manifest.exact_host,
        manifest.path_mode,
        manifest.path_value,
        manifest.allowed_query_strings,
        manifest.source_type.value,
        manifest.official_status.value,
        manifest.access_class.value,
        manifest.collection_permission.value,
        manifest.excerpt_storage_permission.value,
        manifest.body_storage_permission.value,
        manifest.redistribution_permission.value,
        manifest.evidence_refs,
        manifest.checked_at,
        manifest.policy_version,
        manifest.robots_permission.value,
        manifest.result_version,
        manifest.language,
        tuple((url, permission.value) for url, permission in manifest.redirect_robots_permissions),
        manifest.limits.model_dump(mode="python"),
    )


def _rule_payload_from_row(row: SourceApprovalRuleRevision) -> tuple[object, ...]:
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
    return (
        row.company_id,
        row.company_official_domain,
        tuple(row.company_legal_identifiers),
        tuple(row.company_identity_evidence_refs),
        row.exact_host,
        row.path_mode,
        row.path_value,
        tuple(row.allowed_query_strings),
        row.source_type,
        row.official_status,
        row.access_class,
        row.collection_permission,
        row.excerpt_storage_permission,
        row.body_storage_permission,
        row.redistribution_permission,
        tuple(row.evidence_refs),
        row.checked_at,
        row.policy_version,
        row.robots_permission,
        row.result_version,
        row.language,
        tuple((url, permission.value) for url, permission in runtime.redirect_robots_permissions),
        runtime.limits.model_dump(mode="python"),
    )


def _approved_version(row: SourceApprovalRuleRevision) -> ApprovedRuleVersion:
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


def _path_is_within_revision(
    *, previous_mode: str, previous_path: str, candidate_mode: str, candidate_path: str
) -> bool:
    if previous_mode == "EXACT":
        return candidate_mode == "EXACT" and candidate_path == previous_path
    if previous_mode != "SEGMENT_PREFIX":
        return False
    boundary = previous_path.rstrip("/")
    within = (
        candidate_path.startswith("/")
        if not boundary
        else (candidate_path == boundary or candidate_path.startswith(boundary + "/"))
    )
    return within and candidate_mode in {"EXACT", "SEGMENT_PREFIX"}


def _reject_scope_widening(
    previous: SourceApprovalRuleRevision,
    manifest: ApprovedRuleManifest,
) -> None:
    immutable_binding = (
        previous.company_id == manifest.company_id,
        previous.company_official_domain == manifest.company_official_domain,
        tuple(previous.company_legal_identifiers) == manifest.company_legal_identifiers,
        tuple(previous.company_identity_evidence_refs) == manifest.company_identity_evidence_refs,
        previous.exact_host == manifest.exact_host,
        previous.source_type == manifest.source_type.value,
    )
    if (
        not all(immutable_binding)
        or not _path_is_within_revision(
            previous_mode=previous.path_mode,
            previous_path=previous.path_value,
            candidate_mode=manifest.path_mode,
            candidate_path=manifest.path_value,
        )
        or not set(manifest.allowed_query_strings).issubset(previous.allowed_query_strings)
    ):
        raise RuleScopeWidening("approval-rule revision widens its locked scope")


def _advisory_lock_key(rule_id: UUID) -> int:
    value = rule_id.int & ((1 << 63) - 1)
    return value if value else 1


def append_approved_rule(
    session: Session,
    manifest: ApprovedRuleManifest,
) -> ApprovedRuleVersion:
    """Append the next revision under a transaction lock or reuse an exact replay."""

    if not isinstance(manifest, ApprovedRuleManifest):
        raise TypeError("manifest must be an ApprovedRuleManifest")
    session.execute(
        select(func.pg_advisory_xact_lock(_advisory_lock_key(manifest.approval_rule_id)))
    )
    head = session.scalar(
        select(SourceApprovalRuleHead)
        .where(SourceApprovalRuleHead.approval_rule_id == manifest.approval_rule_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = datetime.now(UTC)
    if head is None:
        if manifest.revision != 1:
            raise RuleRevisionConflict("first approval-rule revision must be one")
        head = SourceApprovalRuleHead(
            approval_rule_id=manifest.approval_rule_id,
            current_revision=1,
            is_active=True,
            updated_at=now,
        )
        session.add(head)
    else:
        existing = session.get(
            SourceApprovalRuleRevision,
            (manifest.approval_rule_id, manifest.revision),
            populate_existing=True,
        )
        if existing is not None:
            if _rule_payload_from_row(existing) != _rule_payload_from_manifest(manifest):
                raise RuleRevisionConflict("approval-rule revision payload conflicts")
            return _approved_version(existing)
        if manifest.revision != head.current_revision + 1:
            raise RuleRevisionConflict("approval-rule revision is not the next revision")
        previous = session.get(
            SourceApprovalRuleRevision,
            (manifest.approval_rule_id, head.current_revision),
            populate_existing=True,
        )
        if previous is None:
            raise RuleRevisionConflict("approval-rule head is inconsistent")
        _reject_scope_widening(previous, manifest)
        head.current_revision = manifest.revision
        head.is_active = True
        head.updated_at = now

    row = SourceApprovalRuleRevision(
        approval_rule_id=manifest.approval_rule_id,
        revision=manifest.revision,
        company_id=manifest.company_id,
        company_official_domain=manifest.company_official_domain,
        company_legal_identifiers=list(manifest.company_legal_identifiers),
        company_identity_evidence_refs=list(manifest.company_identity_evidence_refs),
        exact_host=manifest.exact_host,
        path_mode=manifest.path_mode,
        path_value=manifest.path_value,
        allowed_query_strings=list(manifest.allowed_query_strings),
        source_type=manifest.source_type.value,
        official_status=manifest.official_status.value,
        access_class=manifest.access_class.value,
        collection_permission=manifest.collection_permission.value,
        excerpt_storage_permission=manifest.excerpt_storage_permission.value,
        body_storage_permission=manifest.body_storage_permission.value,
        redistribution_permission=manifest.redistribution_permission.value,
        evidence_refs=list(manifest.evidence_refs),
        checked_at=manifest.checked_at,
        policy_version=manifest.policy_version,
        robots_permission=manifest.robots_permission.value,
        result_version=manifest.result_version,
        language=manifest.language,
        redirect_robots_permissions=[
            [url, permission.value] for url, permission in manifest.redirect_robots_permissions
        ],
        limits=manifest.limits.model_dump(mode="python"),
        created_at=now,
    )
    session.add(row)
    session.flush()
    return _approved_version(row)


@dataclass(frozen=True, slots=True)
class LegacyImportSummary:
    imported: int
    already_imported: int
    disabled_pending_evidence: int


def _company_legal_identifier_refs(company: Company) -> tuple[str, ...] | None:
    refs: set[str] = set()
    for kind, raw in company.legal_identifiers.items():
        if not isinstance(kind, str) or not kind.strip() or kind != kind.strip() or ":" in kind:
            return None
        values = raw if isinstance(raw, list) else [raw]
        if not values:
            return None
        for value in values:
            if not isinstance(value, (str, int)) or isinstance(value, bool):
                return None
            rendered = str(value)
            if not rendered.strip() or rendered != rendered.strip():
                return None
            refs.add(f"{kind}:{rendered}")
    return tuple(sorted(refs)) if refs else None


def _nonempty_strings(values: Sequence[object]) -> bool:
    return bool(values) and all(isinstance(value, str) and bool(value.strip()) for value in values)


def _approved_company_domain(company: Company, host: str) -> str | None:
    try:
        domains = sorted(
            {normalize_company_domain(domain) for domain in company.official_domains},
            key=len,
            reverse=True,
        )
    except (TypeError, ValueError):
        return None
    return next(
        (domain for domain in domains if host == domain or host.endswith("." + domain)), None
    )


def _legacy_manifest(
    *,
    source: Source,
    company: Company,
    policy: SourcePolicyDecision,
    runtime: RuntimeSourceConfig,
) -> ApprovedRuleManifest | None:
    if (
        company.identity_status != "verified"
        or policy.revision != runtime.policy_revision
        or policy.official_status != "verified"
        or policy.access_class != "public"
        or policy.collection_permission != "allowed"
        or runtime.robots_permission is not Permission.ALLOWED
        or not _nonempty_strings(company.identity_evidence)
        or not _nonempty_strings(policy.evidence_refs)
        or not policy.policy_version.strip()
    ):
        return None
    legal_identifiers = _company_legal_identifier_refs(company)
    if not legal_identifiers:
        return None
    try:
        source_type = SourceType(source.source_type)
        canonical_url = canonicalize_source_url(source.canonical_url)
        parts = urlsplit(canonical_url)
    except (TypeError, ValueError):
        return None
    host = parts.hostname
    if canonical_url != source.canonical_url or host is None or parts.port not in (None, 443):
        return None
    official_domain = _approved_company_domain(company, host)
    if official_domain is None:
        return None
    return ApprovedRuleManifest(
        schema_version="w2.source-approval-rule-manifest.v1",
        approval_rule_id=uuid5(_LEGACY_RULE_NAMESPACE, str(source.source_id)),
        revision=1,
        company_id=source.company_id,
        company_official_domain=official_domain,
        company_legal_identifiers=legal_identifiers,
        company_identity_evidence_refs=tuple(company.identity_evidence),
        exact_host=host,
        path_mode="EXACT",
        path_value=parts.path or "/",
        allowed_query_strings=(parts.query,),
        source_type=source_type,
        official_status=OfficialStatus(policy.official_status),
        access_class=AccessClass(policy.access_class),
        collection_permission=Permission(policy.collection_permission),
        excerpt_storage_permission=Permission(policy.excerpt_storage_permission),
        body_storage_permission=Permission(policy.body_storage_permission),
        redistribution_permission=Permission(policy.redistribution_permission),
        evidence_refs=tuple(policy.evidence_refs),
        checked_at=policy.checked_at,
        policy_version=policy.policy_version,
        robots_permission=runtime.robots_permission,
        result_version=runtime.result_version,
        language=runtime.language,
        redirect_robots_permissions=runtime.redirect_robots_permissions,
        limits=runtime.limits,
    )


def import_v1_config(
    session: Session,
    config: RuntimeSourceConfigFile,
) -> LegacyImportSummary:
    """Import only legacy entries already supported by durable W2 approval evidence."""

    if not isinstance(config, RuntimeSourceConfigFile):
        raise TypeError("config must be a RuntimeSourceConfigFile")
    imported = already_imported = disabled = 0
    for source_id, runtime in sorted(config.sources.items(), key=lambda item: str(item[0])):
        source = session.scalar(
            select(Source)
            .where(Source.source_id == source_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if source is None:
            disabled += 1
            continue
        existing = session.get(SourceRuntimeApproval, source_id, populate_existing=True)
        if existing is not None:
            if load_source_runtime_approval(session, source_id) != runtime:
                raise LegacyConfigImportConflict(
                    "existing Source approval conflicts with v1 config"
                )
            already_imported += 1
            continue
        company = session.get(Company, source.company_id, populate_existing=True)
        policy = session.scalar(
            select(SourcePolicyDecision)
            .where(SourcePolicyDecision.source_id == source_id)
            .order_by(SourcePolicyDecision.revision.desc())
            .limit(1)
        )
        if company is None or policy is None:
            disabled += 1
            continue
        manifest = _legacy_manifest(
            source=source,
            company=company,
            policy=policy,
            runtime=runtime,
        )
        if manifest is None:
            disabled += 1
            continue
        rule = append_approved_rule(session, manifest)
        session.add(
            SourceRuntimeApproval(
                source_id=source_id,
                approval_rule_id=rule.approval_rule_id,
                approval_rule_revision=rule.revision,
                policy_revision=runtime.policy_revision,
                robots_permission=runtime.robots_permission.value,
                result_version=runtime.result_version,
                language=runtime.language,
                redirect_robots_permissions=[
                    [url, permission.value]
                    for url, permission in runtime.redirect_robots_permissions
                ],
                limits=runtime.limits.model_dump(mode="python"),
                updated_at=datetime.now(UTC),
            )
        )
        session.flush()
        if load_source_runtime_approval(session, source_id) != runtime:
            raise LegacyConfigImportConflict("imported Source approval failed closed validation")
        imported += 1
    return LegacyImportSummary(
        imported=imported,
        already_imported=already_imported,
        disabled_pending_evidence=disabled,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SourceOnboardingOperatorError("operator input contains duplicate keys")
        result[key] = value
    return result


def _reject_nonfinite_number(_value: str) -> NoReturn:
    raise SourceOnboardingOperatorError("operator input contains a non-finite number")


def _read_bounded(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            raw = stream.read(_MAX_INPUT_BYTES + 1)
    except OSError:
        raise SourceOnboardingOperatorError("operator input is unavailable") from None
    if len(raw) > _MAX_INPUT_BYTES:
        raise SourceOnboardingOperatorError("operator input exceeds the size limit")
    return raw


def _parse_manifest(raw: bytes) -> ApprovedRuleManifest:
    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_number,
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise SourceOnboardingOperatorError("operator manifest is invalid") from None
    return ApprovedRuleManifest.model_validate(parsed)


class _QuietArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> NoReturn:
        raise SourceOnboardingOperatorError("operator arguments are invalid")


def _check_migration_head(session: Session) -> None:
    revisions = tuple(session.scalars(text("SELECT version_num FROM alembic_version")).all())
    if revisions != (_MIGRATION_HEAD,):
        raise SourceOnboardingOperatorError("source onboarding migration is not current")


def main(argv: Sequence[str] | None = None) -> int:
    """Run one bounded action; output contains only fixed status and count fields."""

    parser = _QuietArgumentParser(description="W2 source-onboarding operator")
    parser.add_argument("action", choices=["approve-rule", "import-v1-config"])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    engine = None
    try:
        args = parser.parse_args(argv)
        raw = _read_bounded(args.input)
        engine = create_database_engine(database_url_from_environment())
        sessions = create_session_factory(engine)
        with sessions() as session:
            transaction = session.begin()
            try:
                _check_migration_head(session)
                if args.action == "approve-rule":
                    append_approved_rule(session, _parse_manifest(raw))
                    result: Mapping[str, object] = {
                        "status": "RULE_VALIDATED" if args.dry_run else "RULE_APPROVED"
                    }
                else:
                    summary = import_v1_config(session, parse_runtime_source_config_json(raw))
                    result = {
                        "status": "IMPORT_VALIDATED" if args.dry_run else "IMPORT_COMPLETED",
                        "imported": summary.imported,
                        "already_imported": summary.already_imported,
                        "disabled_pending_evidence": summary.disabled_pending_evidence,
                    }
                if args.dry_run:
                    transaction.rollback()
                else:
                    transaction.commit()
            except Exception:
                if transaction.is_active:
                    transaction.rollback()
                raise
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print('{"status":"SOURCE_ONBOARDING_OPERATOR_FAILED"}')
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
