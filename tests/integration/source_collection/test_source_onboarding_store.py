from __future__ import annotations

import json
from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from epick_engine.source_collection.contracts import SourceType
from epick_engine.source_collection.persistence import (
    Base,
    Company,
    PersistenceConflict,
    PrivateDeletionOwnerState,
    Source,
    SourceApprovalRuleHead,
    SourceApprovalRuleRevision,
    SourcePolicyDecision,
    SourceRegistrationAckOutbox,
    SourceRegistrationReceipt,
    SourceRuntimeApproval,
)
from epick_engine.source_collection.private_deletion_v2 import PrivateDeletionScope
from epick_engine.source_collection.private_scope import (
    PrivateScopeRejected,
    PrivateWriteAuthorityDecision,
    PrivateWriteScope,
)
from epick_engine.source_collection.source_onboarding_contracts import (
    RegistrationMetadata,
    registration_digest,
)
from epick_engine.source_collection.source_onboarding_policy import (
    load_source_runtime_approval,
)
from epick_engine.source_collection.source_onboarding_store import (
    confirm_registration_ack,
    register_direct_source,
)
from epick_engine.source_collection.w1_transport import (
    W1DirectSourceRegistrationDispatch,
    parse_w1_dispatch,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "w1_private_contract"
    / "private-w2-direct-source-registration-dispatch.json"
)
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
COMPANY_A = UUID("00000000-0000-4000-8000-00000000c501")
COMPANY_B = UUID("00000000-0000-4000-8000-00000000c502")
SOURCE_A = UUID("00000000-0000-4000-8000-00000000c503")
SOURCE_B = UUID("00000000-0000-4000-8000-00000000c504")
RULE_A = UUID("00000000-0000-4000-8000-00000000c505")
RULE_B = UUID("00000000-0000-4000-8000-00000000c506")
RULE_PROFILE = UUID("00000000-0000-4000-8000-00000000c507")
OWNER_A = UUID("00000000-0000-4000-8000-00000000c508")
OWNER_B = UUID("00000000-0000-4000-8000-00000000c509")


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
    schema_name = f"epick_source_onboarding_store_{uuid4().hex}"
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


def _dispatch(
    *,
    command_id: UUID | None = None,
    job_id: UUID | None = None,
    owner_id: UUID = OWNER_A,
    company_id: UUID = COMPANY_A,
    source_id: UUID = SOURCE_A,
    owner_deletion_epoch: int = 0,
) -> W1DirectSourceRegistrationDispatch:
    raw = deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
    command_id = command_id or uuid4()
    job_id = job_id or uuid4()
    input_version = f"direct:{source_id}:1"
    raw["message_id"] = str(command_id)
    raw["payload"].update(
        command_id=str(command_id),
        job_id=str(job_id),
        authenticated_owner_ref=str(owner_id),
        company_id=str(company_id),
        source_id=str(source_id),
        owner_deletion_epoch=owner_deletion_epoch,
    )
    raw["lookup_request"].update(
        command_id=str(command_id),
        owner_deletion_epoch=owner_deletion_epoch,
    )
    raw["direct_source_registration_pin"].update(
        registration_decision_id=str(uuid4()),
        company_id=str(company_id),
        source_id=str(source_id),
        registration_input_version=input_version,
    )
    parsed = parse_w1_dispatch(raw)
    assert isinstance(parsed, W1DirectSourceRegistrationDispatch)
    return parsed


