"""Lifecycle boundaries between direct Source registration and private deletion."""

from __future__ import annotations

import json
from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from epick_engine.source_collection.contracts import SourceType
from epick_engine.source_collection.persistence import (
    Base,
    CollectionRuntimeAttempt,
    OutboxEvent,
    PrivateDeletionOwnerState,
    Source,
    SourceApprovalRuleHead,
    SourceApprovalRuleRevision,
    SourcePolicyDecision,
    SourceRegistrationAckOutbox,
    SourceRegistrationReceipt,
    SourceVersion,
    apply_private_deletion_v2,
)
from epick_engine.source_collection.private_deletion_v2 import (
    PrivateDeletionCommandV2,
    PrivateDeletionScope,
)
from epick_engine.source_collection.private_scope import (
    PrivateScopeRejected,
    PrivateWriteAuthorityDecision,
    PrivateWriteScope,
)
from epick_engine.source_collection.source_onboarding_contracts import RegistrationMetadata
from epick_engine.source_collection.source_onboarding_store import register_direct_source
from epick_engine.source_collection.w1_transport import (
    W1DirectSourceRegistrationDispatch,
    parse_w1_dispatch,
)

pytestmark = pytest.mark.approved_postgres

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "w1_private_contract"
    / "private-w2-direct-source-registration-dispatch.json"
)
NOW = datetime(2032, 2, 3, 4, 5, tzinfo=UTC)
OWNER_A = UUID("00000000-0000-4000-8000-000000008501")
OWNER_B = UUID("00000000-0000-4000-8000-000000008502")
PROJECT_A = UUID("00000000-0000-4000-8000-000000008511")
COMPANY_ID = UUID("00000000-0000-4000-8000-000000008521")
SOURCE_ID = UUID("00000000-0000-4000-8000-000000008522")
RULE_ID = UUID("00000000-0000-4000-8000-000000008523")
CANONICAL_URL = "https://careers.lifecycle.test/jobs"


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
    schema_name = f"epick_onboarding_lifecycle_{uuid4().hex}"
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
    owner_id: UUID,
    project_id: UUID | None,
    owner_deletion_epoch: int = 0,
) -> W1DirectSourceRegistrationDispatch:
    raw = deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
    command_id, job_id = uuid4(), uuid4()
    raw["message_id"] = str(command_id)
    raw["payload"].update(
        command_id=str(command_id),
        job_id=str(job_id),
        authenticated_owner_ref=str(owner_id),
        project_ref=str(project_id) if project_id is not None else None,
        company_id=str(COMPANY_ID),
        source_id=str(SOURCE_ID),
        owner_deletion_epoch=owner_deletion_epoch,
    )
    raw["lookup_request"].update(
        command_id=str(command_id),
        owner_deletion_epoch=owner_deletion_epoch,
    )
    raw["direct_source_registration_pin"].update(
        registration_decision_id=str(uuid4()),
        company_id=str(COMPANY_ID),
        source_id=str(SOURCE_ID),
        registration_input_version=f"direct:{SOURCE_ID}:1",
    )
    parsed = parse_w1_dispatch(raw)
    assert isinstance(parsed, W1DirectSourceRegistrationDispatch)
    return parsed


def _metadata(dispatch: W1DirectSourceRegistrationDispatch) -> RegistrationMetadata:
    command = dispatch.payload
    return RegistrationMetadata(
        schema_version="w1.private.w2-source-registration-lookup.v1",
        status="AVAILABLE",
        command_id=command.command_id,
        execution_fence=dispatch.lookup_request.execution_fence,
        owner_deletion_epoch=command.owner_deletion_epoch,
        company_id=command.company_id,
        source_id=command.source_id,
        canonical_url=CANONICAL_URL,
        w1_source_type="JOB_POSTING",
        registration_input_version=(
            dispatch.direct_source_registration_pin.registration_input_version
        ),
        company_legal_name="Synthetic Lifecycle Company Ltd.",
        company_official_domain="lifecycle.test",
        company_legal_identifiers=[f"corp:{COMPANY_ID}"],
        company_identity_evidence_refs=[f"evidence:{COMPANY_ID}"],
    )


def _scope(dispatch: W1DirectSourceRegistrationDispatch) -> PrivateWriteScope:
    command = dispatch.payload
    project_id = UUID(command.project_ref) if command.project_ref is not None else None
    return PrivateWriteScope(
        PrivateWriteAuthorityDecision(
            owner_user_id=command.authenticated_owner_ref,
            owner_deletion_epoch=command.owner_deletion_epoch,
            scope=PrivateDeletionScope(
                kind="PROJECT" if project_id is not None else "ACCOUNT",
                project_id=project_id,
            ),
            authority_ref="w1:test-source-onboarding-lifecycle",
            command_id=command.command_id,
            job_id=command.job_id,
        )
    )


