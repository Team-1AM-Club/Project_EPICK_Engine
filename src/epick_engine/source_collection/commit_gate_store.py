"""W2_UNADOPTED_PROPOSAL_QUEUE_DISCONNECTED private PostgreSQL boundary.

The caller owns the transaction. Savepoints isolate storage conflicts; releasing
a savepoint is not a database commit and no relay/worker is registered here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Mapped, Session, mapped_column

from epick_engine.source_collection.commit_gate_contracts import (
    CommitGateAckProposal,
    CommitGateCommand,
    StagedResultProposal,
    build_commit_gate_ack,
    build_staged_result,
    parse_commit_gate_command,
)
from epick_engine.source_collection.contracts import CollectionCommand, CollectionResult
from epick_engine.source_collection.persistence import Base
from epick_engine.source_collection.w1_transport import (
    W1WireContractError,
    _parse_wire,
    _revalidate_model,
)


class PrivateCommitStage(Base):
    __tablename__ = "private_commit_stages"
    __table_args__ = (
        UniqueConstraint("operation_id", name="uq_private_commit_stages_operation"),
        CheckConstraint(
            "state IN ('STAGED', 'PREPARED', 'FINALIZED', 'ABORTED', 'PURGED')",
            name="valid_state",
        ),
        CheckConstraint(
            "(state IN ('ABORTED', 'PURGED') AND result_payload IS NULL) OR "
            "(state IN ('STAGED', 'PREPARED', 'FINALIZED') AND result_payload IS NOT NULL)",
            name="payload_matches_state",
        ),
    )

    command_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    owner_ref: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    # Wire integers have no upper bound: canonical decimal text avoids bigint overflow.
    execution_fence: Mapped[str] = mapped_column(Text, nullable=False)
    owner_deletion_epoch: Mapped[str] = mapped_column(Text, nullable=False)
    result_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    operation_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    operation_revision: Mapped[str] = mapped_column(Text, nullable=False)
    max_purge_epoch: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )


class PrivateStagedOutbox(Base):
    __tablename__ = "private_staged_outbox"
    __table_args__ = (UniqueConstraint("command_id", name="uq_private_staged_outbox_command"),)

    message_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    command_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("private_commit_stages.command_id"), nullable=False
    )
    wire_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)


class PrivateCommitGateAck(Base):
    __tablename__ = "private_commit_gate_acks"

    message_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    command_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("private_commit_stages.command_id"), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PrivateCommitGateReceipt(Base):
    __tablename__ = "private_commit_gate_receipts"

    operation_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    operation_revision: Mapped[str] = mapped_column(Text, primary_key=True)
    command_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("private_commit_stages.command_id"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ack_message_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("private_commit_gate_acks.message_id"),
        nullable=False,
    )


class PrivateCommitGateInbox(Base):
    __tablename__ = "private_commit_gate_inbox"

    message_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    command_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("private_commit_stages.command_id"), nullable=False
    )
    wire_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ack_message_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("private_commit_gate_acks.message_id"),
        nullable=False,
    )


class CommitGateRejected(ValueError):
    """Safe storage rejection without embedding private input in diagnostics."""


def _hash(raw: dict[str, Any]) -> str:
    encoded = json.dumps(
        raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _lock_command(session: Session, command_id: UUID) -> None:
    if session.get_bind().dialect.name != "postgresql":
        raise CommitGateRejected("private commit-gate storage requires PostgreSQL")
    # Namespace + UUID, not owner, prevents alternate-owner claims bypassing the lock.
    # Lock before looking for a row; FOR UPDATE alone misses the absent-row race.
    key = int.from_bytes(
        hashlib.sha256(b"epick.w2.private.commit-gate.v1\0" + command_id.bytes).digest()[:8],
        "big",
        signed=True,
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


@contextmanager
def _storage_transaction(session: Session, command_id: UUID) -> Iterator[None]:
    try:
        with session.begin_nested():
            _lock_command(session, command_id)
            yield
    except IntegrityError:
        # Unique delivery/operation collisions cannot leak driver parameters or
        # partially change the command, even if the caller catches and commits.
        raise CommitGateRejected("private commit-gate identity conflict") from None
    except StatementError:
        # JSONB data errors and DBAPI statement failures can include private SQL
        # parameters. Roll back the savepoint before exposing a fixed rejection.
        raise CommitGateRejected("private commit-gate data storage rejected") from None


def _flush_private_storage(session: Session) -> None:
    try:
        session.flush()
    except (TypeError, ValueError):
        # psycopg JSON serializers can raise these directly, without a DBAPI
        # wrapper. Catch only the flush boundary, not unrelated store logic.
        raise CommitGateRejected("private commit-gate data serialization rejected") from None


def _bound_row(
    row: PrivateCommitStage, *, owner: UUID, job: UUID, fence: str, epoch: int, digest: str
) -> None:
    if (
        row.owner_ref != owner
        or row.job_id != job
        or row.execution_fence != fence
        or row.owner_deletion_epoch != str(epoch)
        or row.result_digest != digest
    ):
        raise CommitGateRejected("private commit-gate binding mismatch")


def _stored_ack(session: Session, message_id: UUID) -> CommitGateAckProposal:
    row = session.get(PrivateCommitGateAck, message_id)
    if row is None:
        raise CommitGateRejected("private commit-gate ACK unavailable")
    try:
        return _parse_wire(row.payload, CommitGateAckProposal, label="persisted W2 gate ACK")
    except W1WireContractError:
        raise CommitGateRejected("invalid persisted private commit-gate ACK") from None


def stage_private_result(
    session: Session,
    command: CollectionCommand,
    result: CollectionResult,
    *,
    message_id: UUID,
    occurred_at: datetime,
) -> StagedResultProposal:
    """Store an invisible result and submission together, without committing."""
    try:
        proposal = build_staged_result(
            command, result, message_id=message_id, occurred_at=occurred_at
        )
    except W1WireContractError:
        raise CommitGateRejected("invalid private staged-result context") from None
    raw = proposal.model_dump(mode="json")
    wire_hash = _hash(raw)
    command = proposal.command
    with _storage_transaction(session, command.command_id):
        row = session.get(PrivateCommitStage, command.command_id, populate_existing=True)
        delivery = session.get(PrivateStagedOutbox, message_id)
        if delivery is not None and (
            delivery.command_id != command.command_id or delivery.wire_hash != wire_hash
        ):
            raise CommitGateRejected("private staged-result message conflict")
        if row is not None:
            _bound_row(
                row,
                owner=command.authenticated_owner_ref,
                job=command.job_id,
                fence=command.execution_fence,
                epoch=command.owner_deletion_epoch,
                digest=proposal.result_digest,
            )
            if row.state in {"ABORTED", "PURGED"}:
                raise CommitGateRejected("private staged-result command is terminal")
            existing = session.scalar(
                select(PrivateStagedOutbox).where(
                    PrivateStagedOutbox.command_id == command.command_id
                )
            )
            if existing is None or existing.payload is None:
                raise CommitGateRejected("private staged-result submission unavailable")
            try:
                return _parse_wire(
                    existing.payload, StagedResultProposal, label="persisted W2 stage"
                )
            except W1WireContractError:
                raise CommitGateRejected("invalid persisted private staged-result") from None
        session.add(
            PrivateCommitStage(
                command_id=command.command_id,
                owner_ref=command.authenticated_owner_ref,
                job_id=command.job_id,
                execution_fence=command.execution_fence,
                owner_deletion_epoch=str(command.owner_deletion_epoch),
                result_digest=proposal.result_digest,
                operation_id=None,
                operation_revision="0",
                max_purge_epoch=str(command.owner_deletion_epoch),
                state="STAGED",
                result_payload=proposal.result.model_dump(mode="json"),
            )
        )
        _flush_private_storage(session)
        session.add(
            PrivateStagedOutbox(
                message_id=message_id,
                command_id=command.command_id,
                wire_hash=wire_hash,
                payload=raw,
            )
        )
        _flush_private_storage(session)
    return proposal


def apply_commit_gate(
    session: Session,
    gate_command: CommitGateCommand,
    *,
    ack_message_id: UUID,
    occurred_at: datetime,
) -> CommitGateAckProposal:
    """Apply binding/state/revision and persist the exact ACK in the same transaction."""
    try:
        gate = (
            _revalidate_model(gate_command, CommitGateCommand, label="private gate command")
            if isinstance(gate_command, CommitGateCommand)
            else parse_commit_gate_command(gate_command)
        )
        ack = build_commit_gate_ack(
            gate, outcome="APPLIED", message_id=ack_message_id, occurred_at=occurred_at
        )
    except W1WireContractError:
        raise CommitGateRejected("invalid private commit-gate context") from None
    raw = gate.model_dump(mode="json")
    wire_hash = _hash(raw)
    content_hash = _hash({k: v for k, v in raw.items() if k not in {"message_id", "issued_at"}})
    with _storage_transaction(session, gate.command_id):
        inbox = session.get(PrivateCommitGateInbox, gate.message_id)
        if inbox is not None:
            if inbox.wire_hash != wire_hash or inbox.command_id != gate.command_id:
                raise CommitGateRejected("private commit-gate message conflict")
            return _stored_ack(session, inbox.ack_message_id)
        row = session.get(PrivateCommitStage, gate.command_id, populate_existing=True)
        if row is not None:
            _bound_row(
                row,
                owner=gate.authenticated_owner_ref,
                job=gate.job_id,
                fence=str(gate.execution_fence),
                epoch=gate.owner_deletion_epoch,
                digest=gate.result_digest,
            )
            if row.operation_id is not None and row.operation_id != gate.operation_id:
                raise CommitGateRejected("private commit-gate operation conflict")
        receipt = session.get(
            PrivateCommitGateReceipt, (gate.operation_id, str(gate.operation_revision))
        )
        if receipt is not None:
            if receipt.command_id != gate.command_id or receipt.content_hash != content_hash:
                raise CommitGateRejected("private commit-gate revision conflict")
            stored = _stored_ack(session, receipt.ack_message_id)
            session.add(
                PrivateCommitGateInbox(
                    message_id=gate.message_id,
                    command_id=gate.command_id,
                    wire_hash=wire_hash,
                    ack_message_id=receipt.ack_message_id,
                )
            )
            _flush_private_storage(session)
            return stored
        if row is None:
            if gate.action not in {"ABORT", "PURGE"}:
                raise CommitGateRejected("private commit-gate staged result unavailable")
            row = PrivateCommitStage(
                command_id=gate.command_id,
                owner_ref=gate.authenticated_owner_ref,
                job_id=gate.job_id,
                execution_fence=str(gate.execution_fence),
                owner_deletion_epoch=str(gate.owner_deletion_epoch),
                result_digest=gate.result_digest,
                operation_id=gate.operation_id,
                operation_revision="0",
                max_purge_epoch=str(gate.owner_deletion_epoch),
                state="ABORTED",
                result_payload=None,
            )
            session.add(row)
        elif gate.operation_revision <= int(row.operation_revision):
            raise CommitGateRejected("private commit-gate stale revision")
        if gate.action == "PREPARE":
            if row.state != "STAGED":
                raise CommitGateRejected("private commit-gate PREPARE requires STAGED")
            row.state = "PREPARED"
        elif gate.action == "FINALIZE":
            if row.state != "PREPARED":
                raise CommitGateRejected("private commit-gate FINALIZE requires PREPARED")
            row.state = "FINALIZED"
        elif gate.action == "ABORT":
            if row.state in {"FINALIZED", "PURGED"} or (
                row.state == "ABORTED" and int(row.operation_revision) != 0
            ):
                raise CommitGateRejected("private commit-gate ABORT requires nonterminal result")
            row.state = "ABORTED"
            row.result_payload = None
        else:
            epoch = gate.purge_owner_deletion_epoch
            if epoch is None or epoch <= int(row.max_purge_epoch):
                raise CommitGateRejected("private commit-gate PURGE requires newer deletion epoch")
            row.max_purge_epoch = str(epoch)
            row.state = "PURGED"
            row.result_payload = None
        row.operation_id = gate.operation_id
        row.operation_revision = str(gate.operation_revision)
        if gate.action in {"ABORT", "PURGE"}:
            staged = session.scalar(
                select(PrivateStagedOutbox).where(PrivateStagedOutbox.command_id == gate.command_id)
            )
            if staged is not None:
                staged.payload = None
        _flush_private_storage(session)
        session.add(
            PrivateCommitGateAck(
                message_id=ack.message_id,
                command_id=gate.command_id,
                payload=ack.model_dump(mode="json"),
            )
        )
        _flush_private_storage(session)
        session.add(
            PrivateCommitGateReceipt(
                operation_id=gate.operation_id,
                operation_revision=str(gate.operation_revision),
                command_id=gate.command_id,
                content_hash=content_hash,
                ack_message_id=ack.message_id,
            )
        )
        session.add(
            PrivateCommitGateInbox(
                message_id=gate.message_id,
                command_id=gate.command_id,
                wire_hash=wire_hash,
                ack_message_id=ack.message_id,
            )
        )
        _flush_private_storage(session)
    return ack


def read_finalized_result(
    session: Session, *, owner_ref: UUID, command_id: UUID
) -> CollectionResult | None:
    """Read only finalized results for the caller-authenticated owner reference."""
    if not isinstance(owner_ref, UUID) or not isinstance(command_id, UUID):
        raise CommitGateRejected("invalid private finalized-result identity")
    row = session.scalar(
        select(PrivateCommitStage)
        .where(
            PrivateCommitStage.command_id == command_id,
            PrivateCommitStage.owner_ref == owner_ref,
            PrivateCommitStage.state == "FINALIZED",
        )
        .execution_options(populate_existing=True)
    )
    if row is None:
        return None
    try:
        return _parse_wire(
            row.result_payload, CollectionResult, label="persisted W2 private result"
        )
    except W1WireContractError:
        raise CommitGateRejected("invalid persisted private finalized result") from None
