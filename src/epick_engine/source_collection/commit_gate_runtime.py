"""Queue-independent runtime for the W2 private commit gate."""

from __future__ import annotations

import hmac
import json
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from epick_engine.source_collection.commit_gate_contracts import (
    CommitGateAckProposal,
    CommitGateCommand,
    parse_commit_gate_command,
)
from epick_engine.source_collection.commit_gate_store import (
    PrivateCommitGateAck,
    PrivateCommitStage,
    PrivateStagedOutbox,
    _lock_command,
    apply_commit_gate,
)
from epick_engine.source_collection.private_deletion_v2 import PrivateDeletionScope
from epick_engine.source_collection.private_scope import (
    PrivateWriteAuthorityDecision,
    PrivateWriteScope,
    lock_private_write_scope,
)
from epick_engine.source_collection.w1_transport import W1WireContractError

# W1's adopted command outbox bound is 16 KiB. Outbound payloads retain the
# earlier SQS-safe 256 KiB ceiling because staged results can exceed commands.
MAX_MESSAGE_BYTES = 16_384
MAX_OUTBOUND_MESSAGE_BYTES = 262_144
DEFAULT_RELAY_CLAIM_LEASE_SECONDS = 300

type ConsumeStatus = Literal[
    "EMPTY",
    "APPLIED",
    "DELETE_FAILED",
    "MALFORMED",
    "UNAUTHENTICATED",
    "REJECTED",
    "RECEIVE_FAILED",
]
type RelayStatus = Literal["EMPTY", "SENT", "SEND_FAILED"]
type BeforeSend = Callable[[str, Mapping[str, object]], None]


@dataclass(frozen=True, slots=True)
class QueueDelivery:
    receipt_handle: str
    body: str
    sender_id: str | None


class Queue(Protocol):
    def receive(self) -> Sequence[QueueDelivery]: ...

    def delete(self, receipt_handle: str) -> None: ...

    def send(self, body: str) -> None: ...


class SessionFactory(Protocol):
    def __call__(self) -> Session: ...

    def begin(self) -> AbstractContextManager[Session]: ...


class GateApplier(Protocol):
    def __call__(
        self,
        session: Session,
        gate_command: CommitGateCommand,
        *,
        ack_message_id: UUID,
        occurred_at: datetime,
        private_scope: PrivateWriteScope | None = None,
    ) -> CommitGateAckProposal: ...


class PrivateWriteAuthorityProvider(Protocol):
    """Authenticate one commit-gate authority decision outside its wire body."""

    def __call__(self, gate: CommitGateCommand) -> PrivateWriteAuthorityDecision: ...


@dataclass(frozen=True, slots=True)
class ConsumeResult:
    status: ConsumeStatus


