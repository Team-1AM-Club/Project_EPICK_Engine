"""Pure W2 contract values for proposed direct Source onboarding.

The W1 lookup wire remains a proposal until W1 publishes a pinned schema.  The
ACK model is W2-owned, but this module performs no HTTP, queue, persistence, or
collection work.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from epick_engine.source_collection.contracts import ContractModel, SourceType
from epick_engine.source_collection.service import canonicalize_source_url
from epick_engine.source_collection.w1_transport import (
    NonNegativeWireInt,
    PositiveWireInt,
    W1DirectSourceRegistrationDispatch,
    W1WireContractError,
    _parse_wire,
    _revalidate_model,
)

NonEmptyWireStr = Annotated[str, Field(strict=True, min_length=1)]
RegistrationDigest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
RegistrationStatus = Literal["READY", "HELD", "REJECTED"]
RegistrationReasonCode = Literal[
    "APPROVED",
    "POLICY_RULE_MISSING",
    "COMPANY_UNVERIFIED",
    "URL_NORMALIZATION_MISMATCH",
    "UNSUPPORTED_SOURCE_TYPE",
    "SOURCE_ID_CONFLICT",
    "CANONICAL_URL_CONFLICT",
    "EXPLICIT_POLICY_DENIAL",
]

_AVAILABLE_ONLY_FIELDS = frozenset(
    {
        "canonical_url",
        "w1_source_type",
        "registration_input_version",
        "company_official_domain",
        "company_legal_identifiers",
        "company_identity_evidence_refs",
    }
)
_HELD_REASONS = frozenset(
    {
        "POLICY_RULE_MISSING",
        "COMPANY_UNVERIFIED",
        "URL_NORMALIZATION_MISMATCH",
        "UNSUPPORTED_SOURCE_TYPE",
    }
)
_REJECTED_REASONS = frozenset(
    {
        "SOURCE_ID_CONFLICT",
        "CANONICAL_URL_CONFLICT",
        "EXPLICIT_POLICY_DENIAL",
    }
)


class RegistrationMetadata(ContractModel):
    """Strict proposed W1 lookup response bound to one direct dispatch."""

    schema_version: Literal["w1.private.w2-source-registration-lookup.v1"]
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    command_id: UUID
    execution_fence: PositiveWireInt
    owner_deletion_epoch: NonNegativeWireInt
    company_id: UUID
    source_id: UUID
    canonical_url: NonEmptyWireStr | None = None
    w1_source_type: NonEmptyWireStr | None = None
    registration_input_version: NonEmptyWireStr | None = None
    company_official_domain: NonEmptyWireStr | None = None
    company_legal_identifiers: list[NonEmptyWireStr] | None = None
    company_identity_evidence_refs: list[NonEmptyWireStr] | None = None
    reason_code: NonEmptyWireStr | None = None

    @model_validator(mode="after")
    def validate_status_shape(self) -> RegistrationMetadata:
        present_available = _AVAILABLE_ONLY_FIELDS.intersection(self.model_fields_set)
        if self.status == "AVAILABLE":
            if (
                present_available != _AVAILABLE_ONLY_FIELDS
                or "reason_code" in self.model_fields_set
            ):
                raise ValueError("AVAILABLE requires only the complete approval input")
            if (
                self.canonical_url is None
                or self.w1_source_type is None
                or self.registration_input_version is None
                or self.company_official_domain is None
                or not self.company_legal_identifiers
                or not self.company_identity_evidence_refs
            ):
                raise ValueError("AVAILABLE requires non-empty approval input")
            try:
                canonical = canonicalize_source_url(self.canonical_url)
            except ValueError:
                raise ValueError("AVAILABLE requires a canonical HTTPS URL") from None
            if canonical != self.canonical_url:
                raise ValueError("W1 canonical URL differs from W2 normalization")
        elif (
            present_available
            or "reason_code" not in self.model_fields_set
            or self.reason_code is None
        ):
            raise ValueError("UNAVAILABLE requires only a reason")
        return self

    @model_serializer(mode="wrap")
    def omit_inapplicable_fields(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        raw: dict[str, object] = handler(self)
        return {name: value for name, value in raw.items() if value is not None}


class RegistrationAck(ContractModel):
    """W2-owned private ACK; READY is registration approval, never collection success."""

    schema_version: Literal["w2.private.source-registration-ack.v1"]
    command_id: UUID
    job_id: UUID
    authenticated_owner_ref: UUID
    project_ref: str | None
    company_id: UUID
    source_id: UUID
    execution_fence: PositiveWireInt
    owner_deletion_epoch: NonNegativeWireInt
    registration_digest: RegistrationDigest
    status: RegistrationStatus
    reason_code: RegistrationReasonCode
    policy_revision: PositiveWireInt | None
    approval_rule_id: UUID | None
    approval_rule_revision: PositiveWireInt | None

    @model_validator(mode="after")
    def validate_status_shape(self) -> RegistrationAck:
        revisions = (
            self.policy_revision,
            self.approval_rule_id,
            self.approval_rule_revision,
        )
        if self.status == "READY":
            if self.reason_code != "APPROVED" or any(value is None for value in revisions):
                raise ValueError("READY requires APPROVED and positive policy/rule revisions")
        elif self.status == "HELD":
            if self.reason_code not in _HELD_REASONS or any(
                value is not None for value in revisions
            ):
                raise ValueError("HELD requires its fixed reason and null policy/rule revisions")
        elif self.reason_code not in _REJECTED_REASONS or any(
            value is not None for value in revisions
        ):
            raise ValueError("REJECTED requires its fixed reason and null policy/rule revisions")
        return self


class _DuplicateJsonKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateJsonKey
        value[key] = item
    return value


def _decode_metadata_input(raw: object) -> object:
    if not isinstance(raw, str | bytes | bytearray):
        return raw
    try:
        return json.loads(raw, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError, _DuplicateJsonKey, TypeError):
        raise W1WireContractError("invalid W1 source registration metadata") from None


def parse_registration_metadata(
    raw: object, dispatch: W1DirectSourceRegistrationDispatch
) -> RegistrationMetadata:
    """Parse and bind one proposed lookup response without repairing private data."""

    if not isinstance(dispatch, W1DirectSourceRegistrationDispatch):
        raise W1WireContractError("invalid W1 source registration dispatch context")
    dispatch = _revalidate_model(
        dispatch,
        W1DirectSourceRegistrationDispatch,
        label="W1 direct registration dispatch",
    )
    metadata = _parse_wire(
        _decode_metadata_input(raw),
        RegistrationMetadata,
        label="W1 source registration metadata",
    )
    command = dispatch.payload
    pin = dispatch.direct_source_registration_pin
    if (
        metadata.command_id != command.command_id
        or metadata.execution_fence != dispatch.lookup_request.execution_fence
        or metadata.owner_deletion_epoch != command.owner_deletion_epoch
        or metadata.company_id != command.company_id
        or metadata.source_id != command.source_id
        or (
            metadata.status == "AVAILABLE"
            and metadata.registration_input_version != pin.registration_input_version
        )
    ):
        raise W1WireContractError("W1 source registration metadata binding mismatch")
    return metadata


def registration_digest(metadata: RegistrationMetadata) -> str:
    """Hash only the documented AVAILABLE approval inputs as canonical UTF-8 JSON."""

    if not isinstance(metadata, RegistrationMetadata):
        raise W1WireContractError("invalid W1 source registration digest input")
    metadata = _revalidate_model(
        metadata, RegistrationMetadata, label="W1 source registration metadata"
    )
    if metadata.status != "AVAILABLE":
        raise W1WireContractError("UNAVAILABLE metadata has no registration digest")
    raw = {
        "canonical_url": metadata.canonical_url,
        "company_id": str(metadata.company_id),
        "company_identity_evidence_refs": sorted(
            set(metadata.company_identity_evidence_refs or [])
        ),
        "company_legal_identifiers": sorted(set(metadata.company_legal_identifiers or [])),
        "company_official_domain": metadata.company_official_domain,
        "registration_input_version": metadata.registration_input_version,
        "source_id": str(metadata.source_id),
        "w1_source_type": metadata.w1_source_type,
    }
    try:
        encoded = json.dumps(
            raw,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise W1WireContractError("invalid W1 source registration digest input") from None
    return hashlib.sha256(encoded).hexdigest()


def map_w1_source_type(value: str) -> SourceType:
    """Map only the two W1 purpose values accepted by this onboarding proposal."""

    if value == "JOB_POSTING":
        return SourceType.JOB_POSTING
    if value == "COMPANY_PROFILE":
        return SourceType.COMPANY_WEBSITE
    raise W1WireContractError("unsupported W1 source type")
