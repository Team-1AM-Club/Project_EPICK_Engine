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
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from epick_engine.source_collection.contracts import SourceType
from epick_engine.source_collection.persistence import (
    Base,
    Company,
    Source,
    SourceApprovalRuleHead,
    SourceApprovalRuleRevision,
    SourcePolicyDecision,
    SourceRuntimeApproval,
)
from epick_engine.source_collection.source_onboarding_contracts import RegistrationMetadata
from epick_engine.source_collection.source_onboarding_operator import (
    ApprovedRuleManifest,
    RuleRevisionConflict,
    RuleScopeWidening,
    append_approved_rule,
    import_v1_config,
    main,
)
from epick_engine.source_collection.source_onboarding_policy import (
    load_source_runtime_approval,
    match_approved_rule,
)
from epick_engine.source_collection.source_runtime_input import RuntimeSourceConfigFile

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
COMPANY_ID = UUID("00000000-0000-4000-8000-00000000c311")
SOURCE_ID = UUID("00000000-0000-4000-8000-00000000c312")
RULE_ID = UUID("00000000-0000-4000-8000-00000000c313")
PROJECT_ROOT = Path(__file__).resolve().parents[3]


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


def _manifest(*, revision: int = 1, **changes: object) -> ApprovedRuleManifest:
    payload: dict[str, object] = {
        "schema_version": "w2.source-approval-rule-manifest.v1",
        "approval_rule_id": RULE_ID,
        "revision": revision,
        "company_id": COMPANY_ID,
        "company_official_domain": "company.test",
        "company_legal_identifiers": ["corp:synthetic-legal-id"],
        "company_identity_evidence_refs": ["company-evidence:synthetic"],
        "exact_host": "careers.company.test",
        "path_mode": "SEGMENT_PREFIX",
        "path_value": "/jobs",
        "allowed_query_strings": ["team=engineering"],
        "source_type": SourceType.JOB_POSTING.value,
        "official_status": "verified",
        "access_class": "public",
        "collection_permission": "allowed",
        "excerpt_storage_permission": "allowed",
        "body_storage_permission": "denied",
        "redistribution_permission": "denied",
        "evidence_refs": ["policy-evidence:synthetic"],
        "checked_at": NOW,
        "policy_version": "policy-v1",
        "robots_permission": "allowed",
        "result_version": 1,
        "language": "ko",
        "redirect_robots_permissions": [],
        "limits": _limits(),
    }
    payload.update(changes)
    return ApprovedRuleManifest.model_validate(payload)


def _metadata(url: str) -> RegistrationMetadata:
    return RegistrationMetadata(
        schema_version="w1.private.w2-source-registration-lookup.v1",
        status="AVAILABLE",
        command_id=uuid4(),
        execution_fence=1,
        owner_deletion_epoch=0,
        company_id=COMPANY_ID,
        source_id=SOURCE_ID,
        canonical_url=url,
        w1_source_type="JOB_POSTING",
        registration_input_version="input-v1",
        company_official_domain="company.test",
        company_legal_identifiers=["corp:synthetic-legal-id"],
        company_identity_evidence_refs=["company-evidence:synthetic"],
    )


def _runtime_config() -> RuntimeSourceConfigFile:
    return RuntimeSourceConfigFile.model_validate(
        {
            "schema_version": "w2.source-runtime-config.v1",
            "claim_lease_seconds": 120,
            "sources": {
                SOURCE_ID: {
                    "policy_revision": 1,
                    "robots_permission": "allowed",
                    "result_version": 1,
                    "language": "ko",
                    "redirect_robots_permissions": [],
                    "limits": _limits(),
                }
            },
        }
    )


@pytest.fixture
def database_engine(approved_postgres_url: URL) -> Iterator[Engine]:
    admin_engine = create_engine(approved_postgres_url, pool_pre_ping=True)
    schema_name = f"epick_onboarding_op_{uuid4().hex}"
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
def _migrated_schema(
    approved_postgres_url: URL,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Engine]:
    schema_name = f"epick_onboarding_cli_{uuid4().hex}"
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
        alembic_command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        admin_engine.dispose()


def _add_legacy_source(session: Session, *, policy_evidence: bool = True) -> None:
    session.add(
        Company(
            company_id=COMPANY_ID,
            legal_name="Synthetic Company",
            aliases=[],
            official_domains=["company.test"],
            legal_identifiers={"corp": "synthetic-legal-id"},
            identity_status="verified",
            identity_evidence=["company-evidence:synthetic"],
        )
    )
    session.add(
        Source(
            source_id=SOURCE_ID,
            company_id=COMPANY_ID,
            source_type=SourceType.JOB_POSTING.value,
            canonical_url="https://careers.company.test/jobs?team=engineering",
        )
    )
    session.add(
        SourcePolicyDecision(
            policy_decision_id=uuid4(),
            source_id=SOURCE_ID,
            revision=1,
            official_status="verified",
            access_class="public",
            collection_permission="allowed",
            excerpt_storage_permission="allowed",
            body_storage_permission="denied",
            redistribution_permission="denied",
            evidence_refs=["policy-evidence:synthetic"] if policy_evidence else [],
            checked_at=NOW,
            policy_version="policy-v1",
        )
    )


@pytest.mark.approved_postgres
def test_valid_rule_matches_and_same_revision_replay_is_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    manifest = _manifest()
    with session_factory.begin() as session:
        first = append_approved_rule(session, manifest)
        replay = append_approved_rule(session, manifest)
        assert first == replay
        assert (
            match_approved_rule(
                session,
                _metadata("https://careers.company.test/jobs/open?team=engineering"),
            )
            is not None
        )

    with session_factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(SourceApprovalRuleHead)) == 1
        assert session.scalar(select(func.count()).select_from(SourceApprovalRuleRevision)) == 1


