"""TDD contract for the lookup-gated POLICY collection runtime."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

import epick_engine.source_collection.source_runtime as source_runtime
from epick_engine.source_collection.contracts import CollectionStage
from epick_engine.source_collection.source_runtime import (
    LookupGatedExecutionContext,
    RuntimeAuthorizationError,
    handle_collection_dispatch,
)
from epick_engine.source_collection.source_runtime_input import RuntimeSourceConfigFile
from epick_engine.source_collection.source_runtime_store import CollectionRuntimeConflict
from epick_engine.source_collection.w1_transport import (
    LookupResponse,
    W1Dispatch,
    parse_w1_dispatch,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "w1_private_contract"
NOW = datetime(2026, 9, 20, 12, tzinfo=UTC)
ATTEMPT_ID = UUID("00000000-0000-4000-8000-000000000101")
CLAIM_TOKEN = UUID("00000000-0000-4000-8000-000000000102")
STAGED_MESSAGE_ID = UUID("00000000-0000-4000-8000-000000000103")


def _dispatch(*, resume_stage: str = "policy", policy_revision: int | None = None) -> W1Dispatch:
    raw = json.loads((FIXTURES / "private-w2-command-dispatch.json").read_text(encoding="utf-8"))
    raw["payload"]["resume_stage"] = resume_stage
    raw["payload"]["policy_revision"] = policy_revision
    return parse_w1_dispatch(raw)


def _runtime_config(
    dispatch: W1Dispatch,
    *,
    policy_revision: int = 3,
) -> RuntimeSourceConfigFile:
    return RuntimeSourceConfigFile.model_validate_json(
        json.dumps(
            {
                "schema_version": "w2.source-runtime-config.v1",
                "claim_lease_seconds": 120,
                "sources": {
                    str(dispatch.payload.source_id): {
                        "policy_revision": policy_revision,
                        "robots_permission": "allowed",
                        "result_version": 1,
                        "language": "ko",
                        "redirect_robots_permissions": [],
                        "limits": {
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
                        },
                    }
                },
            }
        )
    )


def _available(dispatch: W1Dispatch) -> LookupResponse:
    return LookupResponse(
        schema_version="w1.private.command-lookup.v1",
        command_id=dispatch.payload.command_id,
        status="AVAILABLE",
        reason_code=None,
        command=dispatch.payload,
    )


def _not_found(dispatch: W1Dispatch) -> LookupResponse:
    return LookupResponse(
        schema_version="w1.private.command-lookup.v1",
        command_id=dispatch.payload.command_id,
        status="NOT_FOUND",
        reason_code="COMMAND_NOT_FOUND",
        command=None,
    )


class _RecordingLookupClient:
    def __init__(self, response: LookupResponse) -> None:
        self._response = response
        self.dispatches: list[W1Dispatch] = []

    def lookup_dispatch(self, dispatch: W1Dispatch) -> LookupResponse:
        self.dispatches.append(dispatch)
        return self._response


class _UnexpectedCallable:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise AssertionError("initial lookup failure must not create an execution resource")


class _UnexpectedInputProvider:
    def __init__(self) -> None:
        self.calls = 0

    def load(self, command: object) -> object:
        self.calls += 1
        raise AssertionError("initial lookup failure must not load approved source input")


class _Session:
    def begin(self) -> _Session:
        return self

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _SessionFactory:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> _Session:
        self.calls += 1
        return _Session()


@dataclass(frozen=True)
class _RuntimeInput:
    policy_revision: int


class _RuntimeInputProvider:
    def __init__(self, value: _RuntimeInput, events: list[str]) -> None:
        self._value = value
        self._events = events
        self.commands: list[object] = []

    def load(self, command: object) -> _RuntimeInput:
        self.commands.append(command)
        self._events.append("provider")
        return self._value


def _heartbeat_type(
    events: list[str],
    *,
    lose_on_ensure: int | None = None,
) -> type[object]:
    class _Heartbeat:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._ensures = 0
            self.lost = False
            events.append("heartbeat-create")

        def start(self) -> None:
            events.append("heartbeat-start")

        def ensure_active(self) -> None:
            self._ensures += 1
            events.append("heartbeat-ensure")
            if lose_on_ensure == self._ensures:
                self.lost = True
                raise RuntimeAuthorizationError("collection runtime claim is no longer active")

        def stop_and_join(self) -> None:
            events.append("heartbeat-stop-join")

    return _Heartbeat


def _execution_type(
    events: list[str],
    *,
    prepared: object,
    fail_run: bool = False,
    fail_close: bool = False,
) -> tuple[type[object], list[object]]:
    instances: list[object] = []

    class _Execution:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.closed = 0
            instances.append(self)
            events.append("execution-create")

        def run_once(self, context: LookupGatedExecutionContext) -> object:
            events.append("execution-run")
            context.enter_stage(CollectionStage.POLICY, policy_revision=3)
            context.enter_stage(CollectionStage.FETCH, policy_revision=3)
            if fail_run:
                raise TimeoutError("synthetic fetch timeout")
            context.enter_stage(CollectionStage.PARSE, policy_revision=3)
            return prepared

        def close(self) -> None:
            self.closed += 1
            events.append("execution-close")
            if fail_close:
                raise RuntimeError("synthetic close failure")

    return _Execution, instances


def _uuid_factory(*values: UUID) -> Any:
    iterator = iter(values)
    return lambda: next(iterator)


def _patch_runtime_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[str],
    input_value: _RuntimeInput,
    heartbeat_type: type[object],
    execution_type: type[object],
    attempt_state: tuple[str, int, UUID] | None = None,
) -> dict[str, Any]:
    calls: dict[str, Any] = {
        "claim": [],
        "commit": [],
        "load": [],
        "release": [],
        "replay": [],
        "renew": [],
        "reserve": [],
    }

    def load(*args: object, **kwargs: object) -> object | None:
        calls["load"].append((args, kwargs))
        if attempt_state is None:
            return None
        return SimpleNamespace(
            state=attempt_state[0],
            effective_policy_revision=attempt_state[1],
            attempt_id=attempt_state[2],
        )

    def reserve(*args: object, **kwargs: object) -> object:
        calls["reserve"].append((args, kwargs))
        events.append("reserve")
        return SimpleNamespace(
            attempt_id=ATTEMPT_ID,
            effective_policy_revision=input_value.policy_revision,
        )

    def claim(*args: object, **kwargs: object) -> object:
        calls["claim"].append((args, kwargs))
        events.append("claim")
        return SimpleNamespace(attempt_id=ATTEMPT_ID)

    def renew(*args: object, **kwargs: object) -> None:
        calls["renew"].append((args, kwargs))
        events.append("renew")

    def release(*args: object, **kwargs: object) -> None:
        calls["release"].append((args, kwargs))
        events.append("release")

    def commit(*args: object, **kwargs: object) -> object:
        calls["commit"].append((args, kwargs))
        events.append("commit")
        return "staged-proposal"

    def replay(*args: object, **kwargs: object) -> object:
        calls["replay"].append((args, kwargs))
        events.append("replay")
        return "replayed-proposal"

    operations = source_runtime.RuntimeStoreOperations(
        load_attempt=load,
        reserve_attempt=reserve,
        claim_attempt=claim,
        renew_claim=renew,
        release_claim=release,
        commit_candidate=commit,
        replay_candidate=replay,
    )
    calls["operations"] = operations

    monkeypatch.setattr(source_runtime, "StaticCollectionInput", _RuntimeInput)
    monkeypatch.setattr(source_runtime, "StaticCollectionExecution", execution_type)
    monkeypatch.setattr(source_runtime, "_ClaimHeartbeat", heartbeat_type)
    return calls


class _SequencedLookupClient:
    def __init__(
        self,
        *,
        unavailable_call: int | None = None,
    ) -> None:
        self._unavailable_call = unavailable_call
        self.dispatches: list[W1Dispatch] = []

    def lookup_dispatch(self, dispatch: W1Dispatch) -> LookupResponse:
        self.dispatches.append(dispatch)
        if self._unavailable_call == len(self.dispatches):
            return _not_found(dispatch)
        return _available(dispatch)


def test_initial_unavailable_lookup_has_no_db_or_execution_side_effects() -> None:
    """Removing the initial lookup guard must fail before any DB/provider/collector action."""

    dispatch = _dispatch()
    lookup = _RecordingLookupClient(_not_found(dispatch))
    session_factory = _UnexpectedCallable()
    input_provider = _UnexpectedInputProvider()
    collector_factory = _UnexpectedCallable()
    parser = _UnexpectedCallable()

    with pytest.raises(RuntimeAuthorizationError):
        handle_collection_dispatch(
            dispatch,
            session_factory=session_factory,
            lookup_client=lookup,
            input_provider=input_provider,
            collector_factory=collector_factory,
            parser=parser,
            runtime_config=_runtime_config(dispatch),
            clock=_UnexpectedCallable(),
            uuid_factory=_UnexpectedCallable(),
        )

    assert lookup.dispatches == [dispatch]
    assert session_factory.calls == 0
    assert input_provider.calls == 0
    assert collector_factory.calls == 0
    assert parser.calls == 0


def test_non_policy_wire_command_is_rejected_before_lookup_or_db_work() -> None:
    """Changing the initial POLICY/null command gate must leave no authorization side effect."""

    dispatch = _dispatch(resume_stage="fetch", policy_revision=3)
    lookup = _RecordingLookupClient(_available(dispatch))
    session_factory = _UnexpectedCallable()

    with pytest.raises(RuntimeAuthorizationError):
        handle_collection_dispatch(
            dispatch,
            session_factory=session_factory,
            lookup_client=lookup,
            input_provider=_UnexpectedInputProvider(),
            collector_factory=_UnexpectedCallable(),
            parser=_UnexpectedCallable(),
            runtime_config=_runtime_config(dispatch),
            clock=_UnexpectedCallable(),
            uuid_factory=_UnexpectedCallable(),
        )

    assert lookup.dispatches == []
    assert session_factory.calls == 0


def test_context_derives_effective_policy_without_mutating_wire_dispatch() -> None:
    """Assigning the provider revision to the received W1 command would corrupt replay identity."""

    dispatch = _dispatch()
    original_payload = deepcopy(dispatch.payload.model_dump(mode="python"))
    lookup = _RecordingLookupClient(_available(dispatch))
    context = LookupGatedExecutionContext(
        dispatch=dispatch,
        lookup_client=lookup,
        _effective_command=dispatch.payload,
    )

    response = context.enter_stage(CollectionStage.FETCH, policy_revision=3)

    assert response.status == "AVAILABLE"
    assert lookup.dispatches == [dispatch]
    assert dispatch.payload.model_dump(mode="python") == original_payload
    assert dispatch.payload.policy_revision is None
    assert context.command is not dispatch.payload
    assert context.command.resume_stage is CollectionStage.FETCH
    assert context.command.policy_revision == 3


def test_successful_persist_stops_heartbeat_before_exact_claim_candidate_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Moving commit before heartbeat join could race the PERSISTED claim-clear transition."""

    dispatch = _dispatch()
    events: list[str] = []
    input_value = _RuntimeInput(policy_revision=3)
    execution_type, instances = _execution_type(events, prepared="prepared")
    calls = _patch_runtime_happy_path(
        monkeypatch,
        events=events,
        input_value=input_value,
        heartbeat_type=_heartbeat_type(events),
        execution_type=execution_type,
    )
    lookup = _SequencedLookupClient()
    session_factory = _SessionFactory()
    input_provider = _RuntimeInputProvider(input_value, events)

    proposal = handle_collection_dispatch(
        dispatch,
        session_factory=session_factory,
        lookup_client=lookup,
        input_provider=input_provider,
        collector_factory=lambda: object(),
        parser=lambda candidate: candidate,
        runtime_config=_runtime_config(dispatch),
        clock=lambda: NOW,
        uuid_factory=_uuid_factory(CLAIM_TOKEN, STAGED_MESSAGE_ID),
        store_operations=calls["operations"],
    )

    assert proposal == "staged-proposal"
    assert lookup.dispatches == [dispatch] * 5
    assert input_provider.commands == [dispatch.payload]
    assert len(calls["reserve"]) == len(calls["claim"]) == len(calls["renew"]) == 1
    assert calls["release"] == []
    assert len(calls["commit"]) == 1
    commit_args, commit_kwargs = calls["commit"][0]
    assert commit_args[1].payload.policy_revision is None
    assert commit_args[2].resume_stage is CollectionStage.PERSIST
    assert commit_args[2].policy_revision == 3
    assert commit_args[3] == "prepared"
    assert commit_kwargs["claim_token"] == CLAIM_TOKEN
    assert commit_kwargs["staged_message_id"] == STAGED_MESSAGE_ID
    assert instances[0].closed == 1
    assert events.index("renew") < events.index("heartbeat-stop-join")
    assert events.index("heartbeat-stop-join") < events.index("execution-close")
    assert events.index("execution-close") < events.index("commit")
    assert "deliver" not in events


