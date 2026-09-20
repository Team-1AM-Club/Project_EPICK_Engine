"""Durable reservation and short-lived claim storage for W2 collection runtime."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from epick_engine.source_collection.commit_gate_store import (
    PrivateCommitStage,
    lock_private_command,
)
from epick_engine.source_collection.persistence import (
    CollectionRuntimeAttempt,
    Source,
    SourcePolicyDecision,
)
from epick_engine.source_collection.w1_transport import (
    W1CommandDispatch,
    W1DirectSourceRegistrationDispatch,
    W1Dispatch,
    W1WireContractError,
    _revalidate_model,
)


class CollectionRuntimeConflict(RuntimeError):
    """The same private command identity was reused with different immutable input."""


class CollectionRuntimeBusy(RuntimeError):
    """Another unexpired DB-clock claim owns this reserved command."""


type SessionFactory = Callable[[], Session]
type UUIDFactory = Callable[[], UUID]


def dispatch_digest(dispatch: W1Dispatch) -> str:
    payload = dispatch.model_dump(mode="json")
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validated_dispatch(dispatch: W1Dispatch) -> W1Dispatch:
    try:
        if isinstance(dispatch, W1CommandDispatch):
            return _revalidate_model(dispatch, W1CommandDispatch, label="W1 command dispatch")
        if isinstance(dispatch, W1DirectSourceRegistrationDispatch):
            return _revalidate_model(
                dispatch,
                W1DirectSourceRegistrationDispatch,
                label="W1 direct registration dispatch",
            )
    except W1WireContractError:
        pass
    raise CollectionRuntimeConflict("invalid collection runtime dispatch") from None


def _assert_bound_attempt(
    attempt: CollectionRuntimeAttempt,
    dispatch: W1Dispatch,
    digest: str,
) -> None:
    command = dispatch.payload
    if (
        attempt.dispatch_digest != digest
        or attempt.owner_ref != command.authenticated_owner_ref
        or attempt.job_id != command.job_id
        or attempt.source_id != command.source_id
        or attempt.company_id != command.company_id
    ):
        raise CollectionRuntimeConflict("collection runtime dispatch binding conflict")


def load_bound_collection_attempt(
    session: Session,
    dispatch: W1Dispatch,
) -> CollectionRuntimeAttempt | None:
    """Load an immutable dispatch-bound attempt without consulting current policy."""

    validated = _validated_dispatch(dispatch)
    digest = dispatch_digest(validated)
    attempt = session.get(
        CollectionRuntimeAttempt,
        validated.payload.command_id,
        populate_existing=True,
    )
    if attempt is not None:
        _assert_bound_attempt(attempt, validated, digest)
    return attempt


def reserve_collection_attempt(
    session: Session,
    dispatch: W1Dispatch,
    effective_policy_revision: int,
    now: datetime,
    uuid_factory: UUIDFactory,
) -> CollectionRuntimeAttempt:
    """Reserve one Source-local observation order in the caller-owned transaction."""

    validated = _validated_dispatch(dispatch)
    if (
        not isinstance(effective_policy_revision, int)
        or isinstance(effective_policy_revision, bool)
        or effective_policy_revision <= 0
    ):
        raise CollectionRuntimeConflict("effective policy revision must be positive")
    command = validated.payload
    digest = dispatch_digest(validated)

    lock_private_command(session, command.command_id)
    terminal_stage = session.scalar(
        select(PrivateCommitStage)
        .where(
            PrivateCommitStage.command_id == command.command_id,
            PrivateCommitStage.state.in_(("ABORTED", "PURGED")),
        )
        .execution_options(populate_existing=True)
    )
    if terminal_stage is not None:
        raise CollectionRuntimeConflict("collection runtime command is terminal")

    attempt = session.scalar(
        select(CollectionRuntimeAttempt)
        .where(CollectionRuntimeAttempt.command_id == command.command_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is not None:
        _assert_bound_attempt(attempt, validated, digest)
        if attempt.effective_policy_revision != effective_policy_revision:
            raise CollectionRuntimeConflict("collection runtime policy binding conflict")
        if attempt.state != "RESERVED":
            raise CollectionRuntimeConflict("collection runtime attempt is terminal")

    source = session.scalar(
        select(Source)
        .where(Source.source_id == command.source_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if source is None or source.company_id != command.company_id:
        raise CollectionRuntimeConflict("collection runtime source binding conflict")

    current_policy_revision = session.scalar(
        select(func.max(SourcePolicyDecision.revision)).where(
            SourcePolicyDecision.source_id == command.source_id
        )
    )
    if current_policy_revision != effective_policy_revision:
        raise CollectionRuntimeConflict("collection runtime policy revision is stale")

    if attempt is not None:
        return attempt

    source.pointer_update_mode = "FINALIZE_GATE"
    source.next_observation_order += 1
    attempt = CollectionRuntimeAttempt(
        command_id=command.command_id,
        attempt_id=uuid_factory(),
        dispatch_digest=digest,
        owner_ref=command.authenticated_owner_ref,
        job_id=command.job_id,
        source_id=command.source_id,
        company_id=command.company_id,
        observation_order=source.next_observation_order,
        effective_policy_revision=effective_policy_revision,
        state="RESERVED",
        claim_token=None,
        claim_expires_at=None,
        observation_id=None,
        source_version_id=None,
        created_at=now,
        updated_at=now,
    )
    session.add(attempt)
    session.flush()
    return attempt


def _validate_claim_identity(command_id: UUID, claim_token: UUID) -> None:
    if not isinstance(command_id, UUID) or not isinstance(claim_token, UUID):
        raise CollectionRuntimeConflict("invalid collection runtime claim identity")


def _validate_lease_seconds(lease_seconds: int) -> None:
    if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds <= 0:
        raise CollectionRuntimeConflict("collection runtime lease must be positive")


def _lock_reserved_attempt(session: Session, command_id: UUID) -> CollectionRuntimeAttempt:
    lock_private_command(session, command_id)
    attempt = session.scalar(
        select(CollectionRuntimeAttempt)
        .where(CollectionRuntimeAttempt.command_id == command_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is None or attempt.state != "RESERVED":
        raise CollectionRuntimeConflict("collection runtime attempt is not reserved")
    return attempt


def _database_now(session: Session) -> datetime:
    value = session.scalar(select(func.clock_timestamp()))
    if not isinstance(value, datetime):
        raise CollectionRuntimeConflict("collection runtime database clock unavailable")
    return value


def _detach_after_flush(
    session: Session,
    attempt: CollectionRuntimeAttempt,
) -> CollectionRuntimeAttempt:
    session.flush()
    session.expunge(attempt)
    return attempt


def claim_collection_attempt(
    session_factory: SessionFactory,
    command_id: UUID,
    *,
    claim_token: UUID,
    lease_seconds: int,
) -> CollectionRuntimeAttempt:
    """Claim a RESERVED attempt in one self-contained DB-clock transaction."""

    _validate_claim_identity(command_id, claim_token)
    _validate_lease_seconds(lease_seconds)
    with session_factory() as session, session.begin():
        attempt = _lock_reserved_attempt(session, command_id)
        database_now = _database_now(session)
        if (
            attempt.claim_token is not None
            and attempt.claim_token != claim_token
            and attempt.claim_expires_at is not None
            and attempt.claim_expires_at > database_now
        ):
            raise CollectionRuntimeBusy("collection runtime attempt is already claimed")
        attempt.claim_token = claim_token
        attempt.claim_expires_at = database_now + timedelta(seconds=lease_seconds)
        attempt.updated_at = database_now
        return _detach_after_flush(session, attempt)


def renew_collection_claim(
    session_factory: SessionFactory,
    command_id: UUID,
    *,
    claim_token: UUID,
    lease_seconds: int,
) -> CollectionRuntimeAttempt:
    """Renew only the caller's active RESERVED claim using the database clock."""

    _validate_claim_identity(command_id, claim_token)
    _validate_lease_seconds(lease_seconds)
    with session_factory() as session, session.begin():
        attempt = _lock_reserved_attempt(session, command_id)
        database_now = _database_now(session)
        if (
            attempt.claim_token != claim_token
            or attempt.claim_expires_at is None
            or attempt.claim_expires_at <= database_now
        ):
            raise CollectionRuntimeConflict("collection runtime claim token is not active")
        attempt.claim_expires_at = database_now + timedelta(seconds=lease_seconds)
        attempt.updated_at = database_now
        return _detach_after_flush(session, attempt)


def release_collection_claim(
    session_factory: SessionFactory,
    command_id: UUID,
    *,
    claim_token: UUID,
) -> CollectionRuntimeAttempt:
    """Release only the caller's active RESERVED claim in one root transaction."""

    _validate_claim_identity(command_id, claim_token)
    with session_factory() as session, session.begin():
        attempt = _lock_reserved_attempt(session, command_id)
        database_now = _database_now(session)
        if (
            attempt.claim_token != claim_token
            or attempt.claim_expires_at is None
            or attempt.claim_expires_at <= database_now
        ):
            raise CollectionRuntimeConflict("collection runtime claim token is not active")
        attempt.claim_token = None
        attempt.claim_expires_at = None
        attempt.updated_at = database_now
        return _detach_after_flush(session, attempt)
