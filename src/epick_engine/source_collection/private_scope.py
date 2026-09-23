"""Private-write authority values, scope validation, and owner-first locking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from epick_engine.source_collection.persistence import (
    PrivateDeletionOwnerState,
    PrivateDeletionProjectTombstone,
)
from epick_engine.source_collection.private_deletion_v2 import PrivateDeletionScope

SIGNED_64_MAX = 9_223_372_036_854_775_807


class PrivateScopeRejected(RuntimeError):
    """Raised when a private-write authority value cannot pass its fence."""


class ScopeUnclassified(PrivateScopeRejected):
    """Raised when a private row has no authenticated account or Project scope."""


@dataclass(frozen=True, slots=True)
class PrivateWriteAuthorityDecision:
    """Shape-validated value supplied by a trusted authentication adapter.

    Constructing this value does not authenticate W1. Task 3 owns the production
    adapter/provider that may create it after authenticating the authority decision.
    """

    owner_user_id: UUID
    owner_deletion_epoch: int
    scope: PrivateDeletionScope
    authority_ref: str
    command_id: UUID | None = None
    job_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.owner_user_id, UUID):
            raise PrivateScopeRejected("owner binding must be a UUID")
        if (
            isinstance(self.owner_deletion_epoch, bool)
            or not isinstance(self.owner_deletion_epoch, int)
            or not 0 <= self.owner_deletion_epoch <= SIGNED_64_MAX
        ):
            raise PrivateScopeRejected("owner deletion epoch is outside signed 64-bit range")
        if not isinstance(self.scope, PrivateDeletionScope):
            raise PrivateScopeRejected("authority decision requires a validated v2 scope")
        if not isinstance(self.authority_ref, str) or not self.authority_ref.strip():
            raise PrivateScopeRejected("authority reference must be nonempty")
        if self.command_id is not None and not isinstance(self.command_id, UUID):
            raise PrivateScopeRejected("command binding must be a UUID")
        if self.job_id is not None and not isinstance(self.job_id, UUID):
            raise PrivateScopeRejected("job binding must be a UUID")


@dataclass(frozen=True, slots=True)
class PrivateWriteScope:
    """Write-fence proof built from one upstream authority decision value."""

    decision: PrivateWriteAuthorityDecision

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PrivateWriteAuthorityDecision):
            raise PrivateScopeRejected("a private write authority decision is required")

    @property
    def owner_user_id(self) -> UUID:
        return self.decision.owner_user_id

    @property
    def owner_deletion_epoch(self) -> int:
        return self.decision.owner_deletion_epoch

    @property
    def kind(self) -> Literal["ACCOUNT", "PROJECT"]:
        return self.decision.scope.kind

    @property
    def project_id(self) -> UUID | None:
        return self.decision.scope.project_id

    @property
    def authority_ref(self) -> str:
        return self.decision.authority_ref

    @property
    def command_id(self) -> UUID | None:
        return self.decision.command_id

    @property
    def job_id(self) -> UUID | None:
        return self.decision.job_id

    def assert_bound_to(
        self,
        *,
        owner_user_id: UUID,
        owner_deletion_epoch: int,
        command_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> None:
        """Reject a proof reused for a different owner, epoch, command, or job."""

        if not isinstance(owner_user_id, UUID):
            raise PrivateScopeRejected("target owner binding must be a UUID")
        if (
            isinstance(owner_deletion_epoch, bool)
            or not isinstance(owner_deletion_epoch, int)
            or not 0 <= owner_deletion_epoch <= SIGNED_64_MAX
        ):
            raise PrivateScopeRejected("target owner deletion epoch is outside signed 64-bit range")
        if command_id is not None and not isinstance(command_id, UUID):
            raise PrivateScopeRejected("target command binding must be a UUID")
        if job_id is not None and not isinstance(job_id, UUID):
            raise PrivateScopeRejected("target job binding must be a UUID")
        if self.owner_user_id != owner_user_id:
            raise PrivateScopeRejected("private scope owner binding does not match")
        if self.owner_deletion_epoch != owner_deletion_epoch:
            raise PrivateScopeRejected("private scope epoch binding does not match")
        if self.command_id != command_id:
            raise PrivateScopeRejected("private scope command binding does not match")
        if self.job_id != job_id:
            raise PrivateScopeRejected("private scope job binding does not match")


def lock_private_write_scope(session: Session, proof: PrivateWriteScope) -> None:
    """Lock the owner fence first and reject deleted or non-current write scope."""

    if not isinstance(proof, PrivateWriteScope):
        raise PrivateScopeRejected("a private write scope from an authority decision is required")

    session.execute(
        postgresql_insert(PrivateDeletionOwnerState)
        .values(
            owner_user_id=proof.owner_user_id,
            latest_epoch=0,
            account_deleted=False,
        )
        .on_conflict_do_nothing(index_elements=["owner_user_id"])
    )
    owner_state = session.scalar(
        select(PrivateDeletionOwnerState)
        .where(PrivateDeletionOwnerState.owner_user_id == proof.owner_user_id)
        .with_for_update()
    )
    if owner_state is None:
        raise RuntimeError("private deletion owner state row was not found")
    if owner_state.account_deleted:
        raise PrivateScopeRejected("private write rejected by account tombstone")
    if proof.owner_deletion_epoch != owner_state.latest_epoch:
        raise PrivateScopeRejected("private write proof does not bind the current epoch")

    if proof.kind == "PROJECT":
        tombstone = session.scalar(
            select(PrivateDeletionProjectTombstone)
            .where(
                PrivateDeletionProjectTombstone.owner_user_id == proof.owner_user_id,
                PrivateDeletionProjectTombstone.project_id == proof.project_id,
            )
            .with_for_update()
        )
        if tombstone is not None:
            raise PrivateScopeRejected("private write rejected by project tombstone")
