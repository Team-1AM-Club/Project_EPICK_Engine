"""Fail-closed approved input loading for the W2 collection runtime."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Annotated, Literal, NoReturn
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    field_serializer,
    field_validator,
    model_validator,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from epick_engine.source_collection.collector import _hard_deadline_seconds
from epick_engine.source_collection.contracts import (
    AccessClass,
    CollectionCommand,
    CollectionStage,
    OfficialStatus,
    Permission,
    Policy,
    SourceType,
)
from epick_engine.source_collection.persistence import (
    Company,
    OutboxEvent,
    Source,
    SourcePolicyDecision,
)
from epick_engine.source_collection.policy import (
    ExecutionLimits,
    ExecutionPolicyUnconfigured,
    parse_execution_limits,
)
from epick_engine.source_collection.service import StaticCollectionInput

type SessionFactory = Callable[[], Session]
type PositiveStrictInt = Annotated[int, Field(strict=True, gt=0)]
type NonEmptyStrictStr = Annotated[str, Field(strict=True, min_length=1)]

_SOURCE_INTEGER_FIELDS = ("policy_revision", "result_version")
_LIMIT_INTEGER_FIELDS = (
    "site_concurrency",
    "global_concurrency",
    "source_ttl_seconds",
    "max_response_bytes",
    "max_decompressed_bytes",
    "max_redirects",
    "general_retry_limit",
    "retention_days",
)


class SourceRuntimeInputError(ValueError):
    """Approved runtime input is unavailable or inconsistent with durable state."""


class _StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RuntimeExecutionLimits(_StrictConfigModel):
    """Strict wire representation parsed only through the shared policy validator."""

    site_concurrency: StrictInt
    global_concurrency: StrictInt
    source_ttl_seconds: StrictInt
    max_response_bytes: StrictInt
    max_decompressed_bytes: StrictInt
    connect_timeout_seconds: StrictFloat
    read_timeout_seconds: StrictFloat
    max_redirects: StrictInt
    general_retry_limit: StrictInt
    retention_days: StrictInt

    @model_validator(mode="after")
    def validate_shared_limits(self) -> RuntimeExecutionLimits:
        try:
            parse_execution_limits(self.model_dump(mode="python"))
        except ExecutionPolicyUnconfigured as exc:
            raise ValueError(str(exc)) from None
        return self

    def to_execution_limits(self) -> ExecutionLimits:
        return parse_execution_limits(self.model_dump(mode="python"))


class RuntimeSourceConfig(_StrictConfigModel):
    policy_revision: PositiveStrictInt
    robots_permission: Permission
    result_version: PositiveStrictInt
    language: NonEmptyStrictStr | None
    redirect_robots_permissions: tuple[tuple[NonEmptyStrictStr, Permission], ...]
    limits: RuntimeExecutionLimits

    @field_validator("robots_permission", mode="before")
    @classmethod
    def parse_robots_permission(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                return Permission(value)
            except ValueError:
                raise ValueError("robots_permission must be an existing permission") from None
        return value

    @field_validator("redirect_robots_permissions", mode="before")
    @classmethod
    def normalize_redirect_permissions(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        normalized: list[tuple[object, object]] = []
        for item in value:
            if not isinstance(item, list | tuple) or len(item) != 2:
                return value
            url, raw_permission = item
            if isinstance(raw_permission, str):
                try:
                    permission: object = Permission(raw_permission)
                except ValueError:
                    raise ValueError(
                        "redirect robots permission must be an existing permission"
                    ) from None
            else:
                permission = raw_permission
            normalized.append((url, permission))
        return tuple(normalized)

    @property
    def execution_limits(self) -> ExecutionLimits:
        return self.limits.to_execution_limits()


class RuntimeSourceConfigFile(_StrictConfigModel):
    """Non-secret, immutable runtime configuration keyed by normalized Source UUID."""

    schema_version: Literal["w2.source-runtime-config.v1"]
    claim_lease_seconds: PositiveStrictInt
    sources: Annotated[Mapping[UUID, RuntimeSourceConfig], Field(min_length=1)]

    @field_validator("sources", mode="before")
    @classmethod
    def normalize_source_keys(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized: dict[UUID, object] = {}
        for raw_source_id, source_config in value.items():
            if isinstance(raw_source_id, UUID):
                source_id = raw_source_id
            elif isinstance(raw_source_id, str):
                try:
                    source_id = UUID(raw_source_id)
                except ValueError:
                    raise ValueError("runtime config Source key must be a UUID") from None
            else:
                raise ValueError("runtime config Source key must be a UUID")
            if source_id in normalized:
                raise ValueError("duplicate Source after UUID normalization")
            normalized[source_id] = source_config
        return normalized

    @field_serializer("sources")
    def serialize_sources(
        self,
        value: Mapping[UUID, RuntimeSourceConfig],
    ) -> dict[UUID, RuntimeSourceConfig]:
        return dict(value)

    @model_validator(mode="after")
    def validate_claim_lease(self) -> RuntimeSourceConfigFile:
        for source_config in self.sources.values():
            limits = source_config.execution_limits
            minimum_lease = (
                _hard_deadline_seconds(limits)
                + limits.connect_timeout_seconds
                + limits.read_timeout_seconds
            )
            if not math.isfinite(minimum_lease) or self.claim_lease_seconds <= minimum_lease:
                raise ValueError(
                    "claim lease must exceed collector deadline and connect/read timeouts"
                )
        object.__setattr__(self, "sources", MappingProxyType(dict(self.sources)))
        return self

    @property
    def heartbeat_interval_seconds(self) -> float:
        """Return the fixed renewal cadence used across child fetch and parent parsing."""

        return self.claim_lease_seconds / 3.0


def _reject_duplicate_json_object_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for key, value in pairs:
        if key in parsed:
            raise SourceRuntimeInputError("runtime config has a duplicate JSON object key")
        parsed[key] = value
    return parsed


def _reject_nonfinite_json_number(_value: str) -> NoReturn:
    raise SourceRuntimeInputError("runtime config contains a non-finite JSON number")


def _normalize_schema_integer_field(container: dict[str, object], field: str) -> None:
    value = container.get(field)
    if type(value) is float and math.isfinite(value) and value.is_integer():
        container[field] = int(value)


def _normalize_schema_integer_numbers(parsed: object) -> object:
    if not isinstance(parsed, dict):
        return parsed

    _normalize_schema_integer_field(parsed, "claim_lease_seconds")
    sources = parsed.get("sources")
    if not isinstance(sources, dict):
        return parsed

    for source in sources.values():
        if not isinstance(source, dict):
            continue
        for field in _SOURCE_INTEGER_FIELDS:
            _normalize_schema_integer_field(source, field)

        limits = source.get("limits")
        if not isinstance(limits, dict):
            continue
        for field in _LIMIT_INTEGER_FIELDS:
            _normalize_schema_integer_field(limits, field)

    return parsed


def parse_runtime_source_config_json(
    raw_json: str | bytes | bytearray,
) -> RuntimeSourceConfigFile:
    """Parse the approved wire config without allowing JSON key shadowing."""

    try:
        parsed = json.loads(
            raw_json,
            object_pairs_hook=_reject_duplicate_json_object_keys,
            parse_constant=_reject_nonfinite_json_number,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceRuntimeInputError("runtime config is not valid JSON") from exc
    return RuntimeSourceConfigFile.model_validate(_normalize_schema_integer_numbers(parsed))


class SqlAlchemyCollectionInputProvider:
    """Load one approved Source input in a short read transaction."""

    def __init__(
        self,
        session_factory: SessionFactory,
        config: RuntimeSourceConfigFile,
    ) -> None:
        self._session_factory = session_factory
        self._config = config

    @property
    def claim_lease_seconds(self) -> int:
        return self._config.claim_lease_seconds

    @property
    def heartbeat_interval_seconds(self) -> float:
        return self._config.heartbeat_interval_seconds

    def load(self, command: CollectionCommand) -> StaticCollectionInput:
        if (
            command.resume_stage is not CollectionStage.POLICY
            or command.policy_revision is not None
        ):
            raise SourceRuntimeInputError("runtime input requires an initial policy command")

        approved = self._config.sources.get(command.source_id)
        if approved is None:
            raise SourceRuntimeInputError("approved source config is missing")

        with self._session_factory() as session, session.begin():
            source = session.get(Source, command.source_id)
            if source is None:
                raise SourceRuntimeInputError("registered Source is missing")
            if source.company_id != command.company_id:
                raise SourceRuntimeInputError("Source/Company binding does not match")

            company = session.get(Company, command.company_id)
            if company is None or company.identity_status != "verified":
                raise SourceRuntimeInputError("Source company is not verified")

            policy = session.scalar(
                select(SourcePolicyDecision)
                .where(SourcePolicyDecision.source_id == command.source_id)
                .order_by(SourcePolicyDecision.revision.desc())
                .limit(1)
            )
            if policy is None:
                raise SourceRuntimeInputError("current Source policy is missing")
            if policy.revision != approved.policy_revision:
                raise SourceRuntimeInputError(
                    "approved policy revision does not match current policy"
                )

            aggregate_revision = session.scalar(
                select(func.coalesce(func.max(OutboxEvent.aggregate_revision), 0) + 1).where(
                    OutboxEvent.aggregate_id == command.source_id
                )
            )
            if (
                isinstance(aggregate_revision, bool)
                or not isinstance(aggregate_revision, int)
                or aggregate_revision <= 0
            ):
                raise SourceRuntimeInputError("next aggregate revision is unavailable")

            try:
                source_type = SourceType(source.source_type)
                mapped_policy = Policy(
                    policy_decision_id=policy.policy_decision_id,
                    official_status=OfficialStatus(policy.official_status),
                    access_class=AccessClass(policy.access_class),
                    collection_permission=Permission(policy.collection_permission),
                    excerpt_storage_permission=Permission(policy.excerpt_storage_permission),
                    body_storage_permission=Permission(policy.body_storage_permission),
                    redistribution_permission=Permission(policy.redistribution_permission),
                    checked_at=policy.checked_at,
                    policy_version=policy.policy_version,
                )
            except ValueError:
                raise SourceRuntimeInputError("registered Source policy data is invalid") from None

            return StaticCollectionInput(
                source_id=source.source_id,
                company_id=source.company_id,
                source_url=source.canonical_url,
                title=source.title,
                source_type=source_type,
                policy=mapped_policy,
                policy_revision=policy.revision,
                robots_permission=approved.robots_permission,
                limits=approved.execution_limits,
                result_version=approved.result_version,
                aggregate_revision=aggregate_revision,
                language=approved.language,
                redirect_robots_permissions=approved.redirect_robots_permissions,
            )