def _add_rule(session: Session) -> None:
    session.add(
        SourceApprovalRuleHead(
            approval_rule_id=RULE_ID,
            current_revision=1,
            is_active=True,
            updated_at=NOW,
        )
    )
    session.add(
        SourceApprovalRuleRevision(
            approval_rule_id=RULE_ID,
            revision=1,
            company_id=COMPANY_ID,
            company_official_domain="lifecycle.test",
            company_legal_identifiers=[f"corp:{COMPANY_ID}"],
            company_identity_evidence_refs=[f"evidence:{COMPANY_ID}"],
            exact_host="careers.lifecycle.test",
            path_mode="SEGMENT_PREFIX",
            path_value="/jobs",
            allowed_query_strings=[""],
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


def _register(session: Session, dispatch: W1DirectSourceRegistrationDispatch) -> None:
    ack = register_direct_source(session, dispatch, _metadata(dispatch), _scope(dispatch), NOW)
    assert ack.status == "READY"
    assert ack.reason_code == "APPROVED"


def _add_existing_finalized_history(session: Session) -> tuple[UUID, UUID]:
    policy = session.scalar(
        select(SourcePolicyDecision).where(SourcePolicyDecision.source_id == SOURCE_ID)
    )
    assert policy is not None
    version_id, event_id = uuid4(), uuid4()
    session.add(
        SourceVersion(
            source_version_id=version_id,
            source_id=SOURCE_ID,
            company_id=COMPANY_ID,
            title="Synthetic lifecycle source",
            source_type=SourceType.JOB_POSTING.value,
            canonical_url=CANONICAL_URL,
            content_hash="a" * 64,
            hash_profile_version="test-v1",
            representation="html",
            first_parser_version="parser-v1",
            collected_at=NOW,
            published_at={"status": "unknown", "raw_text": None, "value": None},
            valid_from={"status": "unknown", "raw_text": None, "value": None},
            valid_to={"status": "unknown", "raw_text": None, "value": None},
            language="ko",
            policy_decision_id=policy.policy_decision_id,
        )
    )
    session.add(
        OutboxEvent(
            event_id=event_id,
            aggregate_id=SOURCE_ID,
            aggregate_revision=1,
            event_type="source.version.available",
            schema_version="w2.source-event.v1",
            payload={"source_id": str(SOURCE_ID), "source_version_id": str(version_id)},
            occurred_at=NOW,
            delivery_state="pending",
        )
    )
    return version_id, event_id


def _delete(
    session: Session,
    *,
    owner_id: UUID,
    kind: Literal["ACCOUNT", "PROJECT"],
    project_id: UUID | None,
) -> str:
    return apply_private_deletion_v2(
        session,
        PrivateDeletionCommandV2(
            deletion_id=uuid4(),
            owner_user_id=owner_id,
            deletion_epoch=1,
            scope=PrivateDeletionScope(kind=kind, project_id=project_id),
        ),
    )


def test_account_deletion_purges_only_owner_registration_and_preserves_public_history(
    session_factory: sessionmaker[Session],
) -> None:
    dispatch_a = _dispatch(owner_id=OWNER_A, project_id=None)
    dispatch_b = _dispatch(owner_id=OWNER_B, project_id=None)
    with session_factory.begin() as session:
        _add_rule(session)
        _register(session, dispatch_a)
        _register(session, dispatch_b)
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
        version_id, event_id = _add_existing_finalized_history(session)

    with session_factory.begin() as session:
        assert _delete(session, owner_id=OWNER_A, kind="ACCOUNT", project_id=None) == "APPLIED"

    with session_factory() as session:
        assert session.get(SourceRegistrationReceipt, dispatch_a.payload.command_id) is None
        assert (
            session.scalar(
                select(SourceRegistrationAckOutbox).where(
                    SourceRegistrationAckOutbox.command_id == dispatch_a.payload.command_id
                )
            )
            is None
        )
        assert session.get(SourceRegistrationReceipt, dispatch_b.payload.command_id) is not None
        assert (
            session.scalar(
                select(SourceRegistrationAckOutbox).where(
                    SourceRegistrationAckOutbox.command_id == dispatch_b.payload.command_id
                )
            )
            is not None
        )
        source = session.get(Source, SOURCE_ID)
        assert source is not None
        assert source.company_id == COMPANY_ID
        assert source.canonical_url == CANONICAL_URL
        assert session.get(SourceVersion, version_id) is not None
        event = session.get(OutboxEvent, event_id)
        assert event is not None
        assert event.aggregate_id == SOURCE_ID
        assert event.aggregate_revision == 1


def test_project_tombstone_rejects_late_registration_without_recreating_private_state(
    session_factory: sessionmaker[Session],
) -> None:
    original = _dispatch(owner_id=OWNER_A, project_id=PROJECT_A)
    with session_factory.begin() as session:
        _add_rule(session)
        _register(session, original)

    with session_factory.begin() as session:
        assert _delete(session, owner_id=OWNER_A, kind="PROJECT", project_id=PROJECT_A) == "APPLIED"

    late = _dispatch(
        owner_id=OWNER_A,
        project_id=PROJECT_A,
        owner_deletion_epoch=1,
    )
    with pytest.raises(PrivateScopeRejected, match="project tombstone"):
        with session_factory.begin() as session:
            _register(session, late)

    with session_factory() as session:
        owner_state = session.get(PrivateDeletionOwnerState, OWNER_A)
        assert owner_state is not None and owner_state.latest_epoch == 1
        assert session.get(SourceRegistrationReceipt, original.payload.command_id) is None
        assert session.get(SourceRegistrationReceipt, late.payload.command_id) is None
        assert (
            session.scalar(
                select(SourceRegistrationAckOutbox).where(
                    SourceRegistrationAckOutbox.command_id.in_(
                        [original.payload.command_id, late.payload.command_id]
                    )
                )
            )
            is None
        )
        assert session.get(Source, SOURCE_ID) is not None
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
        assert session.scalar(select(func.count()).select_from(CollectionRuntimeAttempt)) == 0