@pytest.mark.parametrize(
    ("failed_stage", "unavailable_call"),
    [
        (CollectionStage.FETCH, 3),
        (CollectionStage.PARSE, 4),
        (CollectionStage.PERSIST, 5),
    ],
)
def test_unavailable_execution_stage_never_commits_candidate_and_releases_clean_claim(
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: CollectionStage,
    unavailable_call: int,
) -> None:
    """Removing a fresh lookup at FETCH/PARSE/PERSIST would permit stale candidate writes."""

    dispatch = _dispatch()
    events: list[str] = []
    input_value = _RuntimeInput(policy_revision=3)
    execution_type, instances = _execution_type(events, prepared="prepared")
    calls = _patch_runtime_happy_path(
        monkeypatch,
        events=events,
        input_value=input_value,
        heartbeat_type=_heartbeat_type(events),
        execution_type=execution_type,
    )
    lookup = _SequencedLookupClient(unavailable_call=unavailable_call)

    with pytest.raises(RuntimeAuthorizationError):
        handle_collection_dispatch(
            dispatch,
            session_factory=_SessionFactory(),
            lookup_client=lookup,
            input_provider=_RuntimeInputProvider(input_value, events),
            collector_factory=lambda: object(),
            parser=lambda candidate: candidate,
            runtime_config=_runtime_config(dispatch),
            clock=lambda: NOW,
            uuid_factory=_uuid_factory(CLAIM_TOKEN),
            store_operations=calls["operations"],
        )

    assert len(lookup.dispatches) == unavailable_call
    assert calls["commit"] == []
    assert len(calls["release"]) == 1
    assert calls["release"][0][1]["claim_token"] == CLAIM_TOKEN
    assert instances[0].closed == 1
    assert events.index("heartbeat-stop-join") < events.index("execution-close")
    assert events.index("execution-close") < events.index("release")
    assert failed_stage in {CollectionStage.FETCH, CollectionStage.PARSE, CollectionStage.PERSIST}