@dataclass(frozen=True, slots=True)
class RelayResult:
    status: RelayStatus


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _reject_json_constant(_value: str) -> None:
    raise ValueError("invalid JSON constant")


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _strict_json_object(body: str, *, max_bytes: int = MAX_MESSAGE_BYTES) -> dict[str, object]:
    if not isinstance(body, str) or len(body.encode("utf-8")) > max_bytes:
        raise ValueError("invalid queue body")
    value = json.loads(
        body,
        object_pairs_hook=_object_without_duplicate_keys,
        parse_constant=_reject_json_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("queue body must be a JSON object")
    return value


def _sender_matches(sender_id: str | None, expected_sender_id: str) -> bool:
    if not isinstance(sender_id, str) or not isinstance(expected_sender_id, str):
        return False
    if not expected_sender_id or ":" in expected_sender_id:
        return False
    stable_id = sender_id.partition(":")[0]
    try:
        stable_bytes = stable_id.encode("ascii")
        expected_bytes = expected_sender_id.encode("ascii")
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(stable_bytes, expected_bytes)


def _wire_body(payload: dict[str, object]) -> str:
    body = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    if len(body.encode("utf-8")) > MAX_OUTBOUND_MESSAGE_BYTES:
        raise ValueError("persisted queue body is too large")
    return body


def _get_relay_outbox(
    session: Session,
    kind: Literal["STAGED", "ACK"],
    message_id: UUID,
) -> PrivateStagedOutbox | PrivateCommitGateAck | None:
    if kind == "STAGED":
        return session.get(PrivateStagedOutbox, message_id, populate_existing=True)
    return session.get(PrivateCommitGateAck, message_id, populate_existing=True)


def _stored_private_scope(session: Session, command_id: UUID) -> PrivateWriteScope | None:
    stage = session.get(PrivateCommitStage, command_id, populate_existing=True)
    if stage is None or stage.private_scope_kind not in {"ACCOUNT", "PROJECT"}:
        return None
    try:
        epoch = int(stage.owner_deletion_epoch)
        kind: Literal["ACCOUNT", "PROJECT"] = (
            "ACCOUNT" if stage.private_scope_kind == "ACCOUNT" else "PROJECT"
        )
        scope = PrivateDeletionScope(
            kind=kind,
            project_id=stage.project_id,
        )
        return PrivateWriteScope(
            PrivateWriteAuthorityDecision(
                owner_user_id=stage.owner_ref,
                owner_deletion_epoch=epoch,
                scope=scope,
                authority_ref="w2:persisted-private-commit-stage",
                command_id=stage.command_id,
                job_id=stage.job_id,
            )
        )
    except (TypeError, ValueError):
        return None


def _lock_relay_owner_scope(session: Session, command_id: UUID) -> PrivateWriteScope:
    proof = _stored_private_scope(session, command_id)
    if proof is None:
        raise RuntimeError("persisted private relay scope unavailable")
    lock_private_write_scope(session, proof)
    current = _stored_private_scope(session, command_id)
    if current != proof:
        raise RuntimeError("persisted private relay scope changed")
    return proof


def _lock_relay_scope(session: Session, command_id: UUID) -> PrivateWriteScope:
    proof = _lock_relay_owner_scope(session, command_id)
    _lock_command(session, command_id)
    current = _stored_private_scope(session, command_id)
    if current != proof:
        raise RuntimeError("persisted private relay scope changed")
    return proof


def consume_once(
    session_factory: SessionFactory,
    queue: Queue,
    expected_sender_id: str,
    *,
    clock: Callable[[], datetime] = _utc_now,
    message_id_factory: Callable[[], UUID] = uuid4,
    apply_gate: GateApplier | None = None,
    authority_provider: PrivateWriteAuthorityProvider | None = None,
) -> ConsumeResult:
    """Consume at most one gate command; rejected receipts remain for retry/DLQ."""

    try:
        deliveries = queue.receive()
    except Exception:
        return ConsumeResult(status="RECEIVE_FAILED")
    if not deliveries:
        return ConsumeResult(status="EMPTY")
    delivery = deliveries[0]
    if not _sender_matches(delivery.sender_id, expected_sender_id):
        return ConsumeResult(status="UNAUTHENTICATED")
    try:
        payload = _strict_json_object(delivery.body)
        gate = parse_commit_gate_command(payload)
    except (TypeError, ValueError, UnicodeError, RecursionError, W1WireContractError):
        return ConsumeResult(status="MALFORMED")

    gate_applier = apply_commit_gate if apply_gate is None else apply_gate
    try:
        if authority_provider is None:
            raise RuntimeError("trusted private authority provider is required")
        private_scope = PrivateWriteScope(authority_provider(gate))
        with session_factory.begin() as session:
            ack = gate_applier(
                session,
                gate,
                ack_message_id=message_id_factory(),
                occurred_at=clock(),
                private_scope=private_scope,
            )
            persisted_ack = session.get(
                PrivateCommitGateAck, ack.message_id, populate_existing=True
            )
            if persisted_ack is None:
                raise RuntimeError("persisted private commit-gate ACK unavailable")
            # An accepted W1 replay asks for the same durable ACK again. Preserve
            # its stored identity/outcome and only re-arm its delivery marker.
            persisted_ack.delivered_at = None
    except Exception:
        return ConsumeResult(status="REJECTED")

    try:
        queue.delete(delivery.receipt_handle)
    except Exception:
        return ConsumeResult(status="DELETE_FAILED")
    return ConsumeResult(status="APPLIED")


def relay_once(
    session_factory: SessionFactory,
    queue: Queue,
    *,
    clock: Callable[[], datetime] = _utc_now,
    command_id: UUID | None = None,
    before_send: BeforeSend | None = None,
    claim_token_factory: Callable[[], object] = uuid4,
    claim_lease_seconds: int = DEFAULT_RELAY_CLAIM_LEASE_SECONDS,
) -> RelayResult:
    """Relay one persisted wire, optionally scoped to a synthetic command."""

    claimed: tuple[Literal["STAGED", "ACK"], UUID, UUID, UUID] | None = None

    def release_claim() -> None:
        if claimed is None:
            return
        kind, message_id, claimed_command_id, claim_token = claimed
        try:
            with session_factory.begin() as session:
                _lock_relay_scope(session, claimed_command_id)
                outbox = _get_relay_outbox(session, kind, message_id)
                if (
                    outbox is not None
                    and outbox.delivered_at is None
                    and outbox.relay_claim_token == claim_token
                ):
                    outbox.relay_claim_token = None
                    outbox.relay_claim_expires_at = None
        except Exception:
            # A failed cleanup remains recoverable by DB-clock lease expiry.
            return

    try:
        if (
            type(command_id) not in {UUID, type(None)}
            or not isinstance(claim_lease_seconds, int)
            or isinstance(claim_lease_seconds, bool)
            or not 1 <= claim_lease_seconds <= 43_200
        ):
            return RelayResult(status="SEND_FAILED")
        with session_factory() as session:
            staged = session.scalar(
                select(PrivateStagedOutbox)
                .where(
                    PrivateStagedOutbox.delivered_at.is_(None),
                    PrivateStagedOutbox.payload.is_not(None),
                    or_(
                        PrivateStagedOutbox.relay_claim_token.is_(None),
                        PrivateStagedOutbox.relay_claim_expires_at <= func.clock_timestamp(),
                    ),
                    *(
                        (PrivateStagedOutbox.command_id == command_id,)
                        if command_id is not None
                        else ()
                    ),
                )
                .order_by(PrivateStagedOutbox.message_id)
                .limit(1)
            )
            if staged is not None:
                candidate: tuple[Literal["STAGED", "ACK"], UUID, UUID] | None = (
                    "STAGED",
                    staged.message_id,
                    staged.command_id,
                )
            else:
                ack = session.scalar(
                    select(PrivateCommitGateAck)
                    .where(
                        PrivateCommitGateAck.delivered_at.is_(None),
                        or_(
                            PrivateCommitGateAck.relay_claim_token.is_(None),
                            PrivateCommitGateAck.relay_claim_expires_at <= func.clock_timestamp(),
                        ),
                        *(
                            (PrivateCommitGateAck.command_id == command_id,)
                            if command_id is not None
                            else ()
                        ),
                    )
                    .order_by(PrivateCommitGateAck.message_id)
                    .limit(1)
                )
                candidate = None if ack is None else ("ACK", ack.message_id, ack.command_id)
        if candidate is None:
            return RelayResult(status="EMPTY")

        kind, message_id, candidate_command_id = candidate
        claim_token = claim_token_factory()
        if not isinstance(claim_token, UUID):
            return RelayResult(status="SEND_FAILED")
        with session_factory.begin() as session:
            _lock_relay_scope(session, candidate_command_id)
            outbox = _get_relay_outbox(session, kind, message_id)
            db_now = session.scalar(select(func.clock_timestamp()))
            if not isinstance(db_now, datetime) or db_now.tzinfo is None:
                raise RuntimeError("database clock unavailable")
            if (
                outbox is None
                or outbox.command_id != candidate_command_id
                or outbox.delivered_at is not None
                or (kind == "STAGED" and outbox.payload is None)
                or (
                    outbox.relay_claim_token is not None
                    and (
                        outbox.relay_claim_expires_at is None
                        or outbox.relay_claim_expires_at > db_now
                    )
                )
            ):
                return RelayResult(status="EMPTY")
            payload = outbox.payload
            if payload is None:
                return RelayResult(status="EMPTY")
            body = _wire_body(payload)
            authorized_payload = _strict_json_object(
                body,
                max_bytes=MAX_OUTBOUND_MESSAGE_BYTES,
            )
            outbox.relay_claim_token = claim_token
            outbox.relay_claim_expires_at = db_now + timedelta(seconds=claim_lease_seconds)
        claimed = (kind, message_id, candidate_command_id, claim_token)

        with session_factory.begin() as session:
            private_scope = _lock_relay_owner_scope(session, candidate_command_id)
            outbox = _get_relay_outbox(session, kind, message_id)
            if (
                outbox is None
                or outbox.command_id != candidate_command_id
                or outbox.delivered_at is not None
                or outbox.relay_claim_token != claim_token
                or outbox.relay_claim_expires_at is None
            ):
                raise RuntimeError("persisted queue payload changed during relay authorization")
            payload = outbox.payload
            if payload is None or _wire_body(payload) != body:
                raise RuntimeError("persisted queue payload changed during relay authorization")
            if before_send is not None:
                before_send(kind, authorized_payload)
            queue.send(body)
            _lock_command(session, candidate_command_id)
            if _stored_private_scope(session, candidate_command_id) != private_scope:
                raise RuntimeError("persisted private relay scope changed")
            outbox = _get_relay_outbox(session, kind, message_id)
            if (
                outbox is None
                or outbox.command_id != candidate_command_id
                or outbox.delivered_at is not None
                or outbox.relay_claim_token != claim_token
                or outbox.relay_claim_expires_at is None
                or outbox.payload is None
                or _wire_body(outbox.payload) != body
            ):
                raise RuntimeError("persisted queue payload changed during relay send")
            outbox.delivered_at = clock()
            outbox.relay_claim_token = None
            outbox.relay_claim_expires_at = None
        claimed = None
        return RelayResult(status="SENT")
    except Exception:
        release_claim()
        return RelayResult(status="SEND_FAILED")
