"""One-shot HTTPS client for W1's protected private-authority decisions."""

from __future__ import annotations

import json
import ssl
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from epick_engine.source_collection.private_deletion_v2 import PrivateDeletionScope
from epick_engine.source_collection.w1_lookup_client import (
    DEFAULT_LOOKUP_TIMEOUT_SECONDS,
    MAX_LOOKUP_REQUEST_BYTES,
    MAX_LOOKUP_RESPONSE_BYTES,
    LookupHTTPResponse,
    LookupHTTPTransport,
    W1LookupClientError,
    _decode_strict_json,
    _json_content_type_supported,
    _require_verified_tls,
    _StdlibHTTPSLookupTransport,
    _validate_bearer,
    validate_lookup_endpoint,
)
from epick_engine.source_collection.w1_private_authority_contracts import (
    CleanupKind,
    CurrentWriteScopeLookupRequest,
    CurrentWriteScopeLookupResponse,
    GateAuthorityRequest,
    GateAuthorityResponse,
    GatePhase,
    GateScopeLookupRequest,
    GateScopeLookupResponse,
    PrivateWriteAuthorityRequest,
    PrivateWriteAuthorityResponse,
    TerminalCleanupAuthorityRequest,
    TerminalCleanupAuthorityResponse,
    W1GateBinding,
    W1PrivateBinding,
    validate_private_echo,
)
from epick_engine.source_collection.w1_transport import (
    W1WireContractError,
    _parse_wire,
)

CURRENT_SCOPE_TARGET = "/internal/v1/w2-private/current-write-scope-lookup"
WRITE_AUTHORITY_TARGET = "/internal/v1/w2-private/authority"
GATE_SCOPE_TARGET = "/internal/v1/w2-private/gate-scope-lookup"
GATE_AUTHORITY_TARGET = "/internal/v1/w2-private/gate-authority"
TERMINAL_CLEANUP_TARGET = "/internal/v1/w2-private/terminal-cleanup-authority"

_PROTECTED_TARGETS = frozenset(
    {
        CURRENT_SCOPE_TARGET,
        WRITE_AUTHORITY_TARGET,
        GATE_SCOPE_TARGET,
        GATE_AUTHORITY_TARGET,
        TERMINAL_CLEANUP_TARGET,
    }
)


def _binding_payload(binding: object) -> dict[str, object]:
    if not isinstance(binding, W1PrivateBinding):
        raise W1WireContractError("invalid W1 private authority binding")
    return {
        "owner_user_id": binding.owner_user_id,
        "owner_deletion_epoch": binding.owner_deletion_epoch,
        "command_id": binding.command_id,
        "job_id": binding.job_id,
        "execution_fence": binding.execution_fence,
    }


def _gate_payload(gate: object) -> dict[str, object]:
    if not isinstance(gate, W1GateBinding):
        raise W1WireContractError("invalid W1 private gate binding")
    payload = {
        **_binding_payload(gate.private),
        "operation_id": gate.operation_id,
        "operation_revision": gate.operation_revision,
        "action": gate.action,
        "result_digest": gate.result_digest,
    }
    if gate.purge_owner_deletion_epoch is not None:
        payload["purge_owner_deletion_epoch"] = gate.purge_owner_deletion_epoch
    return payload


def _scope_payload(scope: object) -> dict[str, str]:
    if not isinstance(scope, PrivateDeletionScope):
        raise W1WireContractError("invalid W1 private authority scope")
    if scope.kind == "ACCOUNT" and scope.project_id is None:
        return {"type": "ACCOUNT"}
    if scope.kind == "PROJECT" and isinstance(scope.project_id, UUID):
        return {"type": "PROJECT", "project_id": str(scope.project_id)}
    raise W1WireContractError("invalid W1 private authority scope")


def _request_model[M: BaseModel](model: type[M], payload: dict[str, object], *, label: str) -> M:
    try:
        return model.model_validate(payload, strict=True)
    except (TypeError, ValueError):
        raise W1WireContractError(f"invalid {label}") from None