@pytest.mark.approved_postgres
@pytest.mark.parametrize(
    "changes",
    [
        {"exact_host": "jobs.company.test"},
        {"path_value": "/"},
        {"allowed_query_strings": ["team=engineering", "team=finance"]},
    ],
)
def test_revision_rejects_widened_host_path_or_query(
    session_factory: sessionmaker[Session],
    changes: dict[str, object],
) -> None:
    with session_factory.begin() as session:
        append_approved_rule(session, _manifest())
    with pytest.raises(RuleScopeWidening):
        with session_factory.begin() as session:
            append_approved_rule(session, _manifest(revision=2, **changes))


@pytest.mark.approved_postgres
def test_same_revision_with_different_payload_is_a_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        append_approved_rule(session, _manifest())
    with pytest.raises(RuleRevisionConflict):
        with session_factory.begin() as session:
            append_approved_rule(session, _manifest(language="en"))


@pytest.mark.approved_postgres
def test_concurrent_revision_proposals_cannot_both_win(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        append_approved_rule(session, _manifest())

    first_appended = Event()
    release_first = Event()
    second_started = Event()
    second_finished = Event()
    outcomes: list[str] = []
    errors: list[BaseException] = []

    def propose(language: str, *, hold: bool) -> None:
        if not hold:
            second_started.set()
        try:
            with session_factory.begin() as session:
                append_approved_rule(session, _manifest(revision=2, language=language))
                outcomes.append(language)
                if hold:
                    first_appended.set()
                    if not release_first.wait(timeout=10):
                        raise TimeoutError("test did not release first rule transaction")
        except RuleRevisionConflict as error:
            errors.append(error)
        finally:
            if not hold:
                second_finished.set()

    first = Thread(target=propose, args=("ko",), kwargs={"hold": True})
    second = Thread(target=propose, args=("en",), kwargs={"hold": False})
    first.start()
    try:
        assert first_appended.wait(timeout=10)
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
    assert outcomes == ["ko"]
    assert len(errors) == 1
    with session_factory.begin() as session:
        head = session.get(SourceApprovalRuleHead, RULE_ID)
        assert head is not None and head.current_revision == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceApprovalRuleRevision)
                .where(SourceApprovalRuleRevision.revision == 2)
            )
            == 1
        )


@pytest.mark.approved_postgres
def test_v1_import_twice_is_rule_backed_and_does_not_append_policy(
    session_factory: sessionmaker[Session],
) -> None:
    config = _runtime_config()
    with session_factory.begin() as session:
        _add_legacy_source(session)
    with session_factory.begin() as session:
        first = import_v1_config(session, config)
    with session_factory.begin() as session:
        second = import_v1_config(session, config)
    assert first.imported == 1 and first.already_imported == 0
    assert second.imported == 0 and second.already_imported == 1

    with session_factory.begin() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourcePolicyDecision)
                .where(SourcePolicyDecision.source_id == SOURCE_ID)
            )
            == 1
        )
        assert session.scalar(select(func.count()).select_from(SourceRuntimeApproval)) == 1
        loaded = load_source_runtime_approval(session, SOURCE_ID)
        assert loaded == config.sources[SOURCE_ID]


@pytest.mark.approved_postgres
def test_v1_user_config_cannot_enable_source_without_w2_policy_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        _add_legacy_source(session, policy_evidence=False)
    with session_factory.begin() as session:
        result = import_v1_config(session, _runtime_config())
        assert result.disabled_pending_evidence == 1
        assert session.get(SourceRuntimeApproval, SOURCE_ID) is None
        assert load_source_runtime_approval(session, SOURCE_ID) is None


@pytest.mark.approved_postgres
def test_cli_dry_run_and_import_use_isolated_synthetic_v1_copy_without_identifiers(
    approved_postgres_url: URL,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with _migrated_schema(approved_postgres_url, monkeypatch) as engine:
        sessions = sessionmaker(engine, expire_on_commit=False)
        with sessions.begin() as session:
            _add_legacy_source(session)

        manifest_path = tmp_path / "synthetic-rule.json"
        manifest_path.write_text(_manifest().model_dump_json(), encoding="utf-8")
        assert main(["approve-rule", "--input", str(manifest_path), "--dry-run"]) == 0
        dry_rule_output = capsys.readouterr().out
        assert "RULE_VALIDATED" in dry_rule_output
        with sessions.begin() as session:
            assert session.get(SourceApprovalRuleHead, RULE_ID) is None

        config_path = tmp_path / "synthetic-v1-config.json"
        config_path.write_text(_runtime_config().model_dump_json(), encoding="utf-8")
        assert main(["import-v1-config", "--input", str(config_path), "--dry-run"]) == 0
        dry_import_output = capsys.readouterr().out
        assert '"imported": 1' in dry_import_output
        with sessions.begin() as session:
            assert session.get(SourceRuntimeApproval, SOURCE_ID) is None

        assert main(["import-v1-config", "--input", str(config_path)]) == 0
        import_output = capsys.readouterr().out
        assert '"imported": 1' in import_output
        assert main(["import-v1-config", "--input", str(config_path)]) == 0
        replay_output = capsys.readouterr().out
        assert '"already_imported": 1' in replay_output

        combined_output = dry_rule_output + dry_import_output + import_output + replay_output
        assert str(SOURCE_ID) not in combined_output
        assert "careers.company.test" not in combined_output
        assert "postgresql" not in combined_output