def _metadata(
    dispatch: W1DirectSourceRegistrationDispatch,
    *,
    canonical_url: str = "https://careers.synthetic.test/jobs",
    w1_source_type: str = "JOB_POSTING",
    official_domain: str = "synthetic.test",
    legal_name: str = "Synthetic Company A Ltd.",
    legal_identifiers: list[str] | None = None,
) -> RegistrationMetadata:
    command = dispatch.payload
    return RegistrationMetadata(
        schema_version="w1.private.w2-source-registration-lookup.v1",
        status="AVAILABLE",
        command_id=command.command_id,
        execution_fence=dispatch.lookup_request.execution_fence,
        owner_deletion_epoch=command.owner_deletion_epoch,
        company_id=command.company_id,
        source_id=command.source_id,
        canonical_url=canonical_url,
        w1_source_type=w1_source_type,
        registration_input_version=(
            dispatch.direct_source_registration_pin.registration_input_version
        ),
        company_legal_name=legal_name,
        company_official_domain=official_domain,
        company_legal_identifiers=(
            legal_identifiers if legal_identifiers is not None else [f"corp:{command.company_id}"]
        ),
        company_identity_evidence_refs=[f"evidence:{command.company_id}"],
    )


def _private_scope(dispatch: W1DirectSourceRegistrationDispatch) -> PrivateWriteScope:
    command = dispatch.payload
    return PrivateWriteScope(
        PrivateWriteAuthorityDecision(
            owner_user_id=command.authenticated_owner_ref,
            owner_deletion_epoch=command.owner_deletion_epoch,
            scope=PrivateDeletionScope(kind="ACCOUNT", project_id=None),
            authority_ref="authority:synthetic",
            command_id=command.command_id,
            job_id=command.job_id,
        )
    )


def _add_company(session: Session, company_id: UUID, domain: str) -> None:
    session.add(
        Company(
            company_id=company_id,
            legal_name=f"Synthetic Company {company_id}",
            aliases=[],
            official_domains=[domain],
            legal_identifiers={"corp": str(company_id)},
            identity_status="verified",
            identity_evidence=[f"evidence:{company_id}"],
        )
    )


