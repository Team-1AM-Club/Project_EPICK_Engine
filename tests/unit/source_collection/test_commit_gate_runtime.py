"""Queue-independent W2 commit-gate runtime behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from epick_engine.source_collection import commit_gate_runtime, commit_gate_store
from epick_engine.source_collection.commit_gate_runtime import (
    MAX_MESSAGE_BYTES,
    QueueDelivery,
    consume_once,
)
from epick_engine.source_collection.private_deletion_v2 import PrivateDeletionScope
from epick_engine.source_collection.private_scope import PrivateWriteAuthorityDecision

EXPECTED_SENDER_ID = "AROASYNTHETICROLE01"
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@dataclass
class FakeQueue:
    deliveries: list[QueueDelivery] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    receive_error: Exception | None = None

    def receive(self) -> list[QueueDelivery]:
        if self.receive_error is not None:
            raise self.receive_error
        return list(self.deliveries)

    def delete(self, receipt_handle: str) -> None:
        self.deleted.append(receipt_handle)

    def send(self, body: str) -> None:
        raise AssertionError("consumer must not send queue messages")


class NeverSessionFactory:
    def begin(self) -> object:
        raise AssertionError("rejected input must not open a database transaction")


class EmptySession:
    def __enter__(self) -> EmptySession:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def scalar(self, _statement: object) -> None:
        return None


class EmptySessionFactory:
    def __call__(self) -> EmptySession:
        return EmptySession()


@dataclass
class PersistedAck:
    delivered_at: datetime | None


@dataclass(frozen=True)
class AppliedAck:
    message_id: UUID


class GateSession:
    def __init__(self) -> None:
        self.persisted_ack: PersistedAck | None = None

    def __enter__(self) -> GateSession:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, _model: object, _message_id: object, **_kwargs: object) -> PersistedAck | None:
        return self.persisted_ack


class GateSessionFactory:
    def __init__(self) -> None:
        self.session = GateSession()

    def begin(self) -> GateSession:
        return self.session


def _trusted_authority(gate) -> PrivateWriteAuthorityDecision:
    return PrivateWriteAuthorityDecision(
        owner_user_id=gate.authenticated_owner_ref,
        owner_deletion_epoch=gate.owner_deletion_epoch,
        scope=PrivateDeletionScope(kind="ACCOUNT", project_id=None),
        authority_ref="w1:test-gate-authority",
        command_id=gate.command_id,
        job_id=gate.job_id,
    )


def _consume(delivery: QueueDelivery | None, *, receive_error: Exception | None = None):
    queue = FakeQueue(
        deliveries=[] if delivery is None else [delivery], receive_error=receive_error
    )
    result = consume_once(NeverSessionFactory(), queue, EXPECTED_SENDER_ID)
    return result, queue


def test_empty_receive_has_fixed_safe_status() -> None:
    result, queue = _consume(None)

    assert result.status == "EMPTY"
    assert queue.deleted == []


def test_receive_failure_has_fixed_safe_status() -> None:
    result, queue = _consume(None, receive_error=RuntimeError("synthetic transport secret"))

    assert result.status == "RECEIVE_FAILED"
    assert queue.deleted == []
    assert "secret" not in repr(result)


def test_system_sender_id_is_checked_before_untrusted_body() -> None:
    delivery = QueueDelivery(
        receipt_handle="synthetic-receipt",
        body='{"producer":"w1"}',
        sender_id="AROADIFFERENTROLE01:session-name",
    )

    result, queue = _consume(delivery)

    assert result.status == "UNAUTHENTICATED"
    assert queue.deleted == []


def test_non_ascii_system_sender_id_is_rejected_without_exception() -> None:
    delivery = QueueDelivery(
        receipt_handle="synthetic-receipt",
        body='{"producer":"w1"}',
        sender_id=f"{EXPECTED_SENDER_ID}\u00e9:session-name",
    )

    result, queue = _consume(delivery)

    assert result.status == "UNAUTHENTICATED"
    assert queue.deleted == []


def test_matching_stable_role_prefix_does_not_make_malformed_payload_authenticated_work() -> None:
    delivery = QueueDelivery(
        receipt_handle="synthetic-receipt",
        body="{",
        sender_id=f"{EXPECTED_SENDER_ID}:synthetic-session",
    )

    result, queue = _consume(delivery)

    assert result.status == "MALFORMED"
    assert queue.deleted == []


def test_duplicate_json_keys_are_rejected_without_deleting_receipt() -> None:
    delivery = QueueDelivery(
        receipt_handle="synthetic-receipt",
        body='{"schema_version":"first","schema_version":"second"}',
        sender_id=f"{EXPECTED_SENDER_ID}:synthetic-session",
    )

    result, queue = _consume(delivery)

    assert result.status == "MALFORMED"
    assert queue.deleted == []


def test_oversized_body_is_rejected_without_deleting_receipt() -> None:
    delivery = QueueDelivery(
        receipt_handle="synthetic-receipt",
        body="x" * (MAX_MESSAGE_BYTES + 1),
        sender_id=f"{EXPECTED_SENDER_ID}:synthetic-session",
    )

    result, queue = _consume(delivery)

    assert result.status == "MALFORMED"
    assert queue.deleted == []


def test_unsupported_collection_dispatch_is_not_deleted_from_gate_only_queue() -> None:
    body = json.dumps(
        json.loads(
            (FIXTURES / "w1_private_contract/private-w2-command-dispatch.json").read_text(
                encoding="utf-8"
            )
        )
    )
    delivery = QueueDelivery(
        receipt_handle="synthetic-receipt",
        body=body,
        sender_id=f"{EXPECTED_SENDER_ID}:synthetic-session",
    )

    result, queue = _consume(delivery)

    assert result.status == "MALFORMED"
    assert queue.deleted == []


def test_relay_reports_empty_when_no_durable_outbox_is_pending() -> None:
    result = commit_gate_runtime.relay_once(EmptySessionFactory(), FakeQueue())

    assert result.status == "EMPTY"


def test_private_command_lock_keeps_legacy_direct_import_alias() -> None:
    assert commit_gate_store._lock_command is commit_gate_store.lock_private_command


def test_consume_once_keeps_private_gate_applier_as_its_default(monkeypatch) -> None:
    """Replacing the CT15 default with the collection-aware applier must fail."""

    body = (FIXTURES / "w1_private_contract/private-w2-commit-gate-prepare.json").read_text(
        encoding="utf-8"
    )
    queue = FakeQueue(
        [
            QueueDelivery(
                receipt_handle="legacy-default-receipt",
                body=body,
                sender_id=f"{EXPECTED_SENDER_ID}:synthetic-session",
            )
        ]
    )
    session_factory = GateSessionFactory()
    calls: list[str] = []

    def private_applier(
        session: GateSession,
        _gate: object,
        *,
        ack_message_id: UUID,
        occurred_at: datetime,
        private_scope: object,
    ) -> object:
        assert isinstance(ack_message_id, UUID)
        assert occurred_at == datetime(2026, 9, 20, tzinfo=UTC)
        calls.append("private")
        session.persisted_ack = PersistedAck(delivered_at=None)
        return AppliedAck(message_id=ack_message_id)

    def collection_applier(*_args: object, **_kwargs: object) -> object:
        calls.append("collection")
        raise AssertionError("legacy CT15 consume_once must not select the collection applier")

    monkeypatch.setattr(commit_gate_runtime, "apply_commit_gate", private_applier)
    monkeypatch.setattr(
        commit_gate_runtime,
        "apply_collection_commit_gate",
        collection_applier,
        raising=False,
    )

    result = consume_once(
        session_factory,
        queue,
        EXPECTED_SENDER_ID,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
        message_id_factory=uuid4,
        authority_provider=_trusted_authority,
    )

    assert result.status == "APPLIED"
    assert calls == ["private"]
    assert queue.deleted == ["legacy-default-receipt"]


def test_consume_once_allows_explicit_collection_aware_applier(monkeypatch) -> None:
    """Ignoring the apply_gate keyword would route general-runtime gates incorrectly."""

    body = (FIXTURES / "w1_private_contract/private-w2-commit-gate-finalize.json").read_text(
        encoding="utf-8"
    )
    queue = FakeQueue(
        [
            QueueDelivery(
                receipt_handle="collection-aware-receipt",
                body=body,
                sender_id=f"{EXPECTED_SENDER_ID}:synthetic-session",
            )
        ]
    )
    session_factory = GateSessionFactory()
    calls: list[str] = []

    def explicit_applier(
        session: GateSession,
        _gate: object,
        *,
        ack_message_id: UUID,
        occurred_at: datetime,
        private_scope: object,
    ) -> object:
        assert isinstance(ack_message_id, UUID)
        assert occurred_at == datetime(2026, 9, 20, tzinfo=UTC)
        calls.append("collection")
        session.persisted_ack = PersistedAck(delivered_at=None)
        return AppliedAck(message_id=ack_message_id)

    def unexpected_legacy(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("explicit general-runtime applier must override the legacy default")

    monkeypatch.setattr(commit_gate_runtime, "apply_commit_gate", unexpected_legacy)

    result = consume_once(
        session_factory,
        queue,
        EXPECTED_SENDER_ID,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
        message_id_factory=uuid4,
        apply_gate=explicit_applier,
        authority_provider=_trusted_authority,
    )

    assert result.status == "APPLIED"
    assert calls == ["collection"]
    assert queue.deleted == ["collection-aware-receipt"]


def test_valid_gate_is_rejected_without_trusted_authority_provider() -> None:
    body = (FIXTURES / "w1_private_contract/private-w2-commit-gate-prepare.json").read_text(
        encoding="utf-8"
    )
    queue = FakeQueue(
        [
            QueueDelivery(
                receipt_handle="missing-provider-receipt",
                body=body,
                sender_id=f"{EXPECTED_SENDER_ID}:synthetic-session",
            )
        ]
    )

    result = consume_once(NeverSessionFactory(), queue, EXPECTED_SENDER_ID)

    assert result.status == "REJECTED"
    assert queue.deleted == []
