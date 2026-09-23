"""Fresh-lookup-gated execution for one initial W2 collection dispatch."""

from __future__ import annotations

import inspect
import json
import math
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from threading import Event, Thread
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from epick_engine.source_collection.collector import (
    StaticFetchRequest,
    StaticFetchResult,
    StaticResponseCandidate,
)
from epick_engine.source_collection.commit_gate_contracts import (
    CommitGateCommand,
    StagedResultProposal,
    parse_commit_gate_command,
)
from epick_engine.source_collection.commit_gate_runtime import (
    BeforeSend,
    ConsumeResult,
    GateApplier,
    QueueDelivery,
    _sender_matches,
    _strict_json_object,
)
from epick_engine.source_collection.commit_gate_store import PrivateCommitGateAck
from epick_engine.source_collection.contracts import CollectionCommand, CollectionStage
from epick_engine.source_collection.parsing import StaticParseResult
from epick_engine.source_collection.persistence import (
    CollectionRuntimeAttempt,
    bind_private_write_scope,
    commit_collection_candidate,
    replay_staged_collection,
)
from epick_engine.source_collection.private_scope import (
    PrivateWriteAuthorityDecision,
    PrivateWriteScope,
)
from epick_engine.source_collection.service import (
    StaticCollectionExecution,
    StaticCollectionInput,
)
from epick_engine.source_collection.source_runtime_gate import apply_collection_commit_gate
from epick_engine.source_collection.source_runtime_input import RuntimeSourceConfigFile
from epick_engine.source_collection.source_runtime_store import (
    CollectionRuntimeConflict,
    _validated_dispatch,
    claim_collection_attempt,
    load_bound_collection_attempt,
    release_collection_claim,
    renew_collection_claim,
    reserve_collection_attempt,
)
from epick_engine.source_collection.w1_lookup_client import W1LookupClientError
from epick_engine.source_collection.w1_transport import (
    LookupRequest,
    LookupResponse,
    W1Dispatch,
    W1LookupError,
    W1WireContractError,
    parse_w1_dispatch,
    validate_dispatch_lookup,
)


class RuntimeAuthorizationError(RuntimeError):
    """The W1 lookup or durable runtime state no longer authorizes execution."""


type SessionFactory = Callable[[], Session]
type Clock = Callable[[], datetime]
type UUIDFactory = Callable[[], UUID]
type StaticParser = Callable[[StaticResponseCandidate], StaticParseResult]


class LookupClient(Protocol):
    def lookup_dispatch(self, dispatch: W1Dispatch) -> LookupResponse: ...


class RelayLookupClient(Protocol):
    def lookup(self, request: LookupRequest) -> LookupResponse: ...


class CollectionInputProvider(Protocol):
    def load(self, command: CollectionCommand) -> StaticCollectionInput: ...


class CollectorFactory(Protocol):
    def __call__(self) -> object: ...


class PrivateWriteAuthorityProvider(Protocol):
    """Return one decision authenticated outside the W2 wire contract."""

    def __call__(
        self,
        subject: W1Dispatch | CommitGateCommand,
    ) -> PrivateWriteAuthorityDecision: ...


type SourceRuntimeMode = Literal["mixed", "collection", "gate"]


class GateSessionFactory(Protocol):
    def begin(self) -> AbstractContextManager[Session]: ...


class SourceRuntimeQueue(Protocol):
    def receive(self) -> Sequence[QueueDelivery]: ...

    def delete(self, receipt_handle: str) -> None: ...

    def extend_visibility(self, receipt_handle: str) -> None: ...


