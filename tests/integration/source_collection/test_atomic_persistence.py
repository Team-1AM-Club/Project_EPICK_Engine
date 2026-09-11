from __future__ import annotations

from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier, Lock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

import epick_engine.source_collection.contracts as contracts
import epick_engine.source_collection.persistence as persistence_module
from epick_engine.source_collection.contracts import (
    CollectionCommand,
    CollectionResult,
    DateValue,
    ExtractionStatus,
    Locator,
    PostingSection,
    Representation,
    SourceEvent,
    SourceObservationSnapshot,
    SourceType,
)
from epick_engine.source_collection.persistence import (
    Base,
    CollectionAttempt,
    Company,
    Evidence,
    ExecutionAuthorityGrant,
    ExtractionRevision,
    InvalidPreparedCollection,
    OutboxEvent,
    ParserExecution,
    PersistenceConflict,
    PreparedCollectionCommit,
    PreparedEvidence,
    PreparedExtractionRevision,
    PreparedParserExecution,
    PreparedSourceObservation,
    PreparedSourceVersion,
    RequestDeduplication,
    Source,
    SourceObservation,
    SourcePolicyDecision,
    SourceVersion,
    StaleExecution,
    commit_prepared_collection,
    resolve_request_deduplication,
)

pytestmark = pytest.mark.approved_postgres

NOW = datetime(2026, 9, 10, tzinfo=UTC)
OWNER = UUID("00000000-0000-4000-8000-000000000201")