class W1PrivateAuthorityClient:
    """Issue exactly one authenticated POST for each private-authority request."""

    __slots__ = ("_bearer", "_endpoint", "_ssl_context", "_transport")

    def __init__(
        self,
        *,
        endpoint: str,
        bearer: str,
        ssl_context: ssl.SSLContext,
        transport: LookupHTTPTransport | None = None,
    ) -> None:
        self._endpoint = validate_lookup_endpoint(endpoint)
        self._bearer = _validate_bearer(bearer)
        self._ssl_context = _require_verified_tls(ssl_context)
        self._transport = _StdlibHTTPSLookupTransport() if transport is None else transport

    def __repr__(self) -> str:
        return "W1PrivateAuthorityClient(endpoint=<redacted>, bearer=<redacted>)"

    def _post[M: BaseModel, R: BaseModel](
        self,
        *,
        target: str,
        request: M,
        response_model: type[R],
        response_label: str,
    ) -> R:
        if target not in _PROTECTED_TARGETS:
            raise W1LookupClientError("INVALID_TARGET")
        try:
            payload: dict[str, Any] = request.model_dump(
                mode="json",
                warnings="error",
                exclude_none=True,
            )
            body = json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise W1WireContractError("invalid W1 private authority request") from None
        if len(body) > MAX_LOOKUP_REQUEST_BYTES:
            raise W1LookupClientError("REQUEST_TOO_LARGE")

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._bearer}",
            "Content-Length": str(len(body)),
            "Content-Type": "application/json",
            "X-EPICK-Service-Principal": "w2",
        }
        context = _require_verified_tls(self._ssl_context)
        response: object | None = None
        transport_failed = False
        try:
            response = self._transport.post(
                host=self._endpoint.host,
                port=self._endpoint.port,
                target=target,
                headers=headers,
                body=body,
                timeout=DEFAULT_LOOKUP_TIMEOUT_SECONDS,
                ssl_context=context,
                max_response_bytes=MAX_LOOKUP_RESPONSE_BYTES,
            )
        except Exception:
            transport_failed = True
        if transport_failed:
            raise W1LookupClientError("TRANSPORT_FAILURE") from None

        if not isinstance(response, LookupHTTPResponse):
            raise W1LookupClientError("INVALID_TRANSPORT_RESPONSE")
        if (
            type(response.status) is not int
            or not 100 <= response.status <= 599
            or not isinstance(response.body, bytes)
            or not isinstance(response.content_type, str | type(None))
        ):
            raise W1LookupClientError("INVALID_TRANSPORT_RESPONSE")
        if len(response.body) > MAX_LOOKUP_RESPONSE_BYTES:
            raise W1LookupClientError("RESPONSE_TOO_LARGE")
        if not _json_content_type_supported(response.content_type):
            raise W1LookupClientError("UNSUPPORTED_RESPONSE_CONTENT")

        decoded: object | None = None
        decode_error: str | None = None
        try:
            decoded = _decode_strict_json(response.body)
        except W1LookupClientError as error:
            decode_error = error.code
        if decode_error is not None:
            raise W1LookupClientError(decode_error) from None
        if response.status != 200:
            raise W1LookupClientError(f"HTTP_{response.status}")
        parsed = _parse_wire(decoded, response_model, label=response_label)
        validate_private_echo(request, parsed)
        return parsed

    def lookup_current_scope(self, binding: W1PrivateBinding) -> CurrentWriteScopeLookupResponse:
        request = _request_model(
            CurrentWriteScopeLookupRequest,
            {
                "schema_version": "w1.private.w2-current-write-scope-lookup.v1",
                **_binding_payload(binding),
            },
            label="W1 current-write scope lookup request",
        )
        return self._post(
            target=CURRENT_SCOPE_TARGET,
            request=request,
            response_model=CurrentWriteScopeLookupResponse,
            response_label="W1 current-write scope lookup response",
        )

    def authorize_write(
        self,
        binding: W1PrivateBinding,
        scope: PrivateDeletionScope,
    ) -> PrivateWriteAuthorityResponse:
        request = _request_model(
            PrivateWriteAuthorityRequest,
            {
                "schema_version": "w1.private.w2-write-authority.v1",
                **_binding_payload(binding),
                "scope": _scope_payload(scope),
            },
            label="W1 private write authority request",
        )
        return self._post(
            target=WRITE_AUTHORITY_TARGET,
            request=request,
            response_model=PrivateWriteAuthorityResponse,
            response_label="W1 private write authority response",
        )

    def lookup_gate_scope(
        self,
        gate: W1GateBinding,
        phase: GatePhase,
    ) -> GateScopeLookupResponse:
        request = _request_model(
            GateScopeLookupRequest,
            {
                "schema_version": "w1.private.w2-gate-scope-lookup.v1",
                **_gate_payload(gate),
                "phase": phase,
            },
            label="W1 gate scope lookup request",
        )
        return self._post(
            target=GATE_SCOPE_TARGET,
            request=request,
            response_model=GateScopeLookupResponse,
            response_label="W1 gate scope lookup response",
        )

    def authorize_gate(
        self,
        gate: W1GateBinding,
        phase: GatePhase,
        scope: PrivateDeletionScope,
    ) -> GateAuthorityResponse:
        request = _request_model(
            GateAuthorityRequest,
            {
                "schema_version": "w1.private.w2-gate-authority.v1",
                **_gate_payload(gate),
                "scope": _scope_payload(scope),
                "phase": phase,
            },
            label="W1 gate authority request",
        )
        return self._post(
            target=GATE_AUTHORITY_TARGET,
            request=request,
            response_model=GateAuthorityResponse,
            response_label="W1 gate authority response",
        )

    def authorize_terminal_cleanup(
        self,
        binding: W1PrivateBinding,
        scope: PrivateDeletionScope,
        cleanup_kind: CleanupKind,
    ) -> TerminalCleanupAuthorityResponse:
        request = _request_model(
            TerminalCleanupAuthorityRequest,
            {
                "schema_version": "w1.private.w2-terminal-cleanup.v1",
                **_binding_payload(binding),
                "scope": _scope_payload(scope),
                "cleanup_kind": cleanup_kind,
            },
            label="W1 terminal cleanup authority request",
        )
        return self._post(
            target=TERMINAL_CLEANUP_TARGET,
            request=request,
            response_model=TerminalCleanupAuthorityResponse,
            response_label="W1 terminal cleanup authority response",
        )