def test_lost_heartbeat_claim_closes_work_but_never_releases_or_commits_stale_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lost lease must cancel local work and leave takeover to DB-clock expiry."""

    dispatch = _dispatch()
    events: list[str] = []
    input_value = _RuntimeInput(policy_revision=3)
    execution_type, instances = _execution_type(events, prepared="prepared")
    calls = _patch_runtime_happy_path(
        monkeypatch,
        events=events,
        input_value=input_value,
        heartbeat_type=_heartbeat_type(events, lose_on_ensure=2),
        execution_type=execution_type,
    )

    with pytest.raises(RuntimeAuthorizationError, match="claim is no longer active"):
        handle_collection_dispatch(
            dispatch,
            session_factory=_SessionFactory(),
            lookup_client=_SequencedLookupClient(),
            input_provider=_RuntimeInputProvider(input_value, events),
            collector_factory=lambda: object(),
            parser=lambda candidate: candidate,
            runtime_config=_runtime_config(dispatch),
            clock=lambda: NOW,
            uuid_factory=_uuid_factory(CLAIM_TOKEN),
            store_operations=calls["operations"],
        )

    assert calls["commit"] == []
    assert calls["release"] == []
    assert instances[0].closed == 1
    assert "heartbeat-stop-join" in events


def test_uncertain_close_after_precommit_failure_does_not_eagerly_release_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Releasing after a failed close could let another worker overlap a live collector."""

    dispatch = _dispatch()
    events: list[str] = []
    input_value = _RuntimeInput(policy_revision=3)
    execution_type, instances = _execution_type(
        events,
        prepared="prepared",
        fail_run=True,
        fail_close=True,
    )
    calls = _patch_runtime_happy_path(
        monkeypatch,
        events=events,
        input_value=input_value,
        heartbeat_type=_heartbeat_type(events),
        execution_type=execution_type,
    )

    with pytest.raises(TimeoutError, match="synthetic fetch timeout"):
        handle_collection_dispatch(
            dispatch,
            session_factory=_SessionFactory(),
            lookup_client=_SequencedLookupClient(),
            input_provider=_RuntimeInputProvider(input_value, events),
            collector_factory=lambda: object(),
            parser=lambda candidate: candidate,
            runtime_config=_runtime_config(dispatch),
            clock=lambda: NOW,
            uuid_factory=_uuid_factory(CLAIM_TOKEN),
            store_operations=calls["operations"],
        )

    assert calls["commit"] == []
    assert calls["release"] == []
    assert instances[0].closed == 1
    assert "heartbeat-stop-join" in events