def _add_rule(
    session: Session,
    *,
    rule_id: UUID = RULE_A,
    company_id: UUID = COMPANY_A,
    official_domain: str = "synthetic.test",
    host: str = "careers.synthetic.test",
    path: str = "/jobs",
    source_type: SourceType = SourceType.JOB_POSTING,
    legal_identifiers: list[str] | None = None,
) -> None:
    session.add(
        SourceApprovalRuleHead(
            approval_rule_id=rule_id,
            current_revision=1,
            is_active=True,
            updated_at=NOW,
        )
    )
    session.add(
        SourceApprovalRuleRevision(
            approval_rule_id=rule_id,
            revision=1,
            company_id=company_id,
            company_official_domain=official_domain,
            company_legal_identifiers=(
                legal_identifiers if legal_identifiers is not None else [f"corp:{company_id}"]
            ),
            company_identity_evidence_refs=[f"evidence:{company_id}"],
            exact_host=host,
            path_mode="SEGMENT_PREFIX",
            path_value=path,
            allowed_query_strings=[""],
            source_type=source_type.value,
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


def _seed_ready_prerequisites(session: Session) -> None:
    _add_rule(session)


def _register(
    session: Session,
    dispatch: W1DirectSourceRegistrationDispatch,
    metadata: RegistrationMetadata,
):
    return register_direct_source(
        session,
        dispatch,
        metadata,
        _private_scope(dispatch),
        NOW,
    )


@pytest.mark.approved_postgres
def test_same_command_and_digest_replay_reuses_receipt_and_ack(
    session_factory: sessionmaker[Session],
) -> None:
    dispatch = _dispatch()
    legal_identifiers = ["corp:synthetic-z", "registry:42", "corp:synthetic-a"]
    metadata = _metadata(dispatch, legal_identifiers=legal_identifiers)
    with session_factory.begin() as session:
        _add_rule(session, legal_identifiers=legal_identifiers)
        first = _register(session, dispatch, metadata)
    with session_factory.begin() as session:
        replay = _register(session, dispatch, metadata)

    assert replay == first
    assert replay.status == "READY"
    with session_factory.begin() as session:
        company = session.get(Company, COMPANY_A)
        assert company is not None
        assert company.legal_name == "Synthetic Company A Ltd."
        assert company.legal_identifiers == {
            "corp": ["synthetic-a", "synthetic-z"],
            "registry": "42",
        }
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(SourcePolicyDecision)) == 1
        assert session.scalar(select(func.count()).select_from(SourceRuntimeApproval)) == 1
        assert session.scalar(select(func.count()).select_from(SourceRegistrationReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(SourceRegistrationAckOutbox)) == 1
        assert load_source_runtime_approval(session, SOURCE_A) is not None
        outbox = session.scalar(select(SourceRegistrationAckOutbox))
        assert outbox is not None
        assert "canonical_url" not in outbox.payload


@pytest.mark.approved_postgres
@pytest.mark.parametrize("changed", ["url", "company", "type"])
def test_same_source_id_with_different_public_identity_is_rejected_without_overwrite(
    session_factory: sessionmaker[Session],
    changed: str,
) -> None:
    original_dispatch = _dispatch()
    original_metadata = _metadata(original_dispatch)
    with session_factory.begin() as session:
        _seed_ready_prerequisites(session)
        _add_company(session, COMPANY_B, "subsidiary.test")
        _add_rule(
            session,
            rule_id=RULE_B,
            company_id=COMPANY_B,
            official_domain="subsidiary.test",
            host="careers.subsidiary.test",
        )
        _add_rule(
            session,
            rule_id=RULE_PROFILE,
            host="www.synthetic.test",
            path="/about",
            source_type=SourceType.COMPANY_WEBSITE,
        )
        assert _register(session, original_dispatch, original_metadata).status == "READY"

    company_id = COMPANY_B if changed == "company" else COMPANY_A
    conflict_dispatch = _dispatch(company_id=company_id, source_id=SOURCE_A)
    if changed == "url":
        conflict_metadata = _metadata(
            conflict_dispatch,
            canonical_url="https://careers.synthetic.test/jobs/changed",
        )
    elif changed == "company":
        conflict_metadata = _metadata(
            conflict_dispatch,
            canonical_url="https://careers.subsidiary.test/jobs",
            official_domain="subsidiary.test",
            legal_name=f"Synthetic Company {COMPANY_B}",
        )
    else:
        conflict_metadata = _metadata(
            conflict_dispatch,
            canonical_url="https://www.synthetic.test/about",
            w1_source_type="COMPANY_PROFILE",
        )

    with session_factory.begin() as session:
        ack = _register(session, conflict_dispatch, conflict_metadata)

    assert ack.status == "REJECTED"
    assert ack.reason_code == "SOURCE_ID_CONFLICT"
    with session_factory.begin() as session:
        source = session.get(Source, SOURCE_A)
        assert source is not None
        assert source.company_id == COMPANY_A
        assert source.source_type == SourceType.JOB_POSTING.value
        assert source.canonical_url == original_metadata.canonical_url
        assert session.scalar(select(func.count()).select_from(Source)) == 1


@pytest.mark.approved_postgres
@pytest.mark.parametrize("changed", ["url", "company", "type"])
def test_same_source_id_conflict_is_rejected_even_without_an_approval_rule(
    session_factory: sessionmaker[Session],
    changed: str,
) -> None:
    with session_factory.begin() as session:
        _add_company(session, COMPANY_A, "synthetic.test")
        _add_company(session, COMPANY_B, "subsidiary.test")
        session.add(
            Source(
                source_id=SOURCE_A,
                company_id=COMPANY_A,
                source_type=SourceType.JOB_POSTING.value,
                canonical_url="https://careers.synthetic.test/jobs",
                title=None,
                pointer_update_mode="FINALIZE_GATE",
            )
        )

    company_id = COMPANY_B if changed == "company" else COMPANY_A
    dispatch = _dispatch(company_id=company_id, source_id=SOURCE_A)
    if changed == "url":
        metadata = _metadata(
            dispatch,
            canonical_url="https://careers.synthetic.test/jobs/changed",
        )
    elif changed == "company":
        metadata = _metadata(
            dispatch,
            canonical_url="https://careers.subsidiary.test/jobs",
            official_domain="subsidiary.test",
            legal_name=f"Synthetic Company {COMPANY_B}",
        )
    else:
        metadata = _metadata(
            dispatch,
            canonical_url="https://www.synthetic.test/about",
            w1_source_type="COMPANY_PROFILE",
        )

    with session_factory.begin() as session:
        ack = _register(session, dispatch, metadata)

    assert ack.status == "REJECTED"
    assert ack.reason_code == "SOURCE_ID_CONFLICT"
    with session_factory.begin() as session:
        source = session.get(Source, SOURCE_A)
        assert source is not None
        assert source.company_id == COMPANY_A
        assert source.source_type == SourceType.JOB_POSTING.value
        assert source.canonical_url == "https://careers.synthetic.test/jobs"
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(SourcePolicyDecision)) == 0


@pytest.mark.approved_postgres
def test_same_company_url_with_different_source_id_is_rejected_without_alias(
    session_factory: sessionmaker[Session],
) -> None:
    first_dispatch = _dispatch(source_id=SOURCE_A)
    second_dispatch = _dispatch(source_id=SOURCE_B)
    first_metadata = _metadata(first_dispatch)
    second_metadata = _metadata(second_dispatch)
    with session_factory.begin() as session:
        _seed_ready_prerequisites(session)
        assert _register(session, first_dispatch, first_metadata).status == "READY"
    with session_factory.begin() as session:
        ack = _register(session, second_dispatch, second_metadata)

    assert ack.status == "REJECTED"
    assert ack.reason_code == "CANONICAL_URL_CONFLICT"
    with session_factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.get(Source, SOURCE_B) is None


@pytest.mark.approved_postgres
def test_same_company_url_conflict_is_rejected_even_without_an_approval_rule(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        _add_company(session, COMPANY_A, "synthetic.test")
        session.add(
            Source(
                source_id=SOURCE_A,
                company_id=COMPANY_A,
                source_type=SourceType.JOB_POSTING.value,
                canonical_url="https://careers.synthetic.test/jobs",
                title=None,
                pointer_update_mode="FINALIZE_GATE",
            )
        )

    dispatch = _dispatch(source_id=SOURCE_B)
    with session_factory.begin() as session:
        ack = _register(session, dispatch, _metadata(dispatch))

    assert ack.status == "REJECTED"
    assert ack.reason_code == "CANONICAL_URL_CONFLICT"
    with session_factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.get(Source, SOURCE_B) is None
        assert session.scalar(select(func.count()).select_from(SourcePolicyDecision)) == 0


@pytest.mark.approved_postgres
def test_different_owners_share_one_public_source_and_policy_revision(
    session_factory: sessionmaker[Session],
) -> None:
    first_dispatch = _dispatch(owner_id=OWNER_A)
    second_dispatch = _dispatch(owner_id=OWNER_B)
    with session_factory.begin() as session:
        _seed_ready_prerequisites(session)
        first = _register(session, first_dispatch, _metadata(first_dispatch))
    with session_factory.begin() as session:
        second = _register(session, second_dispatch, _metadata(second_dispatch))

    assert first.status == second.status == "READY"
    assert first.policy_revision == second.policy_revision == 1
    with session_factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(SourcePolicyDecision)) == 1
        assert session.scalar(select(func.count()).select_from(SourceRegistrationReceipt)) == 2
        assert session.scalar(select(func.count()).select_from(SourceRegistrationAckOutbox)) == 2


@pytest.mark.approved_postgres
def test_concurrent_first_sources_share_one_company_without_unique_failure(
    session_factory: sessionmaker[Session],
) -> None:
    first_dispatch = _dispatch(owner_id=OWNER_A, source_id=SOURCE_A)
    second_dispatch = _dispatch(owner_id=OWNER_B, source_id=SOURCE_B)
    first_metadata = _metadata(first_dispatch)
    second_metadata = _metadata(
        second_dispatch,
        canonical_url="https://www.synthetic.test/about",
        w1_source_type="COMPANY_PROFILE",
    )
    with session_factory.begin() as session:
        _add_rule(session)
        _add_rule(
            session,
            rule_id=RULE_PROFILE,
            host="www.synthetic.test",
            path="/about",
            source_type=SourceType.COMPANY_WEBSITE,
        )

    first_registered = Event()
    release_first = Event()
    second_started = Event()
    second_finished = Event()
    errors: list[BaseException] = []
    statuses: list[str] = []

    def first_registration() -> None:
        try:
            with session_factory.begin() as session:
                statuses.append(_register(session, first_dispatch, first_metadata).status)
                first_registered.set()
                if not release_first.wait(timeout=10):
                    raise TimeoutError("test did not release the first registration")
        except BaseException as error:
            errors.append(error)
            first_registered.set()

    def second_registration() -> None:
        second_started.set()
        try:
            with session_factory.begin() as session:
                statuses.append(_register(session, second_dispatch, second_metadata).status)
        except BaseException as error:
            errors.append(error)
        finally:
            second_finished.set()

    first = Thread(target=first_registration)
    second = Thread(target=second_registration)
    first.start()
    try:
        assert first_registered.wait(timeout=10)
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
    assert statuses == ["READY", "READY"]
    with session_factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 1
        assert session.scalar(select(func.count()).select_from(Source)) == 2


@pytest.mark.approved_postgres
def test_no_rule_is_held_and_writes_private_state_only(
    session_factory: sessionmaker[Session],
) -> None:
    dispatch = _dispatch()
    metadata = _metadata(dispatch)
    with session_factory.begin() as session:
        ack = _register(session, dispatch, metadata)

    assert ack.status == "HELD"
    assert ack.reason_code == "POLICY_RULE_MISSING"
    with session_factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 0
        assert session.scalar(select(func.count()).select_from(Source)) == 0
        assert session.scalar(select(func.count()).select_from(SourcePolicyDecision)) == 0
        assert session.scalar(select(func.count()).select_from(SourceRuntimeApproval)) == 0
        assert session.scalar(select(func.count()).select_from(SourceRegistrationReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(SourceRegistrationAckOutbox)) == 1


@pytest.mark.approved_postgres
def test_existing_company_identity_conflict_is_held_without_public_source(
    session_factory: sessionmaker[Session],
) -> None:
    dispatch = _dispatch()
    with session_factory.begin() as session:
        _add_company(session, COMPANY_A, "synthetic.test")
        _add_rule(session)
        ack = _register(session, dispatch, _metadata(dispatch))

    assert ack.status == "HELD"
    assert ack.reason_code == "COMPANY_UNVERIFIED"
    with session_factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 1
        assert session.scalar(select(func.count()).select_from(Source)) == 0
        assert session.scalar(select(func.count()).select_from(SourcePolicyDecision)) == 0
        assert session.scalar(select(func.count()).select_from(SourceRuntimeApproval)) == 0


@pytest.mark.approved_postgres
def test_existing_company_identifier_kind_with_colon_is_held_without_public_mutation(
    session_factory: sessionmaker[Session],
) -> None:
    dispatch = _dispatch()
    legal_identifiers = ["corp:sub:x"]
    with session_factory.begin() as session:
        session.add(
            Company(
                company_id=COMPANY_A,
                legal_name="Synthetic Company A Ltd.",
                aliases=[],
                official_domains=["synthetic.test"],
                legal_identifiers={"corp:sub": "x"},
                identity_status="verified",
                identity_evidence=[f"evidence:{COMPANY_A}"],
            )
        )
        _add_rule(session, legal_identifiers=legal_identifiers)
        ack = _register(
            session,
            dispatch,
            _metadata(dispatch, legal_identifiers=legal_identifiers),
        )

    assert ack.status == "HELD"
    assert ack.reason_code == "COMPANY_UNVERIFIED"
    with session_factory.begin() as session:
        company = session.get(Company, COMPANY_A)
        assert company is not None
        assert company.legal_identifiers == {"corp:sub": "x"}
        assert session.scalar(select(func.count()).select_from(Source)) == 0
        assert session.scalar(select(func.count()).select_from(SourcePolicyDecision)) == 0
        assert session.scalar(select(func.count()).select_from(SourceRuntimeApproval)) == 0


@pytest.mark.approved_postgres
def test_existing_company_identifier_with_empty_extra_kind_is_held_without_public_mutation(
    session_factory: sessionmaker[Session],
) -> None:
    dispatch = _dispatch()
    legal_identifiers = ["corp:sub:x"]
    with session_factory.begin() as session:
        session.add(
            Company(
                company_id=COMPANY_A,
                legal_name="Synthetic Company A Ltd.",
                aliases=[],
                official_domains=["synthetic.test"],
                legal_identifiers={"corp": "sub:x", "unused": []},
                identity_status="verified",
                identity_evidence=[f"evidence:{COMPANY_A}"],
            )
        )
        _add_rule(session, legal_identifiers=legal_identifiers)
        ack = _register(
            session,
            dispatch,
            _metadata(dispatch, legal_identifiers=legal_identifiers),
        )

    assert ack.status == "HELD"
    assert ack.reason_code == "COMPANY_UNVERIFIED"
    with session_factory.begin() as session:
        company = session.get(Company, COMPANY_A)
        assert company is not None
        assert company.legal_identifiers == {"corp": "sub:x", "unused": []}
        assert session.scalar(select(func.count()).select_from(Source)) == 0
        assert session.scalar(select(func.count()).select_from(SourcePolicyDecision)) == 0
        assert session.scalar(select(func.count()).select_from(SourceRuntimeApproval)) == 0


@pytest.mark.approved_postgres
def test_existing_company_integer_identifier_preserves_legacy_exact_match(
    session_factory: sessionmaker[Session],
) -> None:
    dispatch = _dispatch()
    legal_identifiers = ["registry:42"]
    with session_factory.begin() as session:
        session.add(
            Company(
                company_id=COMPANY_A,
                legal_name="Synthetic Company A Ltd.",
                aliases=[],
                official_domains=["synthetic.test"],
                legal_identifiers={"registry": 42},
                identity_status="verified",
                identity_evidence=[f"evidence:{COMPANY_A}"],
            )
        )
        _add_rule(session, legal_identifiers=legal_identifiers)
        ack = _register(
            session,
            dispatch,
            _metadata(dispatch, legal_identifiers=legal_identifiers),
        )

    assert ack.status == "READY"
    assert ack.reason_code == "APPROVED"
    with session_factory.begin() as session:
        company = session.get(Company, COMPANY_A)
        assert company is not None
        assert company.legal_identifiers == {"registry": 42}
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(SourcePolicyDecision)) == 1
        assert session.scalar(select(func.count()).select_from(SourceRuntimeApproval)) == 1


@pytest.mark.approved_postgres
def test_same_command_with_changed_digest_is_an_immutable_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    dispatch = _dispatch()
    with session_factory.begin() as session:
        _seed_ready_prerequisites(session)
        assert _register(session, dispatch, _metadata(dispatch)).status == "READY"

    changed = _metadata(
        dispatch,
        canonical_url="https://careers.synthetic.test/jobs/changed",
    )
    with pytest.raises(PersistenceConflict, match="immutable payload"):
        with session_factory.begin() as session:
            _register(session, dispatch, changed)
    with session_factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(SourceRegistrationReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(SourceRegistrationAckOutbox)) == 1


@pytest.mark.approved_postgres
def test_concurrent_different_owners_same_command_is_an_immutable_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    command_id = uuid4()
    job_id = uuid4()
    first_dispatch = _dispatch(
        command_id=command_id,
        job_id=job_id,
        owner_id=OWNER_A,
    )
    second_dispatch = _dispatch(
        command_id=command_id,
        job_id=job_id,
        owner_id=OWNER_B,
    )
    second_started = Event()
    second_finished = Event()
    errors: list[BaseException] = []

    def second_registration() -> None:
        second_started.set()
        try:
            with session_factory.begin() as session:
                _register(session, second_dispatch, _metadata(second_dispatch))
        except BaseException as error:
            errors.append(error)
        finally:
            second_finished.set()

    first = session_factory()
    second = Thread(target=second_registration)
    try:
        first.begin()
        assert _register(first, first_dispatch, _metadata(first_dispatch)).status == "HELD"
        second.start()
        assert second_started.wait(timeout=10)
        assert not second_finished.wait(timeout=0.3)
        first.commit()
        second.join(timeout=10)
    finally:
        first.rollback()
        first.close()
        if second.ident is not None:
            second.join(timeout=10)

    assert not second.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], PersistenceConflict)
    assert "immutable payload" in str(errors[0])
    with session_factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(SourceRegistrationReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(SourceRegistrationAckOutbox)) == 1
        assert session.scalar(select(func.count()).select_from(Source)) == 0