@pytest.fixture
def database_engine(approved_postgres_url) -> Iterator[Engine]:
    admin_engine = create_engine(approved_postgres_url, pool_pre_ping=True)
    schema = f"epick_w2_atomic_{uuid4().hex}"
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
def session_factory(database_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(database_engine, expire_on_commit=False)


def _seed_source(
    session_factory: sessionmaker[Session],
) -> tuple[Company, Source, SourcePolicyDecision]:
    company = Company(
        company_id=uuid4(),
        legal_name="Atomic Test Company Ltd.",
        aliases=["Atomic Test Company"],
        official_domains=["example.test"],
        legal_identifiers={"registration": "ATOMIC-001"},
        identity_status="verified",
        identity_evidence=["synthetic://company-evidence"],
    )
    source = Source(
        source_id=uuid4(),
        company_id=company.company_id,
        source_type="job_posting",
        canonical_url="https://jobs.example.test/opening/1",
        title="Atomic Platform Engineer",
    )
    policy = SourcePolicyDecision(
        policy_decision_id=uuid4(),
        source_id=source.source_id,
        revision=1,
        official_status="verified",
        access_class="public",
        collection_permission="allowed",
        excerpt_storage_permission="allowed",
        body_storage_permission="denied",
        redistribution_permission="unknown",
        evidence_refs=["synthetic://policy-evidence"],
        checked_at=NOW,
        policy_version="atomic-policy-v1",
    )
    with session_factory.begin() as session:
        session.add_all([company, source, policy])
    return company, source, policy


def _policy_snapshot(policy: SourcePolicyDecision) -> contracts.Policy:
    return contracts.Policy.model_validate(
        {
            "policy_decision_id": policy.policy_decision_id,
            "official_status": policy.official_status,
            "access_class": policy.access_class,
            "collection_permission": policy.collection_permission,
            "excerpt_storage_permission": policy.excerpt_storage_permission,
            "body_storage_permission": policy.body_storage_permission,
            "redistribution_permission": policy.redistribution_permission,
            "checked_at": policy.checked_at,
            "policy_version": policy.policy_version,
        }
    )


def _command(source: Source, *, command_id: UUID | None = None) -> CollectionCommand:
    return CollectionCommand.model_validate(
        {
            "schema_version": "w2.collection.v1",
            "command_id": command_id or uuid4(),
            "job_id": uuid4(),
            "authenticated_owner_ref": OWNER,
            "project_ref": None,
            "company_id": source.company_id,
            "source_id": source.source_id,
            "input_version": 1,
            "execution_fence": "atomic-test-fence",
            "owner_deletion_epoch": 0,
            "purpose_ref": uuid4(),
            "core_source_decision": {
                "is_core": True,
                "decided_by": "test",
                "rationale": "atomic persistence test",
                "decision_revision": 1,
                "analysis_input_version": 1,
            },
            "resume_stage": "fetch",
            "policy_revision": 1,
        }
    )


def _unknown_date() -> DateValue:
    return DateValue(
        status="unknown",
        raw_text=None,
        value=None,
        precision=None,
        timezone=None,
    )


def _complete_result(
    command: CollectionCommand,
    *,
    source_version_id: UUID,
    extraction_revision_id: UUID,
    result_version: int = 1,
    message: str = "collection complete",
) -> CollectionResult:
    return CollectionResult.model_validate(
        {
            "schema_version": "w2.collection.v1",
            "command_id": command.command_id,
            "job_id": command.job_id,
            "source_id": command.source_id,
            "input_version": command.input_version,
            "result_version": result_version,
            "policy_revision": command.policy_revision,
            "successful_source_refs": [
                {
                    "source_id": command.source_id,
                    "source_version_id": source_version_id,
                    "extraction_revision_id": extraction_revision_id,
                }
            ],
            "failures": [],
            "completion_kind": "complete",
            "resume_stage": None,
            "checkpoint_ref": None,
            "required_actions": [],
            "retry_not_before": None,
            "message_ko": message,
        }
    )


def _failure_result(command: CollectionCommand) -> CollectionResult:
    return CollectionResult.model_validate(
        {
            "schema_version": "w2.collection.v1",
            "command_id": command.command_id,
            "job_id": command.job_id,
            "source_id": command.source_id,
            "input_version": command.input_version,
            "result_version": 1,
            "policy_revision": command.policy_revision,
            "successful_source_refs": [],
            "failures": [
                {
                    "source_id": command.source_id,
                    "stage": "fetch",
                    "code": "NOT_FOUND",
                    "missing_sections": ["body"],
                    "impact": "source was not available",
                    "core_decision_revision": 1,
                }
            ],
            "completion_kind": "none",
            "resume_stage": "fetch",
            "checkpoint_ref": "retry:atomic",
            "required_actions": [],
            "retry_not_before": None,
            "message_ko": "collection failed",
        }
    )


def _observation(
    source: Source,
    policy: SourcePolicyDecision,
    *,
    observation_id: UUID | None = None,
    source_version_id: UUID | None,
    available: bool,
) -> SourceObservationSnapshot:
    return SourceObservationSnapshot(
        observation_id=observation_id or uuid4(),
        source_id=source.source_id,
        source_version_id=source_version_id,
        policy_decision_id=policy.policy_decision_id,
        observed_at=NOW,
        access_class="public" if available else "unavailable",
        acquisition_status="AVAILABLE" if available else "NOT_FOUND",
        http_status=200 if available else 404,
        checked_url=source.canonical_url,
        error_code=None if available else "NOT_FOUND",
        representation="static_html" if available else None,
    )


def _event(
    source: Source,
    observation: SourceObservationSnapshot,
    *,
    event_id: UUID | None = None,
    aggregate_revision: int,
) -> SourceEvent:
    return SourceEvent(
        event_id=event_id or uuid4(),
        event_type="source.observation.changed",
        schema_version="w2.source.v1",
        aggregate_id=source.source_id,
        aggregate_revision=aggregate_revision,
        occurred_at=NOW,
        payload=observation,
    )


def _complete_prepared(
    command: CollectionCommand,
    source: Source,
    policy: SourcePolicyDecision,
    *,
    attempt_id: UUID | None = None,
    source_version_id: UUID | None = None,
    evidence_id: UUID | None = None,
    extraction_revision_id: UUID | None = None,
    parser_execution_id: UUID | None = None,
    observation_id: UUID | None = None,
    event_id: UUID | None = None,
    aggregate_revision: int,
    content_hash: str = "a" * 64,
    result_version: int = 1,
    message: str = "collection complete",
) -> PreparedCollectionCommit:
    version_id = source_version_id or uuid4()
    prepared_evidence_id = evidence_id or uuid4()
    revision_id = extraction_revision_id or uuid4()
    snapshot = _observation(
        source,
        policy,
        observation_id=observation_id,
        source_version_id=version_id,
        available=True,
    )
    prepared_version = PreparedSourceVersion(
        source_version_id=version_id,
        source_id=source.source_id,
        company_id=source.company_id,
        title=source.title,
        source_type=SourceType.JOB_POSTING,
        canonical_url=source.canonical_url,
        content_hash=content_hash,
        hash_profile_version="html-v1",
        representation=Representation.STATIC_HTML,
        first_parser_version="atomic-parser-v1",
        collected_at=NOW,
        published_at=_unknown_date(),
        valid_from=_unknown_date(),
        valid_to=_unknown_date(),
        language="en",
        policy_decision_id=policy.policy_decision_id,
    )
    prepared_evidence = PreparedEvidence(
        evidence_id=prepared_evidence_id,
        source_version_id=version_id,
        evidence_key="required:0",
        section_title="Required",
        text_excerpt="Python experience",
        locator=Locator(
            kind="css",
            value="#requirements",
            normalization_version=None,
            start=None,
            end=None,
        ),
        chunk_order=0,
        origin_kind="direct",
    )
    prepared_extraction = PreparedExtractionRevision(
        extraction_revision_id=revision_id,
        source_version_id=version_id,
        parser_version="atomic-parser-v1",
        output_hash=content_hash,
        created_at=NOW,
        extraction_status=ExtractionStatus.COMPLETE,
        posting_sections=(
            PostingSection(
                section_key="required",
                kind="required",
                heading_raw="Required",
                text_raw="Python experience",
                evidence_ids=[prepared_evidence_id],
                order=0,
                relation_text=None,
            ),
        ),
        date_values={"published": _unknown_date()},
        limitations=(),
        evidence_ids=(prepared_evidence_id,),
    )
    prepared_execution = PreparedParserExecution(
        parser_execution_id=parser_execution_id or uuid4(),
        source_id=source.source_id,
        source_version_id=version_id,
        content_hash=content_hash,
        parser_version="atomic-parser-v1",
        output_hash=content_hash,
        extraction_revision_id=revision_id,
        status="succeeded",
        executed_at=NOW,
    )
    return PreparedCollectionCommit(
        attempt_id=attempt_id or uuid4(),
        result=_complete_result(
            command,
            source_version_id=version_id,
            extraction_revision_id=revision_id,
            result_version=result_version,
            message=message,
        ),
        finalized_at=NOW,
        source_version=prepared_version,
        evidence=(prepared_evidence,),
        extraction_revision=prepared_extraction,
        parser_execution=prepared_execution,
        observation=PreparedSourceObservation(snapshot=snapshot),
        events=(
            _event(source, snapshot, event_id=event_id, aggregate_revision=aggregate_revision),
        ),
    )


def _failure_prepared(
    command: CollectionCommand,
    source: Source,
    policy: SourcePolicyDecision,
    *,
    attempt_id: UUID | None = None,
    observation_id: UUID | None = None,
    event_id: UUID | None = None,
    aggregate_revision: int,
) -> PreparedCollectionCommit:
    snapshot = _observation(
        source,
        policy,
        observation_id=observation_id,
        source_version_id=None,
        available=False,
    )
    return PreparedCollectionCommit(
        attempt_id=attempt_id or uuid4(),
        result=_failure_result(command),
        finalized_at=NOW,
        observation=PreparedSourceObservation(snapshot=snapshot),
        events=(
            _event(source, snapshot, event_id=event_id, aggregate_revision=aggregate_revision),
        ),
    )


def _grant(
    command: CollectionCommand,
    attempt_id: UUID,
    *,
    pointer_eligible: bool,
) -> ExecutionAuthorityGrant:
    return ExecutionAuthorityGrant(
        attempt_id=attempt_id,
        owner_user_id=command.authenticated_owner_ref,
        job_id=command.job_id,
        command_id=command.command_id,
        company_id=command.company_id,
        source_id=command.source_id,
        input_version=command.input_version,
        execution_fence=command.execution_fence,
        owner_deletion_epoch=command.owner_deletion_epoch,
        pointer_eligible=pointer_eligible,
    )


def _locker(
    command: CollectionCommand,
    *,
    pointer_eligible: bool,
    seen_sessions: list[Session] | None = None,
):
    def lock(
        session: Session, *, command: CollectionCommand, attempt_id: UUID
    ) -> ExecutionAuthorityGrant:
        if seen_sessions is not None:
            seen_sessions.append(session)
        assert session.in_transaction()
        session.execute(
            select(Source.source_id).where(Source.source_id == command.source_id)
        ).scalar_one()
        return _grant(command, attempt_id, pointer_eligible=pointer_eligible)

    return lock


def _count(session: Session, model: type[Base]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _counts(session: Session) -> tuple[int, int, int, int, int, int, int]:
    return (
        _count(session, SourceVersion),
        _count(session, Evidence),
        _count(session, ExtractionRevision),
        _count(session, ParserExecution),
        _count(session, SourceObservation),
        _count(session, CollectionAttempt),
        _count(session, OutboxEvent),
    )


def _payload_keys(value: object) -> set[str]:
    if isinstance(value, Mapping):
        return {str(key) for key in value}.union(*(_payload_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_payload_keys(item) for item in value)) if value else set()
    return set()


def test_atomic_commit_locks_first_and_keeps_private_result_out_of_public_event(
    database_engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    _, source, policy = _seed_source(session_factory)
    command = _command(source)
    prepared = _complete_prepared(command, source, policy, aggregate_revision=1)
    statements: list[str] = []
    seen_sessions: list[Session] = []

    def capture_statement(_connection, _cursor, statement, _parameters, _context, _many) -> None:
        statements.append(statement)

    event.listen(database_engine, "before_cursor_execute", capture_statement)
    try:
        returned = commit_prepared_collection(
            session_factory,
            command=command,
            prepared=prepared,
            lock_authority=_locker(command, pointer_eligible=True, seen_sessions=seen_sessions),
        )
    finally:
        event.remove(database_engine, "before_cursor_execute", capture_statement)

    assert returned == prepared.result
    assert len(seen_sessions) == 1
    assert "select" in statements[0].lower()
    assert "sources" in statements[0].lower()

    with session_factory() as session:
        attempt = session.get(CollectionAttempt, prepared.attempt_id)
        persisted_source = session.get(Source, source.source_id)
        outbox = session.get(OutboxEvent, prepared.events[0].event_id)

        assert attempt is not None
        assert persisted_source is not None
        assert outbox is not None
        assert attempt.result_payload == prepared.result.model_dump(mode="json")
        assert attempt.finalized_at == NOW
        assert (
            persisted_source.current_source_version_id == prepared.source_version.source_version_id
        )
        assert (
            persisted_source.latest_observation_id == prepared.observation.snapshot.observation_id
        )
        assert outbox.payload == prepared.events[0].payload.model_dump(mode="json")
        assert _payload_keys(outbox.payload).isdisjoint(
            {
                "authenticated_owner_ref",
                "owner_user_id",
                "job_id",
                "project_id",
                "purpose_ref",
                "execution_fence",
                "owner_deletion_epoch",
                "result_payload",
            }
        )


def test_same_command_replays_stored_result_without_appending_rows(
    session_factory: sessionmaker[Session],
) -> None:
    _, source, policy = _seed_source(session_factory)
    command = _command(source)
    first = _complete_prepared(command, source, policy, aggregate_revision=1)
    commit_prepared_collection(
        session_factory,
        command=command,
        prepared=first,
        lock_authority=_locker(command, pointer_eligible=True),
    )
    with session_factory() as session:
        before = _counts(session)

    replay_payload = _complete_prepared(
        command,
        source,
        policy,
        attempt_id=first.attempt_id,
        aggregate_revision=2,
        content_hash="b" * 64,
        result_version=2,
        message="must not be persisted",
    )
    replayed = commit_prepared_collection(
        session_factory,
        command=command,
        prepared=replay_payload,
        lock_authority=_locker(command, pointer_eligible=True),
    )

    assert replayed == first.result
    with session_factory() as session:
        assert _counts(session) == before
        attempt = session.get(CollectionAttempt, first.attempt_id)
        assert attempt is not None
        assert attempt.result_payload == first.result.model_dump(mode="json")


def test_stale_authority_rejects_before_any_w2_write(
    session_factory: sessionmaker[Session],
) -> None:
    _, source, policy = _seed_source(session_factory)
    command = _command(source)
    prepared = _complete_prepared(command, source, policy, aggregate_revision=1)

    def stale_locker(
        session: Session, *, command: CollectionCommand, attempt_id: UUID
    ) -> ExecutionAuthorityGrant:
        session.execute(
            select(Source.source_id).where(Source.source_id == command.source_id)
        ).scalar_one()
        return ExecutionAuthorityGrant(
            attempt_id=attempt_id,
            owner_user_id=uuid4(),
            job_id=command.job_id,
            command_id=command.command_id,
            company_id=command.company_id,
            source_id=command.source_id,
            input_version=command.input_version,
            execution_fence=command.execution_fence,
            owner_deletion_epoch=command.owner_deletion_epoch,
            pointer_eligible=True,
        )

    with pytest.raises(StaleExecution, match="execution authority"):
        commit_prepared_collection(
            session_factory,
            command=command,
            prepared=prepared,
            lock_authority=stale_locker,
        )

    with session_factory() as session:
        persisted_source = session.get(Source, source.source_id)
        assert persisted_source is not None
        assert _counts(session) == (0, 0, 0, 0, 0, 0, 0)
        assert persisted_source.current_source_version_id is None
        assert persisted_source.latest_observation_id is None


def test_pointer_updates_are_authority_gated_and_reuse_returned_version(
    session_factory: sessionmaker[Session],
) -> None:
    _, source, policy = _seed_source(session_factory)

    command_a = _command(source)
    first_a = _complete_prepared(command_a, source, policy, aggregate_revision=1)
    commit_prepared_collection(
        session_factory,
        command=command_a,
        prepared=first_a,
        lock_authority=_locker(command_a, pointer_eligible=True),
    )

    command_b = _command(source)
    version_b = _complete_prepared(
        command_b,
        source,
        policy,
        aggregate_revision=2,
        content_hash="b" * 64,
    )
    commit_prepared_collection(
        session_factory,
        command=command_b,
        prepared=version_b,
        lock_authority=_locker(command_b, pointer_eligible=True),
    )

    command_a_again = _command(source)
    returned_a = _complete_prepared(
        command_a_again,
        source,
        policy,
        aggregate_revision=3,
        source_version_id=first_a.source_version.source_version_id,
        evidence_id=first_a.evidence[0].evidence_id,
        extraction_revision_id=first_a.extraction_revision.extraction_revision_id,
        parser_execution_id=first_a.parser_execution.parser_execution_id,
        content_hash=first_a.source_version.content_hash,
    )
    commit_prepared_collection(
        session_factory,
        command=command_a_again,
        prepared=returned_a,
        lock_authority=_locker(command_a_again, pointer_eligible=True),
    )

    command_failure = _command(source)
    failure = _failure_prepared(command_failure, source, policy, aggregate_revision=4)
    commit_prepared_collection(
        session_factory,
        command=command_failure,
        prepared=failure,
        lock_authority=_locker(command_failure, pointer_eligible=True),
    )

    command_ineligible = _command(source)
    ineligible = _complete_prepared(
        command_ineligible,
        source,
        policy,
        aggregate_revision=5,
        content_hash="c" * 64,
    )
    commit_prepared_collection(
        session_factory,
        command=command_ineligible,
        prepared=ineligible,
        lock_authority=_locker(command_ineligible, pointer_eligible=False),
    )

    with session_factory() as session:
        persisted_source = session.get(Source, source.source_id)
        assert persisted_source is not None
        assert _count(session, SourceVersion) == 3
        assert (
            persisted_source.current_source_version_id == first_a.source_version.source_version_id
        )
        assert persisted_source.latest_observation_id == failure.observation.snapshot.observation_id


def test_identical_stable_rows_reuse_and_late_outbox_conflict_rolls_back(
    session_factory: sessionmaker[Session],
) -> None:
    _, source, policy = _seed_source(session_factory)
    original_command = _command(source)
    original = _complete_prepared(original_command, source, policy, aggregate_revision=1)
    commit_prepared_collection(
        session_factory,
        command=original_command,
        prepared=original,
        lock_authority=_locker(original_command, pointer_eligible=True),
    )

    reusable_command = _command(source)
    reusable = _complete_prepared(
        reusable_command,
        source,
        policy,
        aggregate_revision=original.events[0].aggregate_revision,
        source_version_id=original.source_version.source_version_id,
        evidence_id=original.evidence[0].evidence_id,
        extraction_revision_id=original.extraction_revision.extraction_revision_id,
        parser_execution_id=original.parser_execution.parser_execution_id,
        observation_id=original.observation.snapshot.observation_id,
        event_id=original.events[0].event_id,
        content_hash=original.source_version.content_hash,
    )
    commit_prepared_collection(
        session_factory,
        command=reusable_command,
        prepared=reusable,
        lock_authority=_locker(reusable_command, pointer_eligible=True),
    )
    with session_factory() as session:
        after_reuse = _counts(session)
        assert after_reuse == (1, 1, 1, 1, 1, 2, 1)

    conflicting_command = _command(source)
    conflicting = _complete_prepared(
        conflicting_command,
        source,
        policy,
        aggregate_revision=original.events[0].aggregate_revision,
        source_version_id=original.source_version.source_version_id,
        evidence_id=original.evidence[0].evidence_id,
        extraction_revision_id=original.extraction_revision.extraction_revision_id,
        parser_execution_id=original.parser_execution.parser_execution_id,
        observation_id=original.observation.snapshot.observation_id,
        event_id=original.events[0].event_id,
        content_hash=original.source_version.content_hash,
    )
    conflicting_snapshot = _observation(
        source,
        policy,
        source_version_id=original.source_version.source_version_id,
        available=False,
    )
    conflicting_event = _event(
        source,
        conflicting_snapshot,
        event_id=original.events[0].event_id,
        aggregate_revision=original.events[0].aggregate_revision,
    )
    conflicting = PreparedCollectionCommit(
        attempt_id=conflicting.attempt_id,
        result=conflicting.result,
        finalized_at=conflicting.finalized_at,
        source_version=conflicting.source_version,
        evidence=conflicting.evidence,
        extraction_revision=conflicting.extraction_revision,
        parser_execution=conflicting.parser_execution,
        observation=conflicting.observation,
        events=(conflicting_event,),
    )

    with pytest.raises(PersistenceConflict, match="outbox event"):
        commit_prepared_collection(
            session_factory,
            command=conflicting_command,
            prepared=conflicting,
            lock_authority=_locker(conflicting_command, pointer_eligible=True),
        )

    with session_factory() as session:
        assert _counts(session) == after_reuse


def test_request_deduplication_replays_same_hash_and_rejects_different_hash(
    session_factory: sessionmaker[Session],
) -> None:
    owner_user_id = uuid4()
    request = {
        "owner_user_id": owner_user_id,
        "operation": "collection.start",
        "idempotency_key": "atomic-request-key",
        "request_hash": "a" * 64,
        "accepted_resource_ref": "source:atomic",
        "input_version": 1,
        "created_at": NOW,
    }
    with session_factory.begin() as session:
        created = resolve_request_deduplication(session, **request)

    with session_factory.begin() as session:
        replayed = resolve_request_deduplication(session, **request)

    assert replayed.request_deduplication_id == created.request_deduplication_id

    with pytest.raises(PersistenceConflict, match="different request"):
        with session_factory.begin() as session:
            resolve_request_deduplication(
                session,
                **{**request, "request_hash": "b" * 64},
            )

    with session_factory() as session:
        assert _count(session, RequestDeduplication) == 1


def test_natural_key_dedup_canonicalizes_new_candidate_ids(
    session_factory: sessionmaker[Session],
) -> None:
    _, source, policy = _seed_source(session_factory)
    first_command = _command(source)
    first = _complete_prepared(
        first_command,
        source,
        policy,
        aggregate_revision=1,
    )
    first_result = commit_prepared_collection(
        session_factory,
        command=first_command,
        prepared=first,
        lock_authority=_locker(first_command, pointer_eligible=True),
    )

    second_command = _command(source)
    second = _complete_prepared(
        second_command,
        source,
        policy,
        aggregate_revision=1,
    )
    second_result = commit_prepared_collection(
        session_factory,
        command=second_command,
        prepared=second,
        lock_authority=_locker(second_command, pointer_eligible=True),
    )

    first_ref = first_result.successful_source_refs[0]
    second_ref = second_result.successful_source_refs[0]
    assert second_ref.source_version_id == first_ref.source_version_id
    assert second_ref.extraction_revision_id == first_ref.extraction_revision_id
    with session_factory() as session:
        assert _count(session, SourceVersion) == 1
        assert _count(session, Evidence) == 1
        assert _count(session, ExtractionRevision) == 1
        assert _count(session, ParserExecution) == 2
        assert _count(session, SourceObservation) == 2
        attempts = session.scalars(
            select(CollectionAttempt).order_by(CollectionAttempt.command_id)
        ).all()
        stored_second = next(
            attempt for attempt in attempts if attempt.command_id == second_command.command_id
        )
        stored_result = CollectionResult.model_validate(stored_second.result_payload)
        assert (
            stored_result.successful_source_refs[0].source_version_id == first_ref.source_version_id
        )
        latest_event = session.scalar(
            select(OutboxEvent).order_by(OutboxEvent.aggregate_revision.desc())
        )
        assert latest_event is not None
        assert latest_event.payload["source_version_id"] == str(first_ref.source_version_id)


@pytest.mark.parametrize(
    "updates",
    [
        {"project_ref": "00000000-0000-4000-8000-000000000299"},
        {
            "core_source_decision": {
                "is_core": True,
                "decided_by": "test",
                "rationale": "changed private decision",
                "decision_revision": 1,
                "analysis_input_version": 1,
            }
        },
        {"resume_stage": "policy"},
    ],
)
def test_replay_rejects_changed_private_command_scope(
    session_factory: sessionmaker[Session],
    updates: Mapping[str, object],
) -> None:
    _, source, policy = _seed_source(session_factory)
    command = _command(source)
    prepared = _complete_prepared(
        command,
        source,
        policy,
        aggregate_revision=1,
    )
    commit_prepared_collection(
        session_factory,
        command=command,
        prepared=prepared,
        lock_authority=_locker(command, pointer_eligible=True),
    )
    changed = CollectionCommand.model_validate({**command.model_dump(mode="json"), **updates})

    with pytest.raises(PersistenceConflict, match="immutable payload"):
        commit_prepared_collection(
            session_factory,
            command=changed,
            prepared=prepared,
            lock_authority=_locker(changed, pointer_eligible=True),
        )


def test_public_write_requires_an_outbox_event(
    session_factory: sessionmaker[Session],
) -> None:
    _, source, policy = _seed_source(session_factory)
    command = _command(source)
    prepared = replace(
        _complete_prepared(
            command,
            source,
            policy,
            aggregate_revision=1,
        ),
        events=(),
    )

    with pytest.raises(InvalidPreparedCollection, match="source event"):
        commit_prepared_collection(
            session_factory,
            command=command,
            prepared=prepared,
            lock_authority=_locker(command, pointer_eligible=True),
        )
    with session_factory() as session:
        assert _counts(session) == (0, 0, 0, 0, 0, 0, 0)


def test_event_reuse_ignores_mutable_delivery_state(
    session_factory: sessionmaker[Session],
) -> None:
    _, source, policy = _seed_source(session_factory)
    first_command = _command(source)
    first = _complete_prepared(
        first_command,
        source,
        policy,
        aggregate_revision=1,
    )
    commit_prepared_collection(
        session_factory,
        command=first_command,
        prepared=first,
        lock_authority=_locker(first_command, pointer_eligible=True),
    )
    with session_factory.begin() as session:
        outbox = session.get(OutboxEvent, first.events[0].event_id)
        assert outbox is not None
        outbox.delivery_state = "delivered"

    second_command = _command(source)
    second = _complete_prepared(
        second_command,
        source,
        policy,
        source_version_id=first.source_version.source_version_id,
        evidence_id=first.evidence[0].evidence_id,
        extraction_revision_id=(first.extraction_revision.extraction_revision_id),
        parser_execution_id=first.parser_execution.parser_execution_id,
        observation_id=first.observation.snapshot.observation_id,
        event_id=first.events[0].event_id,
        aggregate_revision=99,
    )
    commit_prepared_collection(
        session_factory,
        command=second_command,
        prepared=second,
        lock_authority=_locker(second_command, pointer_eligible=True),
    )
    with session_factory() as session:
        outbox = session.get(OutboxEvent, first.events[0].event_id)
        assert outbox is not None
        assert outbox.delivery_state == "delivered"


def test_failure_result_with_version_observation_preserves_current_version(
    session_factory: sessionmaker[Session],
) -> None:
    _, source, policy = _seed_source(session_factory)
    first_command = _command(source)
    first = _complete_prepared(
        first_command,
        source,
        policy,
        aggregate_revision=1,
    )
    commit_prepared_collection(
        session_factory,
        command=first_command,
        prepared=first,
        lock_authority=_locker(first_command, pointer_eligible=True),
    )

    failed_command = _command(source)
    failed = _complete_prepared(
        failed_command,
        source,
        policy,
        aggregate_revision=2,
        content_hash="f" * 64,
    )
    failed = replace(failed, result=_failure_result(failed_command))
    commit_prepared_collection(
        session_factory,
        command=failed_command,
        prepared=failed,
        lock_authority=_locker(failed_command, pointer_eligible=True),
    )

    with session_factory() as session:
        persisted = session.get(Source, source.source_id)
        assert persisted is not None
        assert persisted.current_source_version_id == first.source_version.source_version_id
        assert persisted.latest_observation_id == failed.observation.snapshot.observation_id


def test_concurrent_same_command_replays_after_source_lock(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, source, policy = _seed_source(session_factory)
    command = _command(source)
    prepared = _complete_prepared(
        command,
        source,
        policy,
        aggregate_revision=1,
    )
    first_replay_barrier = Barrier(2)
    guarded_sessions: set[int] = set()
    guard = Lock()
    original_replay = persistence_module._replay_attempt

    def synchronized_replay(
        session: Session,
        *,
        command: CollectionCommand,
        attempt_id: UUID,
    ) -> CollectionResult | None:
        replay = original_replay(
            session,
            command=command,
            attempt_id=attempt_id,
        )
        with guard:
            first_call = id(session) not in guarded_sessions
            guarded_sessions.add(id(session))
        if first_call:
            assert replay is None
            first_replay_barrier.wait(timeout=10)
        return replay

    monkeypatch.setattr(
        persistence_module,
        "_replay_attempt",
        synchronized_replay,
    )

    def commit() -> CollectionResult:
        return commit_prepared_collection(
            session_factory,
            command=command,
            prepared=prepared,
            lock_authority=_locker(command, pointer_eligible=True),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(commit) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]

    assert results[0] == results[1] == prepared.result
    with session_factory() as session:
        assert _count(session, CollectionAttempt) == 1
        assert _count(session, SourceVersion) == 1
        assert _count(session, OutboxEvent) == 1


def test_concurrent_request_deduplication_reuses_one_row(
    session_factory: sessionmaker[Session],
) -> None:
    request = {
        "owner_user_id": uuid4(),
        "operation": "collection.concurrent",
        "idempotency_key": "same-concurrent-key",
        "request_hash": "c" * 64,
        "accepted_resource_ref": "source:concurrent",
        "input_version": 1,
        "created_at": NOW,
    }
    barrier = Barrier(2)

    def resolve() -> UUID:
        with session_factory.begin() as session:
            barrier.wait(timeout=10)
            row = resolve_request_deduplication(session, **request)
            return row.request_deduplication_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(resolve) for _ in range(2)]
        row_ids = [future.result(timeout=15) for future in futures]

    assert row_ids[0] == row_ids[1]
    with session_factory() as session:
        assert _count(session, RequestDeduplication) == 1