def test_heartbeat_start_failure_releases_exact_claim_without_attempting_join_or_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception before the main try block must not strand a healthy just-acquired claim."""

    dispatch = _dispatch()
    events: list[str] = []
    input_value = _RuntimeInput(policy_revision=3)
    execution_type, _instances = _execution_type(events, prepared="prepared")

    class _StartFailsHeartbeat:
        lost = False

        def __init__(self, *args: object, **kwargs: object) -> None:
            events.append("heartbeat-create")

        def start(self) -> None:
            events.append("heartbeat-start")
            raise RuntimeError("synthetic heartbeat start failure")

        def ensure_active(self) -> None:
            raise AssertionError("failed heartbeat must not enter execution")

        def stop_and_join(self) -> None:
            events.append("heartbeat-stop-join")

    calls = _patch_runtime_happy_path(
        monkeypatch,
        events=events,
        input_value=input_value,
        heartbeat_type=_StartFailsHeartbeat,
        execution_type=execution_type,
    )

    with pytest.raises(RuntimeError, match="synthetic heartbeat start failure"):
        handle_collection_dispatch(
            dispatch,
            session_factory=_SessionFactory(),
            lookup_client=_SequencedLookupClient(),
            input_provider=_RuntimeInputProvider(input_value, events),
            collector_factory=lambda: object(),
            parser=lambda candidate: candidate,
            runtime_config=_runtime_config(dispatch),
            clock=lambda: NOW,
            uuid_factory=_uuid_factory(CLAIM_TOKEN),
            store_operations=calls["operations"],
        )

    assert calls["commit"] == []
    assert len(calls["release"]) == 1
    assert calls["release"][0][1]["claim_token"] == CLAIM_TOKEN
    assert "heartbeat-stop-join" not in events


def test_reserved_attempt_policy_advance_blocks_claim_and_collector_before_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Using a stale RESERVED revision after a policy writer update would bypass Source locking."""

    dispatch = _dispatch()
    events: list[str] = []
    input_value = _RuntimeInput(policy_revision=3)
    execution_type, _instances = _execution_type(events, prepared="prepared")
    calls = _patch_runtime_happy_path(
        monkeypatch,
        events=events,
        input_value=input_value,
        heartbeat_type=_heartbeat_type(events),
        execution_type=execution_type,
        attempt_state=("RESERVED", 3, ATTEMPT_ID),
    )
    original_operations = calls["operations"]

    def stale_locked_reservation(*args: object, **kwargs: object) -> object:
        calls["reserve"].append((args, kwargs))
        raise CollectionRuntimeConflict("current policy revision changed under Source lock")

    calls["operations"] = replace(
        original_operations,
        reserve_attempt=stale_locked_reservation,
    )
    collector_factory = _UnexpectedCallable()

    with pytest.raises(CollectionRuntimeConflict, match="policy revision changed"):
        handle_collection_dispatch(
            dispatch,
            session_factory=_SessionFactory(),
            lookup_client=_SequencedLookupClient(),
            input_provider=_RuntimeInputProvider(input_value, events),
            collector_factory=collector_factory,
            parser=lambda candidate: candidate,
            runtime_config=_runtime_config(dispatch),
            clock=lambda: NOW,
            uuid_factory=_uuid_factory(CLAIM_TOKEN),
            store_operations=calls["operations"],
        )

    assert len(calls["reserve"]) == 1
    assert calls["claim"] == []
    assert calls["commit"] == []
    assert calls["release"] == []
    assert collector_factory.calls == 0
