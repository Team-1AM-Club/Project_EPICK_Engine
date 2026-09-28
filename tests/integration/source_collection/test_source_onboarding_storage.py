from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, func, inspect, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from epick_engine.source_collection.contracts import SourceType
from epick_engine.source_collection.persistence import (
    Base,
    Company,
    PrivateDeletionOwnerState,
    Source,
    SourceApprovalRuleHead,
    SourceApprovalRuleRevision,
    SourcePolicyDecision,
    SourceRegistrationReceipt,
    SourceRuntimeApproval,
    append_or_reuse_source_policy_decision,
)
from epick_engine.source_collection.source_onboarding_contracts import RegistrationMetadata
from epick_engine.source_collection.source_onboarding_policy import (
    load_source_runtime_approval,
    match_approved_rule,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
COMPANY_A = UUID("00000000-0000-4000-8000-00000000b201")
COMPANY_B = UUID("00000000-0000-4000-8000-00000000b202")
SOURCE_ID = UUID("00000000-0000-4000-8000-00000000b203")
RULE_A = UUID("00000000-0000-4000-8000-00000000b204")
RULE_B = UUID("00000000-0000-4000-8000-00000000b205")
OWNER_A = UUID("00000000-0000-4000-8000-00000000b206")
OWNER_B = UUID("00000000-0000-4000-8000-00000000b207")


def _limits() -> dict[str, int | float]:
    return {
        "site_concurrency": 1,
        "global_concurrency": 2,
        "source_ttl_seconds": 300,
        "max_response_bytes": 1_048_576,
        "max_decompressed_bytes": 2_097_152,
        "connect_timeout_seconds": 3.0,
        "read_timeout_seconds": 5.0,
        "max_redirects": 2,
        "general_retry_limit": 0,
        "retention_days": 7,
    }


@pytest.fixture
def database_engine(approved_postgres_url: URL) -> Iterator[Engine]:
    admin_engine = create_engine(approved_postgres_url, pool_pre_ping=True)
    schema_name = f"epick_source_onboarding_{uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    engine = admin_engine.execution_options(schema_translate_map={None: schema_name})
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def session_factory(database_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(database_engine, expire_on_commit=False)


@contextmanager
def _migration_schema(
    approved_postgres_url: URL,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[Engine, Config]]:
    schema_name = f"epick_source_onboarding_migration_{uuid4().hex}"
    schema_url = approved_postgres_url.update_query_dict(
        {"options": f"-csearch_path={schema_name}"}
    )
    admin_engine = create_engine(approved_postgres_url, pool_pre_ping=True)
    engine = create_engine(schema_url, pool_pre_ping=True)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    monkeypatch.setenv("EPICK_DATABASE_URL", schema_url.render_as_string(hide_password=False))
    try:
        yield engine, config
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        admin_engine.dispose()


def _metadata(
    url: str,
    *,
    company_id: UUID = COMPANY_A,
    source_type: str = "JOB_POSTING",
    official_domain: str = "company.test",
    legal_identifiers: list[str] | None = None,
) -> RegistrationMetadata:
    return RegistrationMetadata(
        schema_version="w1.private.w2-source-registration-lookup.v1",
        status="AVAILABLE",
        command_id=uuid4(),
        execution_fence=1,
        owner_deletion_epoch=0,
        company_id=company_id,
        source_id=SOURCE_ID,
        canonical_url=url,
        w1_source_type=source_type,
        registration_input_version="input-v1",
        company_official_domain=official_domain,
        company_legal_name="Synthetic Company A Ltd.",
        company_legal_identifiers=legal_identifiers or [f"corp:{company_id}"],
        company_identity_evidence_refs=[f"evidence:{company_id}"],
    )


def _add_rule(
    session: Session,
    *,
    rule_id: UUID = RULE_A,
    company_id: UUID = COMPANY_A,
    host: str = "careers.company.test",
    path: str = "/jobs",
    path_mode: str = "SEGMENT_PREFIX",
    queries: list[str] | None = None,
    active: bool = True,
) -> None:
    session.add(
        SourceApprovalRuleHead(
            approval_rule_id=rule_id,
            current_revision=1,
            is_active=active,
            updated_at=NOW,
        )
    )
    session.add(
        SourceApprovalRuleRevision(
            approval_rule_id=rule_id,
            revision=1,
            company_id=company_id,
            company_official_domain="company.test",
            company_legal_identifiers=[f"corp:{company_id}"],
            company_identity_evidence_refs=[f"evidence:{company_id}"],
            exact_host=host,
            path_mode=path_mode,
            path_value=path,
            allowed_query_strings=[""] if queries is None else queries,
            source_type=SourceType.JOB_POSTING.value,
            official_status="verified",
            access_class="public",
            collection_permission="allowed",
            excerpt_storage_permission="allowed",
            body_storage_permission="denied",
            redistribution_permission="denied",
            evidence_refs=["policy:evidence"],
            checked_at=NOW,
            policy_version="policy-v1",
            robots_permission="allowed",
            result_version=1,
            language="ko",
            redirect_robots_permissions=[],
            limits=_limits(),
            created_at=NOW,
        )
    )


@pytest.mark.approved_postgres
def test_empty_rule_set_denies(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        assert (
            match_approved_rule(
                session,
                _metadata("https://careers.company.test/jobs"),
            )
            is None
        )


@pytest.mark.approved_postgres
def test_exact_company_host_segment_query_and_type_match(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        _add_rule(session, queries=["team=platform"])
    with session_factory.begin() as session:
        matched = match_approved_rule(
            session,
            _metadata("https://careers.company.test/jobs/backend?team=platform"),
        )
        assert matched is not None
        assert matched.approval_rule_id == RULE_A
        assert matched.approval_rule_revision == 1


@pytest.mark.approved_postgres
@pytest.mark.parametrize(
    "metadata",
    [
        _metadata("https://careers.company.test/jobs-old"),
        _metadata("https://sub.careers.company.test/jobs"),
        _metadata("https://careers.company.test/jobs?unexpected=1"),
        _metadata("https://careers.company.test/jobs", source_type="COMPANY_PROFILE"),
        _metadata("https://careers.company.test/jobs", legal_identifiers=["corp:other"]),
    ],
    ids=["prefix-sibling", "subdomain", "query", "type", "identity"],
)
def test_rule_match_fails_closed_outside_the_exact_scope(
    session_factory: sessionmaker[Session], metadata: RegistrationMetadata
) -> None:
    with session_factory.begin() as session:
        _add_rule(session)
    with session_factory.begin() as session:
        assert match_approved_rule(session, metadata) is None


@pytest.mark.approved_postgres
def test_shared_host_does_not_approve_the_wrong_subsidiary(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        _add_rule(session, rule_id=RULE_A, company_id=COMPANY_A, path="/alpha")
        _add_rule(session, rule_id=RULE_B, company_id=COMPANY_B, path="/beta")
    with session_factory.begin() as session:
        assert (
            match_approved_rule(
                session,
                _metadata("https://careers.company.test/beta", company_id=COMPANY_A),
            )
            is None
        )


@pytest.mark.approved_postgres
def test_revoked_rule_does_not_match(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        _add_rule(session, active=False)
    with session_factory.begin() as session:
        assert (
            match_approved_rule(
                session,
                _metadata("https://careers.company.test/jobs"),
            )
            is None
        )


@pytest.mark.approved_postgres
def test_malformed_rule_runtime_payload_fails_closed(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        _add_rule(session)
        revision = session.get(SourceApprovalRuleRevision, (RULE_A, 1))
        assert revision is not None
        revision.redirect_robots_permissions = [["https://redirect.company.test"]]
    with session_factory.begin() as session:
        assert (
            match_approved_rule(
                session,
                _metadata("https://careers.company.test/jobs"),
            )
            is None
        )


def _add_source_policy(session: Session) -> SourcePolicyDecision:
    session.add(
        Company(
            company_id=COMPANY_A,
            legal_name="Synthetic Company",
            aliases=[],
            official_domains=["company.test"],
            legal_identifiers={"corp": str(COMPANY_A)},
            identity_status="verified",
            identity_evidence=[f"evidence:{COMPANY_A}"],
        )
    )
    session.add(
        Source(
            source_id=SOURCE_ID,
            company_id=COMPANY_A,
            source_type=SourceType.JOB_POSTING.value,
            canonical_url="https://careers.company.test/jobs",
        )
    )
    decision = SourcePolicyDecision(
        policy_decision_id=uuid4(),
        source_id=SOURCE_ID,
        revision=1,
        official_status="verified",
        access_class="public",
        collection_permission="allowed",
        excerpt_storage_permission="allowed",
        body_storage_permission="denied",
        redistribution_permission="denied",
        evidence_refs=["policy:evidence"],
        checked_at=NOW,
        policy_version="policy-v1",
    )
    session.add(decision)
    return decision


def _add_runtime_approval(session: Session) -> None:
    session.add(
        SourceRuntimeApproval(
            source_id=SOURCE_ID,
            approval_rule_id=RULE_A,
            approval_rule_revision=1,
            policy_revision=1,
            robots_permission="allowed",
            result_version=1,
            language="ko",
            redirect_robots_permissions=[],
            limits=_limits(),
            updated_at=NOW,
        )
    )


@pytest.mark.approved_postgres
def test_runtime_approval_loads_bound_row_but_not_absence_or_revocation(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        _add_source_policy(session)
    with session_factory.begin() as session:
        assert load_source_runtime_approval(session, SOURCE_ID) is None
        _add_rule(session)
        _add_runtime_approval(session)
    with session_factory.begin() as session:
        loaded = load_source_runtime_approval(session, SOURCE_ID)
        assert loaded is not None and loaded.policy_revision == 1
        session.get(SourceApprovalRuleHead, RULE_A).is_active = False  # type: ignore[union-attr]
    with session_factory.begin() as session:
        assert load_source_runtime_approval(session, SOURCE_ID) is None


@pytest.mark.approved_postgres
def test_runtime_approval_requires_rule_binding(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        _add_source_policy(session)
    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            session.add(
                SourceRuntimeApproval(
                    source_id=SOURCE_ID,
                    approval_rule_id=None,
                    approval_rule_revision=None,
                    policy_revision=1,
                    robots_permission="allowed",
                    result_version=1,
                    language="ko",
                    redirect_robots_permissions=[],
                    limits=_limits(),
                    updated_at=NOW,
                )
            )


@pytest.mark.approved_postgres
def test_runtime_approval_denies_cross_company_rule_binding(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        _add_source_policy(session)
        _add_rule(session)
        _add_runtime_approval(session)
        session.add(
            Company(
                company_id=COMPANY_B,
                legal_name="Other Company",
                aliases=[],
                official_domains=["company.test"],
                legal_identifiers={"corp": str(COMPANY_B)},
                identity_status="verified",
                identity_evidence=[f"evidence:{COMPANY_B}"],
            )
        )
        source = session.get(Source, SOURCE_ID)
        assert source is not None
        source.company_id = COMPANY_B
    with session_factory.begin() as session:
        assert load_source_runtime_approval(session, SOURCE_ID) is None


@pytest.mark.approved_postgres
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("canonical_url", "https://careers.company.test/admin"),
        ("source_type", SourceType.COMPANY_WEBSITE.value),
    ],
    ids=["url", "source-type"],
)
def test_runtime_approval_denies_source_url_or_type_outside_rule(
    session_factory: sessionmaker[Session], field: str, value: str
) -> None:
    with session_factory.begin() as session:
        _add_source_policy(session)
        _add_rule(session)
        _add_runtime_approval(session)
        source = session.get(Source, SOURCE_ID)
        assert source is not None
        setattr(source, field, value)
    with session_factory.begin() as session:
        assert load_source_runtime_approval(session, SOURCE_ID) is None


@pytest.mark.approved_postgres
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_refs", ["policy:other"]),
        ("collection_permission", "denied"),
    ],
    ids=["evidence", "policy"],
)
def test_runtime_approval_denies_policy_or_evidence_outside_rule(
    session_factory: sessionmaker[Session], field: str, value: object
) -> None:
    with session_factory.begin() as session:
        decision = _add_source_policy(session)
        _add_rule(session)
        _add_runtime_approval(session)
        setattr(decision, field, value)
    with session_factory.begin() as session:
        assert load_source_runtime_approval(session, SOURCE_ID) is None


@pytest.mark.approved_postgres
def test_runtime_approval_denies_limits_wider_than_bound_rule(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        _add_source_policy(session)
        _add_rule(session)
        _add_runtime_approval(session)
        approval = session.get(SourceRuntimeApproval, SOURCE_ID)
        assert approval is not None
        approval.limits = {**_limits(), "max_response_bytes": 2_097_152}
    with session_factory.begin() as session:
        assert load_source_runtime_approval(session, SOURCE_ID) is None


@pytest.mark.approved_postgres
def test_two_owner_receipts_share_one_source_policy_revision(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        decision = _add_source_policy(session)
        for owner in (OWNER_A, OWNER_B):
            session.add(
                PrivateDeletionOwnerState(
                    owner_user_id=owner,
                    latest_epoch=0,
                    account_deleted=False,
                )
            )
            session.add(
                SourceRegistrationReceipt(
                    command_id=uuid4(),
                    job_id=uuid4(),
                    authenticated_owner_ref=owner,
                    project_ref=None,
                    company_id=COMPANY_A,
                    source_id=SOURCE_ID,
                    execution_fence=1,
                    owner_deletion_epoch=0,
                    registration_digest="a" * 64,
                    status="READY",
                    reason_code="APPROVED",
                    policy_revision=decision.revision,
                    approval_rule_id=RULE_A,
                    approval_rule_revision=1,
                    created_at=NOW,
                )
            )
        _add_rule(session)
    with session_factory.begin() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourcePolicyDecision)
                .where(SourcePolicyDecision.source_id == SOURCE_ID)
            )
            == 1
        )


@pytest.mark.approved_postgres
def test_concurrent_duplicate_policy_candidates_reuse_one_source_revision(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        session.add(
            Company(
                company_id=COMPANY_A,
                legal_name="Synthetic Company",
                aliases=[],
                official_domains=["company.test"],
                legal_identifiers={"corp": str(COMPANY_A)},
                identity_status="verified",
                identity_evidence=[f"evidence:{COMPANY_A}"],
            )
        )
        session.add(
            Source(
                source_id=SOURCE_ID,
                company_id=COMPANY_A,
                source_type=SourceType.JOB_POSTING.value,
                canonical_url="https://careers.company.test/jobs",
            )
        )

    first_wrote = Event()
    release_first = Event()
    second_started = Event()
    second_finished = Event()
    errors: list[BaseException] = []
    returned_ids: list[UUID] = []

    def candidate() -> SourcePolicyDecision:
        return SourcePolicyDecision(
            policy_decision_id=uuid4(),
            source_id=SOURCE_ID,
            revision=1,
            official_status="verified",
            access_class="public",
            collection_permission="allowed",
            excerpt_storage_permission="allowed",
            body_storage_permission="denied",
            redistribution_permission="denied",
            evidence_refs=["policy:evidence"],
            checked_at=NOW,
            policy_version="policy-v1",
        )

    def first_write() -> None:
        try:
            with session_factory.begin() as session:
                returned_ids.append(
                    append_or_reuse_source_policy_decision(
                        session,
                        candidate(),
                    ).policy_decision_id
                )
                first_wrote.set()
                if not release_first.wait(timeout=10):
                    raise TimeoutError("test did not release first policy transaction")
        except BaseException as error:
            errors.append(error)
            first_wrote.set()

    def second_write() -> None:
        second_started.set()
        try:
            with session_factory.begin() as session:
                returned_ids.append(
                    append_or_reuse_source_policy_decision(
                        session,
                        candidate(),
                    ).policy_decision_id
                )
        except BaseException as error:
            errors.append(error)
        finally:
            second_finished.set()

    first = Thread(target=first_write)
    second = Thread(target=second_write)
    first.start()
    try:
        assert first_wrote.wait(timeout=10)
        assert not errors
        second.start()
        assert second_started.wait(timeout=10)
        assert not second_finished.wait(timeout=0.3)
        release_first.set()
        first.join(timeout=10)
        second.join(timeout=10)
    finally:
        release_first.set()
        first.join(timeout=10)
        if second.ident is not None:
            second.join(timeout=10)

    assert not first.is_alive()
    assert not second.is_alive()
    assert not errors
    assert len(returned_ids) == 2
    assert returned_ids[0] == returned_ids[1]
    with session_factory.begin() as session:
        decisions = list(
            session.scalars(
                select(SourcePolicyDecision).where(SourcePolicyDecision.source_id == SOURCE_ID)
            )
        )
        assert len(decisions) == 1
        assert decisions[0].revision == 1


@pytest.mark.approved_postgres
def test_private_receipt_rejects_status_reason_mismatch(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            session.add(
                PrivateDeletionOwnerState(
                    owner_user_id=OWNER_A,
                    latest_epoch=0,
                    account_deleted=False,
                )
            )
            session.add(
                SourceRegistrationReceipt(
                    command_id=uuid4(),
                    job_id=uuid4(),
                    authenticated_owner_ref=OWNER_A,
                    project_ref=None,
                    company_id=COMPANY_A,
                    source_id=SOURCE_ID,
                    execution_fence=1,
                    owner_deletion_epoch=0,
                    registration_digest="a" * 64,
                    status="HELD",
                    reason_code="APPROVED",
                    policy_revision=None,
                    approval_rule_id=None,
                    approval_rule_revision=None,
                    created_at=NOW,
                )
            )


@pytest.mark.approved_postgres
def test_owner_deletion_state_and_rule_head_are_lockable(
    database_engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        session.add(
            PrivateDeletionOwnerState(
                owner_user_id=OWNER_A,
                latest_epoch=0,
                account_deleted=False,
            )
        )
        _add_rule(session)

    first = session_factory()
    second = session_factory()
    try:
        first.begin()
        assert (
            match_approved_rule(
                first,
                _metadata("https://careers.company.test/jobs"),
            )
            is not None
        )
        assert (
            first.scalar(
                select(PrivateDeletionOwnerState)
                .where(PrivateDeletionOwnerState.owner_user_id == OWNER_A)
                .with_for_update()
            )
            is not None
        )
        with pytest.raises(OperationalError):
            with second.begin():
                second.scalar(
                    select(SourceApprovalRuleHead)
                    .where(SourceApprovalRuleHead.approval_rule_id == RULE_A)
                    .with_for_update(nowait=True)
                )
        second.rollback()
        with pytest.raises(OperationalError):
            with second.begin():
                second.scalar(
                    select(PrivateDeletionOwnerState)
                    .where(PrivateDeletionOwnerState.owner_user_id == OWNER_A)
                    .with_for_update(nowait=True)
                )
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()


@pytest.mark.approved_postgres
def test_0013_to_0014_preserves_existing_source_and_private_receipt(
    approved_postgres_url: URL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _migration_schema(approved_postgres_url, monkeypatch) as (engine, config):
        alembic_command.upgrade(config, "0013_deletion_ack_confirmed")
        deletion_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO companies (company_id, legal_name, aliases, official_domains, "
                    "legal_identifiers, identity_status, identity_evidence) VALUES "
                    "(:company_id, 'Synthetic', '{}', '{company.test}', '{}'::jsonb, "
                    "'verified', '{evidence}')"
                ),
                {"company_id": COMPANY_A},
            )
            connection.execute(
                text(
                    "INSERT INTO sources (source_id, company_id, source_type, canonical_url) "
                    "VALUES (:source_id, :company_id, 'job_posting', "
                    "'https://careers.company.test/jobs')"
                ),
                {"source_id": SOURCE_ID, "company_id": COMPANY_A},
            )
            connection.execute(
                text(
                    "INSERT INTO private_deletion_owner_states "
                    "(owner_user_id, latest_epoch, account_deleted) VALUES (:owner_id, 1, false)"
                ),
                {"owner_id": OWNER_A},
            )
            connection.execute(
                text(
                    "INSERT INTO private_deletion_receipts "
                    "(deletion_id, owner_user_id, deletion_epoch, contract_version, "
                    "command_digest, outcome, created_at, ack_confirmed_at) VALUES "
                    "(:deletion_id, :owner_id, 1, 'w2.private-deletion.v2', :digest, "
                    "'APPLIED', now(), now())"
                ),
                {"deletion_id": deletion_id, "owner_id": OWNER_A, "digest": "b" * 64},
            )

        alembic_command.upgrade(config, "0014_source_onboarding")

        with engine.begin() as connection:
            assert (
                connection.scalar(
                    text("SELECT canonical_url FROM sources WHERE source_id = :source_id"),
                    {"source_id": SOURCE_ID},
                )
                == "https://careers.company.test/jobs"
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT ack_confirmed_at IS NOT NULL FROM private_deletion_receipts "
                        "WHERE deletion_id = :deletion_id"
                    ),
                    {"deletion_id": deletion_id},
                )
                is True
            )
            assert MigrationContext.configure(connection).get_current_revision() == (
                "0014_source_onboarding"
            )


@pytest.mark.approved_postgres
def test_0014_requires_rule_bound_runtime_rows_and_denies_revision_mutation(
    approved_postgres_url: URL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _migration_schema(approved_postgres_url, monkeypatch) as (engine, config):
        alembic_command.upgrade(config, "0014_source_onboarding")

        runtime_columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("source_runtime_approvals")
        }
        assert runtime_columns["approval_rule_id"]["nullable"] is False
        assert runtime_columns["approval_rule_revision"]["nullable"] is False

        with Session(engine) as session, session.begin():
            _add_rule(session)

        for statement in (
            "UPDATE source_approval_rule_revisions SET policy_version = 'mutated' ",
            "DELETE FROM source_approval_rule_revisions ",
        ):
            with pytest.raises(DBAPIError, match="approval rule revisions are immutable"):
                with engine.begin() as connection:
                    connection.execute(
                        text(statement + "WHERE approval_rule_id = :rule_id AND revision = 1"),
                        {"rule_id": RULE_A},
                    )
