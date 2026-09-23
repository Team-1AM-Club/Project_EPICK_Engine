"""Synthetic CT15 configuration and SDK boundaries; no AWS calls."""

from __future__ import annotations

import hashlib
import json
from threading import Event
from typing import Any
from unittest.mock import MagicMock

import pytest

from epick_engine.source_collection import commit_gate_operator
from epick_engine.source_collection.commit_gate_operator import (
    Ct15ConfigurationError,
    Ct15Settings,
    SqsGateQueue,
    main,
    preflight,
    run_loop,
)
from epick_engine.source_collection.commit_gate_runtime import RelayResult


def environment() -> dict[str, str]:
    return {
        "W2_CT15_ENABLED": "true",
        "W2_CT15_GATE_ONLY_QUEUE_APPROVED": "true",
        "W2_CT15_DATABASE_URL": "postgresql+psycopg://synthetic@localhost/epick_ct15",
        "W2_CT15_REGION": "ap-northeast-2",
        "W2_CT15_COMMAND_QUEUE_URL": (
            "https://sqs.ap-northeast-2.amazonaws.com/123456789012/test-ct15-command"
        ),
        "W2_CT15_INBOUND_QUEUE_URL": (
            "https://sqs.ap-northeast-2.amazonaws.com/123456789012/test-ct15-inbound"
        ),
        "W2_CT15_EXPECTED_W1_SENDER_ID": "AROASYNTHETICW1ROLE12",
        "W2_CT15_RUNTIME_LABEL": "epick-ct15-synthetic",
    }


@pytest.mark.parametrize("key", list(environment()))
def test_all_live_settings_require_explicit_values(key: str) -> None:
    values = environment()
    values.pop(key)
    with pytest.raises(Ct15ConfigurationError):
        Ct15Settings.from_environment(values)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("W2_CT15_ENABLED", "false"),
        ("W2_CT15_DATABASE_URL", "postgresql+psycopg://synthetic@localhost/production"),
        ("W2_CT15_DATABASE_URL", "sqlite:///ct15.db"),
        ("W2_CT15_RUNTIME_LABEL", "production"),
        ("W2_CT15_EXPECTED_W1_SENDER_ID", "AROASYNTHETICW1ROLE12:session"),
        ("W2_CT15_EXPECTED_W1_SENDER_ID", "arn:aws:iam::123456789012:role/ct15"),
        ("W2_CT15_COMMAND_QUEUE_URL", "https://attacker.test/123456789012/test-ct15"),
        (
            "W2_CT15_COMMAND_QUEUE_URL",
            "https://sqs.ap-northeast-2.amazonaws.com/123456789012/production",
        ),
        (
            "W2_CT15_COMMAND_QUEUE_URL",
            "https://sqs.ap-northeast-2.amazonaws.com/123456789012/test-ct15.fifo",
        ),
        ("W2_CT15_REGION", "us-east-1"),
    ],
)
def test_nonisolated_or_ambiguous_configuration_fails_closed(key: str, value: str) -> None:
    values = environment()
    values[key] = value
    with pytest.raises(Ct15ConfigurationError):
        Ct15Settings.from_environment(values)


def test_queue_routes_must_be_distinct_and_config_repr_has_no_secrets() -> None:
    values = environment()
    settings = Ct15Settings.from_environment(values)
    assert "synthetic@" not in repr(settings)
    assert "amazonaws.com" not in repr(settings)
    values["W2_CT15_INBOUND_QUEUE_URL"] = values["W2_CT15_COMMAND_QUEUE_URL"]
    with pytest.raises(Ct15ConfigurationError):
        Ct15Settings.from_environment(values)


class FakeSqs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.receive_response: dict[str, Any] = {}
        self.send_response: dict[str, Any] | None = None

    def receive_message(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("receive", kwargs))
        return self.receive_response

    def delete_message(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("delete", kwargs))
        return {}

    def send_message(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("send", kwargs))
        return self.send_response or {
            "MessageId": "synthetic-service-id",
            "MD5OfMessageBody": hashlib.md5(
                kwargs["MessageBody"].encode("utf-8"), usedforsecurity=False
            ).hexdigest(),
        }

    def get_queue_attributes(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("attributes", kwargs))
        name = kwargs["QueueUrl"].rsplit("/", 1)[-1]
        prefix = "arn:aws:sqs:ap-northeast-2:123456789012:"
        return {
            "Attributes": {
                "QueueArn": prefix + name,
                "SqsManagedSseEnabled": "true",
                "RedrivePolicy": json.dumps(
                    {"deadLetterTargetArn": prefix + name + "-dlq", "maxReceiveCount": "5"}
                ),
            }
        }


def test_sdk_receives_system_sender_id_and_preserves_receipt() -> None:
    sdk = FakeSqs()
    sdk.receive_response = {
        "Messages": [
            {
                "Body": '{"producer":"w1"}',
                "ReceiptHandle": "synthetic-receipt",
                "Attributes": {"SenderId": "AROASYNTHETICW1ROLE12:worker"},
            }
        ]
    }
    queue = SqsGateQueue(sdk, Ct15Settings.from_environment(environment()))
    messages = queue.receive()
    assert len(messages) == 1
    assert messages[0].sender_id == "AROASYNTHETICW1ROLE12:worker"
    assert messages[0].receipt_handle == "synthetic-receipt"
    assert sdk.calls[0][1]["MessageSystemAttributeNames"] == ["SenderId"]
    queue.delete(messages[0].receipt_handle)
    assert sdk.calls[1][1]["ReceiptHandle"] == "synthetic-receipt"