class _ReceiptVisibilityHeartbeat:
    def __init__(
        self,
        queue: SourceRuntimeQueue,
        receipt_handle: str,
        *,
        interval_seconds: float,
    ) -> None:
        if (
            not isinstance(interval_seconds, int | float)
            or isinstance(interval_seconds, bool)
            or not math.isfinite(interval_seconds)
            or interval_seconds <= 0
        ):
            raise ValueError("visibility heartbeat interval must be positive and finite")
        self._queue = queue
        self._receipt_handle = receipt_handle
        self._interval_seconds = float(interval_seconds)
        self._stop = Event()
        self._lost = Event()
        self._thread = Thread(
            target=self._run,
            name="w2-source-receipt-visibility",
            daemon=True,
        )

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    def start(self) -> None:
        # Establish one full configured lease before starting durable work.
        self._queue.extend_visibility(self._receipt_handle)
        self._thread.start()

    def stop_and_join(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._queue.extend_visibility(self._receipt_handle)
            except Exception:
                self._lost.set()
                self._stop.set()
                return


def build_collection_relay_authorizer(
    lookup_client: RelayLookupClient,
) -> BeforeSend:
    """Authorize staged collection delivery from its immutable stored command only."""

    def authorize(kind: str, payload: Mapping[str, object]) -> None:
        if kind == "ACK":
            return
        if kind != "STAGED":
            raise RuntimeAuthorizationError("source runtime relay kind is invalid")
        try:
            encoded = json.dumps(
                dict(payload),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            proposal = StagedResultProposal.model_validate_json(encoded, strict=True)
            command = proposal.command
            fence = command.execution_fence
            if (
                not fence.isascii()
                or not fence.isdecimal()
                or str(int(fence)) != fence
                or int(fence) <= 0
            ):
                raise ValueError
            request = LookupRequest(
                schema_version="w1.private.command-lookup.v1",
                command_id=command.command_id,
                execution_fence=int(fence),
                owner_deletion_epoch=command.owner_deletion_epoch,
            )
            response = lookup_client.lookup(request)
        except (
            TypeError,
            ValueError,
            UnicodeError,
            RecursionError,
            W1LookupClientError,
            W1LookupError,
            W1WireContractError,
        ) as exc:
            raise RuntimeAuthorizationError("source runtime relay lookup is invalid") from exc
        if (
            not isinstance(response, LookupResponse)
            or response.status != "AVAILABLE"
            or response.command_id != command.command_id
            or response.command != command
        ):
            raise RuntimeAuthorizationError("source runtime relay is unavailable")

    return authorize


@dataclass(frozen=True, slots=True)
class RuntimeStoreOperations:
    """Injectable durable-operation boundary used by the runtime and heartbeat."""

    load_attempt: Callable[..., CollectionRuntimeAttempt | None] = field(
        default_factory=lambda: load_bound_collection_attempt
    )
    reserve_attempt: Callable[..., CollectionRuntimeAttempt] = field(
        default_factory=lambda: reserve_collection_attempt
    )
    claim_attempt: Callable[..., CollectionRuntimeAttempt] = field(
        default_factory=lambda: claim_collection_attempt
    )
    renew_claim: Callable[..., CollectionRuntimeAttempt] = field(
        default_factory=lambda: renew_collection_claim
    )
    release_claim: Callable[..., CollectionRuntimeAttempt] = field(
        default_factory=lambda: release_collection_claim
    )
    commit_candidate: Callable[..., StagedResultProposal] = field(
        default_factory=lambda: commit_collection_candidate
    )
    replay_candidate: Callable[..., StagedResultProposal] = field(
        default_factory=lambda: replay_staged_collection
    )


def _default_store_operations() -> RuntimeStoreOperations:
    """Bind the current operation seams when a handler invocation starts."""

    return RuntimeStoreOperations()


def _require_available(
    dispatch: W1Dispatch,
    lookup_client: LookupClient,
) -> LookupResponse:
    try:
        response = lookup_client.lookup_dispatch(dispatch)
        validate_dispatch_lookup(dispatch, response)
    except (
        W1LookupClientError,
        W1LookupError,
        W1WireContractError,
        ValueError,
        TypeError,
    ) as exc:
        raise RuntimeAuthorizationError("collection dispatch lookup is invalid") from exc
    if response.status != "AVAILABLE":
        raise RuntimeAuthorizationError("collection dispatch is unavailable")
    return response


def _derive_effective_command(
    dispatch: W1Dispatch,
    stage: CollectionStage,
    policy_revision: int,
) -> CollectionCommand:
    if (
        not isinstance(policy_revision, int)
        or isinstance(policy_revision, bool)
        or policy_revision <= 0
    ):
        raise RuntimeAuthorizationError("runtime stage requires effective policy revision")
    payload = dispatch.payload.model_dump(mode="python")
    payload.update({"resume_stage": stage, "policy_revision": policy_revision})
    try:
        return CollectionCommand.model_validate(payload)
    except ValueError as exc:
        raise RuntimeAuthorizationError("runtime effective command is invalid") from exc


@dataclass(slots=True)
class LookupGatedExecutionContext:
    """Keep W1's immutable dispatch separate from a local stage-effective command."""

    dispatch: W1Dispatch
    lookup_client: LookupClient
    _effective_command: CollectionCommand
    _claim_guard: Callable[[], None] | None = None

    @property
    def command(self) -> CollectionCommand:
        return self._effective_command

    def enter_stage(
        self,
        stage: CollectionStage,
        *,
        policy_revision: int | None = None,
    ) -> LookupResponse:
        if stage not in {
            CollectionStage.POLICY,
            CollectionStage.FETCH,
            CollectionStage.PARSE,
            CollectionStage.PERSIST,
        }:
            raise RuntimeAuthorizationError("runtime stage is not executable")
        response = _require_available(self.dispatch, self.lookup_client)
        if self._claim_guard is not None:
            self._claim_guard()
        if policy_revision is None:
            raise RuntimeAuthorizationError("runtime stage requires effective policy revision")
        self._effective_command = _derive_effective_command(
            self.dispatch,
            stage,
            policy_revision,
        )
        return response


class _FixedInputProvider:
    def __init__(self, input_value: StaticCollectionInput) -> None:
        self._input_value = input_value

    def load(self, command: CollectionCommand) -> StaticCollectionInput:
        return self._input_value


class _ClaimHeartbeat:
    def __init__(
        self,
        session_factory: SessionFactory,
        command_id: UUID,
        claim_token: UUID,
        *,
        lease_seconds: int,
        interval_seconds: float,
        renew_claim: Callable[..., CollectionRuntimeAttempt],
        private_scope: PrivateWriteScope,
    ) -> None:
        self._session_factory = session_factory
        self._command_id = command_id
        self._claim_token = claim_token
        self._lease_seconds = lease_seconds
        self._interval_seconds = interval_seconds
        self._renew_claim = renew_claim
        self._private_scope = private_scope
        self._stop = Event()
        self._lost = Event()
        self._thread = Thread(
            target=self._run,
            name=f"w2-claim-{command_id}",
            daemon=True,
        )

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    def start(self) -> None:
        self._thread.start()

    def ensure_active(self) -> None:
        if self._lost.is_set():
            raise RuntimeAuthorizationError("collection runtime claim is no longer active")

    def stop_and_join(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._renew_claim(
                    self._session_factory,
                    self._command_id,
                    claim_token=self._claim_token,
                    lease_seconds=self._lease_seconds,
                    private_scope=self._private_scope,
                )
            except Exception:
                self._lost.set()
                self._stop.set()
                return


class _CancellationAwareCollector:
    """Adapt heartbeat loss to collectors that expose ``is_cancelled``."""

    def __init__(self, collector: object, heartbeat: _ClaimHeartbeat) -> None:
        self._collector = collector
        self._heartbeat = heartbeat

    def fetch(self, request: StaticFetchRequest) -> StaticFetchResult:
        fetch = getattr(self._collector, "fetch", None)
        if not callable(fetch):
            raise TypeError("collector must expose fetch")
        parameters = inspect.signature(fetch).parameters.values()
        supports_cancellation = any(
            parameter.name == "is_cancelled" or parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )
        if supports_cancellation:
            return cast(
                StaticFetchResult,
                fetch(request, is_cancelled=lambda: self._heartbeat.lost),
            )
        return cast(StaticFetchResult, fetch(request))

    def close(self) -> None:
        close = getattr(self._collector, "close", None)
        if callable(close):
            close()


def _validated_initial_dispatch(dispatch: W1Dispatch) -> W1Dispatch:
    try:
        validated = _validated_dispatch(dispatch)
    except CollectionRuntimeConflict as exc:
        raise RuntimeAuthorizationError("collection dispatch is invalid") from exc
    command = validated.payload
    if command.resume_stage is not CollectionStage.POLICY or command.policy_revision is not None:
        raise RuntimeAuthorizationError("runtime requires an initial POLICY dispatch")
    return validated


def _aware_now(clock: Clock) -> datetime:
    now = clock()
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return now


def _load_attempt_state(
    session_factory: SessionFactory,
    dispatch: W1Dispatch,
    store_operations: RuntimeStoreOperations,
) -> tuple[str, int, UUID] | None:
    with session_factory() as session, session.begin():
        attempt = store_operations.load_attempt(session, dispatch)
        if attempt is None:
            return None
        return attempt.state, attempt.effective_policy_revision, attempt.attempt_id


def _release_after_clean_failure(
    session_factory: SessionFactory,
    command_id: UUID,
    claim_token: UUID,
    private_scope: PrivateWriteScope,
    store_operations: RuntimeStoreOperations,
) -> None:
    try:
        store_operations.release_claim(
            session_factory,
            command_id,
            claim_token=claim_token,
            private_scope=private_scope,
        )
    except Exception:
        # Lost, expired, or unconfirmed claims are deliberately left for
        # DB-clock takeover; cleanup must not mask the execution failure.
        return


def handle_collection_dispatch(
    dispatch: W1Dispatch,
    *,
    session_factory: SessionFactory,
    lookup_client: LookupClient,
    input_provider: CollectionInputProvider,
    collector_factory: CollectorFactory,
    parser: StaticParser,
    runtime_config: RuntimeSourceConfigFile,
    clock: Clock,
    uuid_factory: UUIDFactory,
    store_operations: RuntimeStoreOperations | None = None,
    private_scope: PrivateWriteScope | None = None,
) -> StagedResultProposal:
    """Execute an initial POLICY dispatch through durable PERSIST, never DELIVER."""

    operations = _default_store_operations() if store_operations is None else store_operations
    validated = _validated_initial_dispatch(dispatch)
    command = validated.payload
    bind_private_write_scope(
        private_scope,
        owner_user_id=command.authenticated_owner_ref,
        owner_deletion_epoch=command.owner_deletion_epoch,
        command_id=command.command_id,
        job_id=command.job_id,
        project_ref=command.project_ref,
        bind_project_ref=True,
    )
    assert private_scope is not None
    _require_available(validated, lookup_client)

    state = _load_attempt_state(session_factory, validated, operations)
    if state is not None and state[0] in {"PERSISTED", "FINALIZED"}:
        return operations.replay_candidate(
            session_factory,
            validated,
            private_scope=private_scope,
        )
    if state is not None and state[0] == "INVALIDATED":
        raise RuntimeAuthorizationError("collection runtime attempt is invalidated")

    input_value = input_provider.load(validated.payload)
    if not isinstance(input_value, StaticCollectionInput):
        raise ValueError("collection input provider returned an invalid input")
    approved = runtime_config.sources.get(validated.payload.source_id)
    if approved is None or approved.policy_revision != input_value.policy_revision:
        raise RuntimeAuthorizationError("approved collection policy revision is stale")
    if state is not None and state[1] != input_value.policy_revision:
        raise RuntimeAuthorizationError("collection runtime policy revision is stale")

    with session_factory() as session, session.begin():
        attempt = operations.reserve_attempt(
            session,
            validated,
            input_value.policy_revision,
            _aware_now(clock),
            uuid_factory,
            private_scope=private_scope,
        )
        attempt_id = attempt.attempt_id
        effective_policy_revision = attempt.effective_policy_revision

    if effective_policy_revision != input_value.policy_revision:
        raise RuntimeAuthorizationError("collection runtime policy revision is stale")

    claim_token = uuid_factory()
    claimed = operations.claim_attempt(
        session_factory,
        validated.payload.command_id,
        claim_token=claim_token,
        lease_seconds=runtime_config.claim_lease_seconds,
        private_scope=private_scope,
    )
    if claimed.attempt_id != attempt_id:
        _release_after_clean_failure(
            session_factory,
            validated.payload.command_id,
            claim_token,
            private_scope,
            operations,
        )
        raise CollectionRuntimeConflict("collection runtime attempt identity conflict")

    heartbeat: _ClaimHeartbeat | None = None
    heartbeat_started = False
    execution: StaticCollectionExecution | None = None
    collector: _CancellationAwareCollector | None = None
    close_attempted = False
    cleanup_confirmed = True
    try:
        heartbeat = _ClaimHeartbeat(
            session_factory,
            validated.payload.command_id,
            claim_token,
            lease_seconds=runtime_config.claim_lease_seconds,
            interval_seconds=runtime_config.heartbeat_interval_seconds,
            renew_claim=operations.renew_claim,
            private_scope=private_scope,
        )
        heartbeat.start()
        heartbeat_started = True
        collector = _CancellationAwareCollector(collector_factory(), heartbeat)
        cleanup_confirmed = False
        execution = StaticCollectionExecution(
            claimed.attempt_id,
            _FixedInputProvider(input_value),
            collector,
            parser,
            clock=clock,
            uuid_factory=uuid_factory,
        )
        context = LookupGatedExecutionContext(
            dispatch=validated,
            lookup_client=lookup_client,
            _effective_command=_derive_effective_command(
                validated,
                CollectionStage.POLICY,
                effective_policy_revision,
            ),
            _claim_guard=heartbeat.ensure_active,
        )
        prepared = execution.run_once(context)
        heartbeat.ensure_active()
        context.enter_stage(
            CollectionStage.PERSIST,
            policy_revision=effective_policy_revision,
        )
        heartbeat.ensure_active()
        operations.renew_claim(
            session_factory,
            validated.payload.command_id,
            claim_token=claim_token,
            lease_seconds=runtime_config.claim_lease_seconds,
            private_scope=private_scope,
        )
        heartbeat.stop_and_join()
        heartbeat.ensure_active()

        close_attempted = True
        execution.close()
        cleanup_confirmed = True
        return operations.commit_candidate(
            session_factory,
            validated,
            context.command,
            prepared,
            claim_token=claim_token,
            staged_message_id=uuid_factory(),
            occurred_at=_aware_now(clock),
            private_scope=private_scope,
        )
    except Exception:
        if heartbeat is not None and heartbeat_started:
            heartbeat.stop_and_join()
        if execution is not None and not close_attempted:
            close_attempted = True
            try:
                execution.close()
            except Exception:
                cleanup_confirmed = False
            else:
                cleanup_confirmed = True
        elif collector is not None and not close_attempted:
            close_attempted = True
            try:
                collector.close()
            except Exception:
                cleanup_confirmed = False
            else:
                cleanup_confirmed = True
        if cleanup_confirmed and (heartbeat is None or not heartbeat.lost):
            _release_after_clean_failure(
                session_factory,
                validated.payload.command_id,
                claim_token,
                private_scope,
                operations,
            )
        raise


def consume_source_runtime_once(
    session_factory: GateSessionFactory,
    queue: SourceRuntimeQueue,
    expected_sender_id: str,
    *,
    mode: SourceRuntimeMode,
    collection_handler: Callable[..., object],
    gate_applier: GateApplier = apply_collection_commit_gate,
    authority_provider: PrivateWriteAuthorityProvider | None = None,
    clock: Clock,
    message_id_factory: Callable[[], UUID] = uuid4,
    visibility_heartbeat_seconds: float | None = None,
) -> ConsumeResult:
    """Route one authenticated source-runtime delivery to exactly one handler."""

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
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return ConsumeResult(status="MALFORMED")

    message_type = payload.get("message_type")
    is_collection = message_type in {
        "w1.private.w2.collection-command.v1",
        "w1.private.w2.direct-source-registration.v1",
    }
    is_gate = message_type == "w1.private.w2.commit-gate.v1"
    if mode not in {"mixed", "collection", "gate"}:
        return ConsumeResult(status="REJECTED")
    if (is_collection and mode == "gate") or (is_gate and mode == "collection"):
        return ConsumeResult(status="REJECTED")
    if not is_collection and not is_gate:
        return ConsumeResult(status="MALFORMED")

    try:
        if is_collection:
            dispatch = parse_w1_dispatch(payload)
            if authority_provider is None:
                raise RuntimeAuthorizationError("trusted private authority provider is required")
            private_scope = PrivateWriteScope(authority_provider(dispatch))
            extend_visibility = getattr(queue, "extend_visibility", None)
            if visibility_heartbeat_seconds is None or extend_visibility is None:
                raise RuntimeError("source runtime visibility heartbeat is required")
            heartbeat = _ReceiptVisibilityHeartbeat(
                queue,
                delivery.receipt_handle,
                interval_seconds=visibility_heartbeat_seconds,
            )
            heartbeat.start()
            try:
                collection_handler(dispatch, private_scope=private_scope)
            finally:
                heartbeat.stop_and_join()
            if heartbeat.lost:
                raise RuntimeError("source runtime receipt visibility is no longer active")
        else:
            gate = parse_commit_gate_command(payload)
            if authority_provider is None:
                raise RuntimeAuthorizationError("trusted private authority provider is required")
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
                    PrivateCommitGateAck,
                    ack.message_id,
                    populate_existing=True,
                )
                if persisted_ack is None:
                    raise RuntimeError("persisted private commit-gate ACK unavailable")
                persisted_ack.delivered_at = None
    except Exception:
        return ConsumeResult(status="REJECTED")

    try:
        queue.delete(delivery.receipt_handle)
    except Exception:
        return ConsumeResult(status="DELETE_FAILED")
    return ConsumeResult(status="APPLIED")