@pytest.mark.approved_postgres
def test_registration_holds_owner_lock_and_stale_epoch_cannot_write(
    session_factory: sessionmaker[Session],
) -> None:
    dispatch = _dispatch(owner_deletion_epoch=0)
    with session_factory.begin() as session:
        _seed_ready_prerequisites(session)
        session.add(
            PrivateDeletionOwnerState(
                owner_user_id=OWNER_A,
                latest_epoch=0,
                account_deleted=False,
            )
        )

    first = session_factory()
    concurrent = session_factory()
    try:
        first.begin()
        assert _register(first, dispatch, _metadata(dispatch)).status == "READY"
        with pytest.raises(OperationalError):
            with concurrent.begin():
                concurrent.scalar(
                    select(PrivateDeletionOwnerState)
                    .where(PrivateDeletionOwnerState.owner_user_id == OWNER_A)
                    .with_for_update(nowait=True)
                )
        concurrent.rollback()
        first.commit()
    finally:
        first.close()
        concurrent.close()

    with session_factory.begin() as session:
        owner_state = session.get(PrivateDeletionOwnerState, OWNER_A)
        assert owner_state is not None
        owner_state.latest_epoch = 1

    stale_dispatch = _dispatch(owner_id=OWNER_A, owner_deletion_epoch=0)
    with pytest.raises(PrivateScopeRejected):
        with session_factory.begin() as session:
            _register(session, stale_dispatch, _metadata(stale_dispatch))
    with session_factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(SourceRegistrationReceipt)) == 1


