"""Authenticated private-write scope validation and owner-first locking."""

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
    """Raised when authenticated private-write scope cannot pass its fence."""


class ScopeUnclassified(PrivateScopeRejected):
    """Raised when a private row has no authenticated account or Project scope."""


@dataclass(frozen=True, slots=True)
class PrivateWriteScope:
    """Immutable scope proof constructed from a trusted W1 authority decision."""

    owner_user_id: UUID
    owner_deletion_epoch: int
    kind: Literal["ACCOUNT", "PROJECT"]
    project_id: UUID | None
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
        if self.kind not in {"ACCOUNT", "PROJECT"}:
            raise PrivateScopeRejected("private scope kind must be explicit")
        if self.kind == "ACCOUNT" and self.project_id is not None:
            raise PrivateScopeRejected("ACCOUNT scope cannot bind a Project")
        if self.kind == "PROJECT" and not isinstance(self.project_id, UUID):
            raise PrivateScopeRejected("PROJECT scope requires a Project UUID")
        if not isinstance(self.authority_ref, str) or not self.authority_ref.strip():
            raise PrivateScopeRejected("authority reference must be nonempty")
        if self.command_id is not None and not isinstance(self.command_id, UUID):
            raise PrivateScopeRejected("command binding must be a UUID")
        if self.job_id is not None and not isinstance(self.job_id, UUID):
            raise PrivateScopeRejected("job binding must be a UUID")

    @classmethod
    def from_scope(
        cls,
        *,
        owner_user_id: UUID,
        owner_deletion_epoch: int,
        scope: PrivateDeletionScope,
        authority_ref: str,
        command_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> PrivateWriteScope:
        """Bind a validated v2 scope to one trusted W1 write authority."""

        if not isinstance(scope, PrivateDeletionScope):
            raise PrivateScopeRejected("scope must be a validated v2 private deletion scope")
        return cls(
            owner_user_id=owner_user_id,
            owner_deletion_epoch=owner_deletion_epoch,
            kind=scope.kind,
            project_id=scope.project_id,
            authority_ref=authority_ref,
            command_id=command_id,
            job_id=job_id,
        )

    def assert_bound_to(
        self,
        *,
        owner_user_id: UUID,
        owner_deletion_epoch: int,
        command_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> None:
        """Reject a proof reused for a different owner, epoch, command, or job."""

        if self.owner_user_id != owner_user_id:
            raise PrivateScopeRejected("private scope owner binding does not match")
        if self.owner_deletion_epoch != owner_deletion_epoch:
            raise PrivateScopeRejected("private scope epoch binding does not match")
        if command_id is not None and self.command_id != command_id:
            raise PrivateScopeRejected("private scope command binding does not match")
        if job_id is not None and self.job_id != job_id:
            raise PrivateScopeRejected("private scope job binding does not match")


def lock_private_write_scope(session: Session, proof: PrivateWriteScope) -> None:
    """Lock the owner fence first and reject deleted or non-current write scope."""

    if not isinstance(proof, PrivateWriteScope):
        raise PrivateScopeRejected("an authenticated private write scope is required")

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
