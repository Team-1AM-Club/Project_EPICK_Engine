"""Recovery-boundary regression tests for source-collection delivery.

The PostgreSQL tests in this module cover only W2 transactional state.  The
in-memory W1 case is deliberately marked by its test name; it is not evidence
for a broker, checkpoint, or Linux process boundary.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.source_collection.test_atomic_persistence import (
    NOW,
    _command,
    _complete_prepared,
    _counts,
    _locker,
    _seed_source,
)
from tests.integration.source_collection.test_source_outbox import (
    RecordingPublisher,
    _delivery_state,
)
from tests.integration.source_collection.test_source_outbox import (
    _worker as outbox_worker,
)
from tests.integration.source_collection.w1_failure_fake import W1FailureFake, W1JobStatus
from tests.unit.source_collection.test_worker import _Control, _Execution, _Factory, _permit

from epick_engine.source_collection.contracts import CollectionStage, SourceEvent
from epick_engine.source_collection.persistence import Base, commit_prepared_collection
from epick_engine.source_collection.worker import OutboxDeliveryError, SourceCollectionWorker


@pytest.fixture
def recovery_database_engine(approved_postgres_url) -> Iterator[Engine]:
    """Use a disposable PostgreSQL schema without sharing W2 state with peers."""

    admin_engine = create_engine(approved_postgres_url, pool_pre_ping=True)
    schema = f"epick_w2_recovery_{uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = admin_engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def recovery_session_factory(recovery_database_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(recovery_database_engine, expire_on_commit=False)


def _source_worker(
    *,
    command,
    session_factory: Callable[[], Session],
    permit,
    run: Callable,
    finalize_error: Exception | None = None,
) -> tuple[SourceCollectionWorker, _Control, _Execution]:
    events: list[str] = []
    control = _Control(permit, events, finalize_error=finalize_error)
    execution = _Execution(events, run)
    return (
        SourceCollectionWorker(
            control=control,
            execution_factory=_Factory(events, execution),
            session_factory=session_factory,
            lock_authority=_locker(command, pointer_eligible=True),
            clock=lambda: NOW,
        ),
        control,
        execution,
    )


def _prepared_runner(prepared):
    def run(context):
        context.enter_stage(CollectionStage.PARSE, policy_revision=context.command.policy_revision)
        return prepared

    return run


def _event_snapshot(source_event: SourceEvent) -> str:
    return json.dumps(
        source_event.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


@pytest.mark.approved_postgres
def test_w2_execution_crash_before_commit_closes_and_leaves_no_collection_rows(
    recovery_session_factory: sessionmaker[Session],
) -> None:
    """Actual W2 evidence: execution failure never begins a durable result graph."""

    _, source, _ = _seed_source(recovery_session_factory)
    command = _command(source)
    permit = _permit(command)

    def crash_during_fetch(context):
        context.enter_stage(CollectionStage.PARSE, policy_revision=context.command.policy_revision)
        raise RuntimeError("synthetic fetch execution crash")

    worker, control, execution = _source_worker(
        command=command,
        session_factory=recovery_session_factory,
        permit=permit,
        run=crash_during_fetch,
    )

    with pytest.raises(RuntimeError, match="fetch execution crash"):
        worker.handle(command.model_dump(mode="json"))

    assert execution.close_count == 1
    assert control.stopped == [(permit, True, "execution_failed")]
    with recovery_session_factory() as session:
        assert _counts(session) == (0, 0, 0, 0, 0, 0, 0)


@pytest.mark.approved_postgres
def test_w2_commit_fault_rolls_back_result_and_outbox_graph(
    recovery_session_factory: sessionmaker[Session],
) -> None:
    """Actual W2 evidence: one transaction rolls back all collection rows."""

    _, source, policy = _seed_source(recovery_session_factory)
    command = _command(source)
    permit = _permit(command)
    prepared = _complete_prepared(
        command,
        source,
        policy,
        attempt_id=permit.attempt_id,
        aggregate_revision=1,
    )

    def commit_fault_session_factory() -> Session:
        session = recovery_session_factory()

        @event.listens_for(session, "before_commit", once=True)
        def fail_commit(_session: Session) -> None:
            raise RuntimeError("synthetic W2 commit fault")

        return session

    worker, control, execution = _source_worker(
        command=command,
        session_factory=commit_fault_session_factory,
        permit=permit,
        run=_prepared_runner(prepared),
    )

    with pytest.raises(RuntimeError, match="W2 commit fault"):
        worker.handle(command.model_dump(mode="json"))

    assert execution.close_count == 1
    assert control.stopped == [(permit, True, "commit_failed")]
    with recovery_session_factory() as session:
        assert _counts(session) == (0, 0, 0, 0, 0, 0, 0)


@pytest.mark.approved_postgres
def test_w2_post_commit_crash_redelivery_reuses_stored_result_without_new_rows(
    recovery_session_factory: sessionmaker[Session],
) -> None:
    """Actual W2 evidence: a redelivery replays the committed logical command."""

    _, source, policy = _seed_source(recovery_session_factory)
    command = _command(source)
    permit = _permit(command)
    initial = _complete_prepared(
        command,
        source,
        policy,
        attempt_id=permit.attempt_id,
        aggregate_revision=1,
    )
    crashing_worker, crashing_control, crashing_execution = _source_worker(
        command=command,
        session_factory=recovery_session_factory,
        permit=permit,
        run=_prepared_runner(initial),
        finalize_error=RuntimeError("synthetic crash after commit"),
    )

    with pytest.raises(RuntimeError, match="crash after commit"):
        crashing_worker.handle(command.model_dump(mode="json"))

    assert crashing_execution.close_count == 1
    assert crashing_control.stopped == []
    with recovery_session_factory() as session:
        counts_after_commit = _counts(session)
    assert counts_after_commit == (1, 1, 1, 1, 1, 1, 1)

    redelivery = _complete_prepared(
        command,
        source,
        policy,
        attempt_id=permit.attempt_id,
        aggregate_revision=2,
        content_hash="b" * 64,
        result_version=2,
        message="must be ignored after committed replay",
    )
    replay_worker, replay_control, replay_execution = _source_worker(
        command=command,
        session_factory=recovery_session_factory,
        permit=replace(permit),
        run=_prepared_runner(redelivery),
    )

    replayed = replay_worker.handle(command.model_dump(mode="json"))

    assert replayed == initial.result
    assert replay_execution.close_count == 1
    assert replay_control.finalized == [(permit, initial.result)]
    with recovery_session_factory() as session:
        assert _counts(session) == counts_after_commit


@pytest.mark.approved_postgres
def test_w2_outbox_ack_commit_fault_republishes_the_exact_pending_snapshot(
    recovery_session_factory: sessionmaker[Session],
) -> None:
    """Actual W2 state plus test-only W3 publisher: ACK failure leaves pending."""

    _, source, policy = _seed_source(recovery_session_factory)
    command = _command(source)
    prepared = _complete_prepared(command, source, policy, aggregate_revision=1)
    commit_prepared_collection(
        recovery_session_factory,
        command=command,
        prepared=prepared,
        lock_authority=_locker(command, pointer_eligible=True),
    )
    event_id = prepared.events[0].event_id
    publisher = RecordingPublisher()
    calls = 0

    def ack_commit_fault_session_factory() -> Session:
        nonlocal calls
        calls += 1
        session = recovery_session_factory()
        if calls == 2:

            @event.listens_for(session, "before_commit", once=True)
            def fail_ack_commit(_session: Session) -> None:
                raise RuntimeError("synthetic ACK commit fault")

        return session

    with pytest.raises(OutboxDeliveryError):
        outbox_worker(ack_commit_fault_session_factory, publisher).deliver_pending(limit=1)

    assert _delivery_state(recovery_session_factory, event_id) == "pending"
    assert len(publisher.events) == 1
    first_snapshot = _event_snapshot(publisher.events[0])

    assert outbox_worker(recovery_session_factory, publisher).deliver_pending(limit=1) == 1

    assert _delivery_state(recovery_session_factory, event_id) == "delivered"
    assert [_event_snapshot(item) for item in publisher.events] == [
        first_snapshot,
        first_snapshot,
    ]


def test_w1_fake_cancel_releases_slot_and_ignores_late_result() -> None:
    """Test-only W1 fake; it does not simulate a broker or a Linux worker."""

    source_id = UUID("00000000-0000-4000-8000-000000005401")
    fake = W1FailureFake(
        {
            "name": "cancel-late-result",
            "job_id": "00000000-0000-4000-8000-000000005402",
            "command_id": "00000000-0000-4000-8000-000000005403",
            "input_version": 1,
            "job_revision": 1,
            "result_revision": 1,
            "recorded_at": "2026-09-10T00:00:00Z",
            "sources": [
                {
                    "name": "primary",
                    "source_id": str(source_id),
                    "is_core": False,
                    "result_version": 1,
                    "core_decision_revision": 1,
                }
            ],
        }
    )

    assert fake.record_source_result(
        "primary",
        outcome="rate_limited",
        core_decision_revision=1,
    )
    receipt = fake.submit_decision(
        action="retry",
        source_id="primary",
        expected_input_version=1,
        expected_result_version=2,
        idempotency_key="retry-primary-once",
    )
    assert receipt["accepted"] is True
    assert fake.dispatch_ready() == (source_id,)
    assert fake.snapshot()["active_slots"] == 1

    fake.cancel()
    before_late_result = fake.snapshot()

    assert not fake.record_source_result(
        "primary",
        outcome="success",
        command_id="00000000-0000-4000-8000-000000005404",
    )

    after_late_result = fake.snapshot()
    assert after_late_result["status"] == W1JobStatus.CANCELLED.value
    assert after_late_result["active_slots"] == 0
    assert (
        after_late_result["logical_source_results"] == before_late_result["logical_source_results"]
    )
    assert after_late_result["ledger"][-1]["event"] == "source_result_after_cancel_ignored"


@pytest.mark.approved_postgres
def test_w2_invalid_payloads_do_not_block_an_independent_valid_handler_delivery(
    recovery_session_factory: sessionmaker[Session],
) -> None:
    """Actual handler boundary: poison commands make no W2 rows and do not poison later work."""

    _, source, policy = _seed_source(recovery_session_factory)
    command = _command(source)
    permit = _permit(command)
    prepared = _complete_prepared(
        command,
        source,
        policy,
        attempt_id=permit.attempt_id,
        aggregate_revision=1,
    )
    worker, control, execution = _source_worker(
        command=command,
        session_factory=recovery_session_factory,
        permit=permit,
        run=_prepared_runner(prepared),
    )
    poison = command.model_dump(mode="json")
    poison["core_source_decision"]["decision_revision"] = 0

    for payload in ({"schema_version": "w2.collection.v1"}, poison):
        with pytest.raises(ValidationError):
            worker.handle(payload)

    assert control.events == []
    assert execution.run_count == 0
    with recovery_session_factory() as session:
        assert _counts(session) == (0, 0, 0, 0, 0, 0, 0)

    committed = worker.handle(command.model_dump(mode="json"))

    assert committed == prepared.result
    assert execution.run_count == 1
    with recovery_session_factory() as session:
        assert _counts(session) == (1, 1, 1, 1, 1, 1, 1)