def test_sdk_send_checks_service_checksum_and_uses_only_inbound_route() -> None:
    sdk = FakeSqs()
    settings = Ct15Settings.from_environment(environment())
    queue = SqsGateQueue(sdk, settings)
    body = json.dumps({"text": "합성"}, ensure_ascii=False)
    queue.send(body)
    assert sdk.calls == [("send", {"QueueUrl": settings.inbound_queue_url, "MessageBody": body})]
    sdk.send_response = {"MessageId": "synthetic", "MD5OfMessageBody": "wrong"}
    with pytest.raises(RuntimeError, match="SQS delivery unconfirmed"):
        queue.send(body)


def test_sdk_errors_do_not_expose_payload_or_receipt() -> None:
    class BrokenSqs(FakeSqs):
        def send_message(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("PRIVATE-BODY-CANARY")

    queue = SqsGateQueue(BrokenSqs(), Ct15Settings.from_environment(environment()))
    with pytest.raises(RuntimeError) as caught:
        queue.send("PRIVATE-BODY-CANARY")
    assert "PRIVATE" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_preflight_accepts_only_private_deletion_receipt_migration_head() -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.side_effect = ["epick_ct15", "0009_private_deletion_receipt"]
    connection.scalars.return_value.all.return_value = ["0009_private_deletion_receipt"]
    sdk = FakeSqs()
    result = preflight(engine, sdk, Ct15Settings.from_environment(environment()))
    assert result["status"] == "PREFLIGHT_PASSED"
    assert [name for name, _ in sdk.calls] == ["attributes", "attributes"]
    assert connection.execute.call_count == 2


@pytest.mark.parametrize(
    "migration_revisions",
    [
        ("0004_private_commit_gate",),
        ("0005_private_gate_delivery",),
        ("0006_source_restriction",),
        ("0007_restriction_receipt",),
        ("0008_collection_runtime",),
        (),
        ("9999_unknown",),
        ("0009_private_deletion_receipt", "9999_unknown"),
        ("0009_private_deletion_receipt", "0009_private_deletion_receipt"),
    ],
)
def test_preflight_does_not_claim_readiness_for_incompatible_migration(
    migration_revisions: tuple[str, ...],
) -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    first_revision = migration_revisions[0] if migration_revisions else None
    connection.scalar.side_effect = ["epick_ct15", first_revision]
    connection.scalars.return_value.all.return_value = list(migration_revisions)
    sdk = FakeSqs()
    with pytest.raises(Ct15ConfigurationError, match="migration required"):
        preflight(engine, sdk, Ct15Settings.from_environment(environment()))
    assert not sdk.calls


@pytest.mark.parametrize("bad_attribute", ["QueueArn", "SqsManagedSseEnabled", "RedrivePolicy"])
def test_preflight_rejects_nonisolated_unencrypted_or_no_dlq_queue(bad_attribute: str) -> None:
    class BadQueue(FakeSqs):
        def get_queue_attributes(self, **kwargs: Any) -> dict[str, Any]:
            response = super().get_queue_attributes(**kwargs)
            response["Attributes"].pop(bad_attribute)
            return response

    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.side_effect = ["epick_ct15", "0009_private_deletion_receipt"]
    connection.scalars.return_value.all.return_value = ["0009_private_deletion_receipt"]
    with pytest.raises(Ct15ConfigurationError):
        preflight(engine, BadQueue(), Ct15Settings.from_environment(environment()))


def test_runtime_stops_after_inflight_delivery_and_emits_only_safe_status(
    monkeypatch, capsys
) -> None:
    stop = Event()
    calls = []

    def finish_current(_sessions, _queue):
        calls.append("sent")
        stop.set()
        return RelayResult(status="SENT")

    monkeypatch.setattr(
        "epick_engine.source_collection.commit_gate_operator.relay_once", finish_current
    )
    assert run_loop("relay", MagicMock(), MagicMock(), "synthetic", stop) == 0
    assert calls == ["sent"]
    assert json.loads(capsys.readouterr().out) == {"status": "SENT"}


def test_inspect_run_uses_explicit_fixture_after_existing_preflight(
    monkeypatch, capsys, tmp_path
) -> None:
    settings = Ct15Settings.from_environment(environment())
    engine = MagicMock()
    client = MagicMock()
    sessions = MagicMock()
    session = sessions.return_value.__enter__.return_value
    scope = object()
    output = {
        "schema_version": "w2.ct15.run-inspection.v1",
        "run_id": "ct15-synthetic-joint-1",
        "counts": {"primary": {}, "secondary": {}, "total": {}},
        "source_verification": {"primary": "absent", "secondary": "absent"},
    }
    preflight_calls = []
    input_path = tmp_path / "scope.json"
    input_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        commit_gate_operator.Ct15Settings,
        "from_environment",
        classmethod(lambda _cls, _values: settings),
    )
    monkeypatch.setattr(commit_gate_operator, "create_ct15_engine", lambda _settings: engine)
    monkeypatch.setattr(commit_gate_operator, "create_sqs_client", lambda _settings: client)
    monkeypatch.setattr(
        commit_gate_operator,
        "preflight",
        lambda *_args: preflight_calls.append("passed") or {"status": "PREFLIGHT_PASSED"},
    )
    monkeypatch.setattr(commit_gate_operator, "sessionmaker", lambda *_args, **_kwargs: sessions)
    monkeypatch.setattr(commit_gate_operator, "load_run_scope", lambda path: scope)
    monkeypatch.setattr(
        commit_gate_operator,
        "inspect_run_counts",
        lambda actual_session, actual_scope: (
            output if (actual_session, actual_scope) == (session, scope) else None
        ),
    )

    assert main(["inspect-run", "--input", str(input_path)]) == 0
    assert preflight_calls == ["passed"]
    assert json.loads(capsys.readouterr().out) == output