@pytest.mark.approved_postgres
def test_ack_marker_rollback_leaves_pending_for_same_digest_retry(
    session_factory: sessionmaker[Session],
) -> None:
    dispatch = _dispatch()
    metadata = _metadata(dispatch)
    digest = registration_digest(metadata)
    with session_factory.begin() as session:
        _seed_ready_prerequisites(session)
        assert _register(session, dispatch, metadata).status == "READY"

    with pytest.raises(RuntimeError, match="synthetic marker failure"):
        with session_factory.begin() as session:
            confirm_registration_ack(session, dispatch.payload.command_id, digest, NOW)
            raise RuntimeError("synthetic marker failure")

    with session_factory.begin() as session:
        pending = session.scalar(select(SourceRegistrationAckOutbox))
        assert pending is not None
        assert pending.delivery_state == "PENDING"
        assert pending.delivered_at is None
        assert pending.ack_confirmed_at is None

    confirmed_at = NOW.replace(minute=1)
    with session_factory.begin() as session:
        confirm_registration_ack(
            session,
            dispatch.payload.command_id,
            digest,
            confirmed_at,
        )
    replayed_at = NOW.replace(minute=2)
    with session_factory.begin() as session:
        confirm_registration_ack(
            session,
            dispatch.payload.command_id,
            digest,
            replayed_at,
        )
    with session_factory.begin() as session:
        delivered = session.scalar(select(SourceRegistrationAckOutbox))
        assert delivered is not None
        assert delivered.delivery_state == "DELIVERED"
        assert delivered.delivered_at == confirmed_at
        assert delivered.ack_confirmed_at == confirmed_at

    with pytest.raises(PersistenceConflict, match="digest"):
        with session_factory.begin() as session:
            confirm_registration_ack(
                session,
                dispatch.payload.command_id,
                "f" * 64,
                confirmed_at,
            )
