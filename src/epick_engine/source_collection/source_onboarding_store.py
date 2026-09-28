"""Atomic persistence boundary for W1 direct Source registration ACKs."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from epick_engine.source_collection.contracts import SourceType
from epick_engine.source_collection.persistence import (
    Company,
    PersistenceConflict,
    Source,
    SourceApprovalRuleRevision,
    SourcePolicyDecision,
    SourceRegistrationAckOutbox,
    SourceRegistrationReceipt,
    SourceRuntimeApproval,
    append_or_reuse_source_policy_decision,
)
from epick_engine.source_collection.private_scope import (
    PrivateScopeRejected,
    PrivateWriteScope,
    lock_private_write_scope,
)
from epick_engine.source_collection.service import (
    canonicalize_source_url,
    normalize_company_domain,
)
from epick_engine.source_collection.source_onboarding_contracts import (
    RegistrationAck,
    RegistrationMetadata,
    map_w1_source_type,
    registration_digest,
)
from epick_engine.source_collection.source_onboarding_policy import (
    ApprovedRuleVersion,
    match_approved_rule,
)
from epick_engine.source_collection.w1_transport import (
    W1DirectSourceRegistrationDispatch,
    W1WireContractError,
)

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
type AckStatus = Literal["READY", "HELD", "REJECTED"]
type AckReason = Literal[
    "APPROVED",
    "POLICY_RULE_MISSING",
    "COMPANY_UNVERIFIED",
    "URL_NORMALIZATION_MISMATCH",
    "UNSUPPORTED_SOURCE_TYPE",
    "SOURCE_ID_CONFLICT",
    "CANONICAL_URL_CONFLICT",
    "EXPLICIT_POLICY_DENIAL",
]


def _require_aware_now(now: datetime) -> None:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("registration timestamp must be timezone-aware")


def _assert_dispatch_binding(
    dispatch: W1DirectSourceRegistrationDispatch,
    metadata: RegistrationMetadata,
    private_scope: PrivateWriteScope,
) -> None:
    if not isinstance(dispatch, W1DirectSourceRegistrationDispatch):
        raise PersistenceConflict("registration dispatch type does not match")
    if not isinstance(metadata, RegistrationMetadata) or metadata.status != "AVAILABLE":
        raise PersistenceConflict("registration metadata is not AVAILABLE")
    command = dispatch.payload
    pin = dispatch.direct_source_registration_pin
    if (
        metadata.command_id != command.command_id
        or metadata.execution_fence != dispatch.lookup_request.execution_fence
        or metadata.owner_deletion_epoch != command.owner_deletion_epoch
        or metadata.company_id != command.company_id
        or metadata.source_id != command.source_id
        or metadata.registration_input_version != pin.registration_input_version
    ):
        raise PersistenceConflict("registration metadata binding does not match dispatch")
    private_scope.assert_bound_to(
        owner_user_id=command.authenticated_owner_ref,
        owner_deletion_epoch=command.owner_deletion_epoch,
        command_id=command.command_id,
        job_id=command.job_id,
    )
    if private_scope.kind == "ACCOUNT":
        if command.project_ref is not None:
            raise PrivateScopeRejected("registration Project binding does not match scope")
    elif command.project_ref != str(private_scope.project_id):
        raise PrivateScopeRejected("registration Project binding does not match scope")


def _receipt_ack(row: SourceRegistrationReceipt) -> RegistrationAck:
    return RegistrationAck(
        schema_version="w2.private.source-registration-ack.v1",
        command_id=row.command_id,
        job_id=row.job_id,
        authenticated_owner_ref=row.authenticated_owner_ref,
        project_ref=row.project_ref,
        company_id=row.company_id,
        source_id=row.source_id,
        execution_fence=row.execution_fence,
        owner_deletion_epoch=row.owner_deletion_epoch,
        registration_digest=row.registration_digest,
        status=row.status,  # type: ignore[arg-type]
        reason_code=row.reason_code,  # type: ignore[arg-type]
        policy_revision=row.policy_revision,
        approval_rule_id=row.approval_rule_id,
        approval_rule_revision=row.approval_rule_revision,
    )


def _load_registration_replay(
    session: Session,
    *,
    dispatch: W1DirectSourceRegistrationDispatch,
    digest: str,
) -> RegistrationAck | None:
    command = dispatch.payload
    receipt = session.scalar(
        select(SourceRegistrationReceipt)
        .where(SourceRegistrationReceipt.command_id == command.command_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if receipt is None:
        return None
    immutable = {
        "job_id": command.job_id,
        "authenticated_owner_ref": command.authenticated_owner_ref,
        "project_ref": command.project_ref,
        "company_id": command.company_id,
        "source_id": command.source_id,
        "execution_fence": dispatch.lookup_request.execution_fence,
        "owner_deletion_epoch": command.owner_deletion_epoch,
        "registration_digest": digest,
    }
    if any(getattr(receipt, field) != expected for field, expected in immutable.items()):
        raise PersistenceConflict("registration command has different immutable payload")
    ack = _receipt_ack(receipt)
    outbox = session.scalar(
        select(SourceRegistrationAckOutbox)
        .where(SourceRegistrationAckOutbox.command_id == command.command_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if outbox is None or outbox.payload != ack.model_dump(mode="json"):
        raise PersistenceConflict("registration ACK outbox is missing or inconsistent")
    return ack


def _ack(
    dispatch: W1DirectSourceRegistrationDispatch,
    *,
    digest: str,
    status: AckStatus,
    reason_code: AckReason,
    policy_revision: int | None = None,
    approval_rule_id: UUID | None = None,
    approval_rule_revision: int | None = None,
) -> RegistrationAck:
    command = dispatch.payload
    return RegistrationAck(
        schema_version="w2.private.source-registration-ack.v1",
        command_id=command.command_id,
        job_id=command.job_id,
        authenticated_owner_ref=command.authenticated_owner_ref,
        project_ref=command.project_ref,
        company_id=command.company_id,
        source_id=command.source_id,
        execution_fence=dispatch.lookup_request.execution_fence,
        owner_deletion_epoch=command.owner_deletion_epoch,
        registration_digest=digest,
        status=status,
        reason_code=reason_code,
        policy_revision=policy_revision,
        approval_rule_id=approval_rule_id,
        approval_rule_revision=approval_rule_revision,
    )


def _record_ack(
    session: Session,
    ack: RegistrationAck,
    *,
    now: datetime,
) -> RegistrationAck:
    session.add(
        SourceRegistrationReceipt(
            command_id=ack.command_id,
            job_id=ack.job_id,
            authenticated_owner_ref=ack.authenticated_owner_ref,
            project_ref=ack.project_ref,
            company_id=ack.company_id,
            source_id=ack.source_id,
            execution_fence=ack.execution_fence,
            owner_deletion_epoch=ack.owner_deletion_epoch,
            registration_digest=ack.registration_digest,
            status=ack.status,
            reason_code=ack.reason_code,
            policy_revision=ack.policy_revision,
            approval_rule_id=ack.approval_rule_id,
            approval_rule_revision=ack.approval_rule_revision,
            created_at=now,
        )
    )
    session.flush()
    session.add(
        SourceRegistrationAckOutbox(
            ack_message_id=uuid4(),
            command_id=ack.command_id,
            payload=ack.model_dump(mode="json"),
            delivery_state="PENDING",
            created_at=now,
            delivered_at=None,
            ack_confirmed_at=None,
        )
    )
    session.flush()
    return ack


def _company_identifier_refs(company: Company) -> frozenset[str] | None:
    refs: set[str] = set()
    stored: object = company.legal_identifiers
    if not isinstance(stored, Mapping):
        return None
    for kind, raw in stored.items():
        if not isinstance(kind, str) or not kind:
            return None
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if not isinstance(value, str) or not value:
                return None
            refs.add(f"{kind}:{value}")
    return frozenset(refs)


def _structured_company_identifiers(refs: Sequence[str]) -> dict[str, str | list[str]] | None:
    values_by_kind: dict[str, list[str]] = {}
    for ref in refs:
        if not isinstance(ref, str) or ":" not in ref:
            return None
        kind, value = ref.split(":", 1)
        if not kind or not value or kind != kind.strip() or value != value.strip():
            return None
        values_by_kind.setdefault(kind, []).append(value)
    result: dict[str, str | list[str]] = {}
    for kind, values in values_by_kind.items():
        unique = sorted(set(values))
        result[kind] = unique[0] if len(unique) == 1 else unique
    return result


def _company_matches_metadata(
    company: Company,
    metadata: RegistrationMetadata,
    *,
    legal_name: str,
) -> bool:
    assert metadata.company_official_domain is not None
    assert metadata.company_legal_identifiers is not None
    assert metadata.company_identity_evidence_refs is not None
    try:
        official_domain = normalize_company_domain(metadata.company_official_domain)
        stored_domains = frozenset(
            normalize_company_domain(domain) for domain in company.official_domains
        )
    except (TypeError, ValueError):
        return False
    return (
        company.identity_status == "verified"
        and company.legal_name == legal_name
        and official_domain in stored_domains
        and _company_identifier_refs(company) == frozenset(metadata.company_legal_identifiers)
        and frozenset(company.identity_evidence)
        == frozenset(metadata.company_identity_evidence_refs)
    )


def _rule_is_denied(rule: ApprovedRuleVersion) -> bool:
    return (
        rule.official_status == "rejected"
        or rule.access_class in {"restricted", "unavailable"}
        or rule.collection_permission == "denied"
        or rule.excerpt_storage_permission == "denied"
    )


def _rule_is_unverified(rule: ApprovedRuleVersion) -> bool:
    return (
        rule.official_status != "verified"
        or rule.access_class != "public"
        or rule.collection_permission != "allowed"
        or rule.excerpt_storage_permission != "allowed"
    )


def _rule_row(session: Session, rule: ApprovedRuleVersion) -> SourceApprovalRuleRevision:
    row = session.get(SourceApprovalRuleRevision, (rule.approval_rule_id, rule.revision))
    if row is None:
        raise PersistenceConflict("matched approval rule disappeared")
    return row


def _resolve_source_conflict(
    session: Session,
    *,
    source_id: UUID,
    company_id: UUID,
    canonical_url: str,
    source_type: SourceType,
) -> tuple[Source | None, AckReason | None]:
    source = session.scalar(
        select(Source)
        .where(Source.source_id == source_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if source is not None and (
        source.company_id != company_id
        or source.canonical_url != canonical_url
        or source.source_type != source_type.value
    ):
        return source, "SOURCE_ID_CONFLICT"
    alias = session.scalar(
        select(Source)
        .where(
            Source.company_id == company_id,
            Source.canonical_url == canonical_url,
            Source.source_id != source_id,
        )
        .with_for_update()
    )
    if alias is not None:
        return source, "CANONICAL_URL_CONFLICT"
    return source, None


def _lock_public_registration_identities(
    session: Session,
    *,
    company_id: UUID,
    source_id: UUID,
    canonical_url: str,
) -> None:
    """Serialize absent Company/Source identities before relying on row locks."""

    if session.get_bind().dialect.name != "postgresql":
        raise PersistenceConflict("Source registration storage requires PostgreSQL")
    namespace = b"epick.w2.source-onboarding.v1\0"
    identities = (
        b"company\0" + company_id.bytes,
        b"source\0" + source_id.bytes,
        b"company-url\0" + company_id.bytes + b"\0" + canonical_url.encode("utf-8"),
    )
    keys = sorted(
        {
            int.from_bytes(
                hashlib.sha256(namespace + identity).digest()[:8],
                "big",
                signed=True,
            )
            for identity in identities
        }
    )
    for key in keys:
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _policy_from_rule(
    *,
    source_id: UUID,
    row: SourceApprovalRuleRevision,
) -> SourcePolicyDecision:
    return SourcePolicyDecision(
        policy_decision_id=uuid4(),
        source_id=source_id,
        revision=1,
        official_status=row.official_status,
        access_class=row.access_class,
        collection_permission=row.collection_permission,
        excerpt_storage_permission=row.excerpt_storage_permission,
        body_storage_permission=row.body_storage_permission,
        redistribution_permission=row.redistribution_permission,
        evidence_refs=list(row.evidence_refs),
        checked_at=row.checked_at,
        policy_version=row.policy_version,
    )


def _upsert_runtime_approval(
    session: Session,
    *,
    source_id: UUID,
    row: SourceApprovalRuleRevision,
    policy_revision: int,
    now: datetime,
) -> None:
    values = {
        "approval_rule_id": row.approval_rule_id,
        "approval_rule_revision": row.revision,
        "policy_revision": policy_revision,
        "robots_permission": row.robots_permission,
        "result_version": row.result_version,
        "language": row.language,
        "redirect_robots_permissions": row.redirect_robots_permissions,
        "limits": row.limits,
        "updated_at": now,
    }
    approval = session.get(SourceRuntimeApproval, source_id)
    if approval is None:
        session.add(SourceRuntimeApproval(source_id=source_id, **values))
        return
    for field, value in values.items():
        setattr(approval, field, value)


def register_direct_source(
    session: Session,
    dispatch: W1DirectSourceRegistrationDispatch,
    metadata: RegistrationMetadata,
    private_scope: PrivateWriteScope,
    now: datetime,
) -> RegistrationAck:
    """Persist one registration decision and ACK outbox in the caller's transaction."""

    _require_aware_now(now)
    _assert_dispatch_binding(dispatch, metadata, private_scope)
    lock_private_write_scope(session, private_scope)
    digest = registration_digest(metadata)
    replay = _load_registration_replay(session, dispatch=dispatch, digest=digest)
    if replay is not None:
        return replay

    assert metadata.canonical_url is not None
    try:
        canonical_url = canonicalize_source_url(metadata.canonical_url)
    except ValueError:
        canonical_url = ""
    if canonical_url != metadata.canonical_url:
        return _record_ack(
            session,
            _ack(
                dispatch,
                digest=digest,
                status="HELD",
                reason_code="URL_NORMALIZATION_MISMATCH",
            ),
            now=now,
        )

    assert metadata.w1_source_type is not None
    try:
        source_type = map_w1_source_type(metadata.w1_source_type)
    except W1WireContractError:
        return _record_ack(
            session,
            _ack(
                dispatch,
                digest=digest,
                status="HELD",
                reason_code="UNSUPPORTED_SOURCE_TYPE",
            ),
            now=now,
        )

    matched = match_approved_rule(session, metadata)
    if matched is None:
        return _record_ack(
            session,
            _ack(
                dispatch,
                digest=digest,
                status="HELD",
                reason_code="POLICY_RULE_MISSING",
            ),
            now=now,
        )

    _lock_public_registration_identities(
        session,
        company_id=metadata.company_id,
        source_id=metadata.source_id,
        canonical_url=canonical_url,
    )
    source, conflict = _resolve_source_conflict(
        session,
        source_id=metadata.source_id,
        company_id=metadata.company_id,
        canonical_url=canonical_url,
        source_type=source_type,
    )
    if conflict is not None:
        return _record_ack(
            session,
            _ack(
                dispatch,
                digest=digest,
                status="REJECTED",
                reason_code=conflict,
            ),
            now=now,
        )
    if _rule_is_denied(matched.rule):
        return _record_ack(
            session,
            _ack(
                dispatch,
                digest=digest,
                status="REJECTED",
                reason_code="EXPLICIT_POLICY_DENIAL",
            ),
            now=now,
        )
    if _rule_is_unverified(matched.rule):
        return _record_ack(
            session,
            _ack(
                dispatch,
                digest=digest,
                status="HELD",
                reason_code="COMPANY_UNVERIFIED",
            ),
            now=now,
        )

    legal_name = metadata.company_legal_name
    assert metadata.company_official_domain is not None
    assert metadata.company_legal_identifiers is not None
    assert metadata.company_identity_evidence_refs is not None
    identifiers = _structured_company_identifiers(metadata.company_legal_identifiers)
    if legal_name is None or not legal_name.strip() or identifiers is None:
        return _record_ack(
            session,
            _ack(
                dispatch,
                digest=digest,
                status="HELD",
                reason_code="COMPANY_UNVERIFIED",
            ),
            now=now,
        )

    company = session.scalar(
        select(Company)
        .where(Company.company_id == metadata.company_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if company is None:
        company = Company(
            company_id=metadata.company_id,
            legal_name=legal_name,
            aliases=[],
            official_domains=[normalize_company_domain(metadata.company_official_domain)],
            legal_identifiers=identifiers,
            identity_status="verified",
            identity_evidence=sorted(set(metadata.company_identity_evidence_refs)),
        )
        session.add(company)
        session.flush()
    elif not _company_matches_metadata(company, metadata, legal_name=legal_name):
        return _record_ack(
            session,
            _ack(
                dispatch,
                digest=digest,
                status="HELD",
                reason_code="COMPANY_UNVERIFIED",
            ),
            now=now,
        )

    if source is None:
        source = Source(
            source_id=metadata.source_id,
            company_id=metadata.company_id,
            source_type=source_type.value,
            canonical_url=canonical_url,
            title=None,
            pointer_update_mode="FINALIZE_GATE",
        )
        session.add(source)
        session.flush()

    row = _rule_row(session, matched.rule)
    policy = append_or_reuse_source_policy_decision(
        session,
        _policy_from_rule(source_id=source.source_id, row=row),
    )
    _upsert_runtime_approval(
        session,
        source_id=source.source_id,
        row=row,
        policy_revision=policy.revision,
        now=now,
    )
    return _record_ack(
        session,
        _ack(
            dispatch,
            digest=digest,
            status="READY",
            reason_code="APPROVED",
            policy_revision=policy.revision,
            approval_rule_id=row.approval_rule_id,
            approval_rule_revision=row.revision,
        ),
        now=now,
    )


def confirm_registration_ack(
    session: Session,
    command_id: UUID,
    digest: str,
    now: datetime,
) -> None:
    """Confirm W1's exact ACK acceptance in a separately committed transaction."""

    _require_aware_now(now)
    if not isinstance(command_id, UUID):
        raise PersistenceConflict("registration ACK command ID is invalid")
    if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
        raise PersistenceConflict("registration ACK digest is invalid")
    receipt = session.scalar(
        select(SourceRegistrationReceipt)
        .where(SourceRegistrationReceipt.command_id == command_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    outbox = session.scalar(
        select(SourceRegistrationAckOutbox)
        .where(SourceRegistrationAckOutbox.command_id == command_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if receipt is None or outbox is None:
        raise PersistenceConflict("registration ACK state was not found")
    if receipt.registration_digest != digest:
        raise PersistenceConflict("registration ACK digest does not match receipt")
    ack = _receipt_ack(receipt)
    if outbox.payload != ack.model_dump(mode="json"):
        raise PersistenceConflict("registration ACK outbox is inconsistent")
    if outbox.delivery_state == "DELIVERED":
        if outbox.delivered_at is None or outbox.ack_confirmed_at is None:
            raise PersistenceConflict("registration ACK confirmation is inconsistent")
        return
    if (
        outbox.delivery_state != "PENDING"
        or outbox.delivered_at is not None
        or outbox.ack_confirmed_at is not None
    ):
        raise PersistenceConflict("registration ACK delivery state is inconsistent")
    outbox.delivery_state = "DELIVERED"
    outbox.delivered_at = now
    outbox.ack_confirmed_at = now
    session.flush()
