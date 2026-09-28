"""Contract tests for W2-owned direct Source registration metadata and ACK values."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from epick_engine.source_collection.contracts import SourceType
from epick_engine.source_collection.w1_transport import (
    W1DirectSourceRegistrationDispatch,
    W1WireContractError,
    parse_w1_dispatch,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
W1 = FIXTURES / "w1_private_contract"
ONBOARDING = FIXTURES / "w2_source_onboarding"
CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "w2-private"


def _codec():
    name = "epick_engine.source_collection.source_onboarding_contracts"
    assert importlib.util.find_spec(name) is not None, "Source onboarding codec is missing"
    return importlib.import_module(name)


def _load(directory: Path, name: str) -> dict:
    return json.loads((directory / name).read_text(encoding="utf-8"))


def _dispatch() -> W1DirectSourceRegistrationDispatch:
    dispatch = parse_w1_dispatch(_load(W1, "private-w2-direct-source-registration-dispatch.json"))
    assert isinstance(dispatch, W1DirectSourceRegistrationDispatch)
    return dispatch


def _available() -> dict:
    return _load(ONBOARDING, "registration-digest-vector.json")["metadata"]


def _unavailable() -> dict:
    raw = _available()
    return {
        key: value
        for key, value in raw.items()
        if key
        in {
            "schema_version",
            "command_id",
            "execution_fence",
            "owner_deletion_epoch",
            "company_id",
            "source_id",
        }
    } | {"status": "UNAVAILABLE", "reason_code": "REGISTRATION_NOT_AVAILABLE"}


def test_same_source_different_url_is_not_silently_normalized() -> None:
    raw = _available()
    w1_canonical_url = "https://SYNTHETIC-MERIDIAN-A.TEST/jobs/%ED%94%8C%EB%9E%AB%ED%8F%BC?lang=ko"
    raw["canonical_url"] = w1_canonical_url

    metadata = _codec().parse_registration_metadata(raw, _dispatch())

    assert metadata.canonical_url == w1_canonical_url
    assert metadata.model_dump(mode="json")["canonical_url"] == w1_canonical_url


@pytest.mark.parametrize(
    "canonical_url",
    [
        "mailto:x@synthetic.invalid",
        "ftp://synthetic.invalid/source",
        "not-a-url",
    ],
)
def test_available_rejects_non_https_or_malformed_canonical_url(canonical_url: str) -> None:
    raw = _available()
    raw["canonical_url"] = canonical_url

    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(raw, _dispatch())


def test_available_metadata_is_strict_and_bound_to_the_dispatch() -> None:
    raw = _available()
    metadata = _codec().parse_registration_metadata(raw, _dispatch())

    assert metadata.status == "AVAILABLE"
    assert metadata.model_dump(mode="json") == raw


@pytest.mark.parametrize(
    "field",
    [
        "canonical_url",
        "w1_source_type",
        "registration_input_version",
        "company_official_domain",
        "company_legal_name",
        "company_legal_identifiers",
        "company_identity_evidence_refs",
    ],
)
def test_available_requires_every_approval_input_and_no_reason(field: str) -> None:
    raw = _available()
    del raw[field]
    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(raw, _dispatch())

    raw = _available()
    raw["reason_code"] = "SHOULD_NOT_BE_PRESENT"
    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(raw, _dispatch())


@pytest.mark.parametrize(
    "field",
    [
        "canonical_url",
        "w1_source_type",
        "registration_input_version",
        "company_official_domain",
        "company_legal_name",
        "company_legal_identifiers",
        "company_identity_evidence_refs",
    ],
)
def test_unavailable_forbids_every_available_only_field_even_when_null(field: str) -> None:
    raw = _unavailable()
    metadata = _codec().parse_registration_metadata(raw, _dispatch())
    assert metadata.status == "UNAVAILABLE"
    assert metadata.reason_code == "REGISTRATION_NOT_AVAILABLE"

    raw[field] = None
    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(raw, _dispatch())


def test_available_rejects_empty_company_legal_name() -> None:
    raw = _available()
    raw["company_legal_name"] = ""

    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(raw, _dispatch())


@pytest.mark.parametrize("field", ["company_official_domain", "company_legal_name"])
@pytest.mark.parametrize("value", [" \t", " leading", "trailing ", "\nleading", "trailing\n"])
def test_available_rejects_ambiguous_company_identity_scalar_whitespace(
    field: str, value: str
) -> None:
    raw = _available()
    raw[field] = value

    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(raw, _dispatch())


@pytest.mark.parametrize("field", ["company_legal_identifiers", "company_identity_evidence_refs"])
@pytest.mark.parametrize("value", [" \t", " leading", "trailing ", "\nleading", "trailing\n"])
def test_available_rejects_ambiguous_company_identity_list_item_whitespace(
    field: str, value: str
) -> None:
    raw = _available()
    raw[field] = [*raw[field], value]

    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(raw, _dispatch())


@pytest.mark.parametrize(
    "identifier",
    [
        "KR-SYNTHETIC-01",
        ":KR-SYNTHETIC-01",
        "registration_number:",
        " registration_number:KR-SYNTHETIC-01",
        "registration_number :KR-SYNTHETIC-01",
        "registration_number: KR-SYNTHETIC-01",
        "registration_number:KR-SYNTHETIC-01 ",
    ],
)
def test_available_requires_exact_kind_value_legal_identifier(identifier: str) -> None:
    raw = _available()
    raw["company_legal_identifiers"] = [identifier]

    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(raw, _dispatch())


def test_available_legal_identifier_value_may_contain_colons_without_rewriting() -> None:
    raw = _available()
    identifier = "registration_number:KR:SYNTHETIC:01"
    raw["company_legal_identifiers"] = [identifier]

    metadata = _codec().parse_registration_metadata(raw, _dispatch())

    assert metadata.company_legal_identifiers == [identifier]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("command_id", "40000000-0000-4000-8000-000000000099"),
        ("execution_fence", 2),
        ("owner_deletion_epoch", 1),
        ("company_id", "40000000-0000-4000-8000-000000000099"),
        ("source_id", "40000000-0000-4000-8000-000000000099"),
        ("registration_input_version", "direct:synthetic:different"),
    ],
)
def test_metadata_rejects_every_dispatch_binding_mismatch(field: str, replacement: object) -> None:
    raw = _available()
    raw[field] = replacement
    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(raw, _dispatch())


@pytest.mark.parametrize("raw", [_available(), _unavailable()])
def test_metadata_rejects_unknown_and_duplicate_json_keys(raw: dict) -> None:
    raw["unexpected"] = "synthetic-private-marker"
    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(raw, _dispatch())

    encoded = json.dumps({key: value for key, value in raw.items() if key != "unexpected"})
    duplicate = encoded.replace(
        '"status": "AVAILABLE"' if raw["status"] == "AVAILABLE" else '"status": "UNAVAILABLE"',
        (
            '"status": "AVAILABLE", "status": "AVAILABLE"'
            if raw["status"] == "AVAILABLE"
            else '"status": "UNAVAILABLE", "status": "UNAVAILABLE"'
        ),
        1,
    )
    with pytest.raises(W1WireContractError):
        _codec().parse_registration_metadata(duplicate, _dispatch())


def test_digest_matches_independently_fixed_utf8_vector() -> None:
    vector = _load(ONBOARDING, "registration-digest-vector.json")
    metadata = _codec().parse_registration_metadata(vector["metadata"], _dispatch())

    assert (
        hashlib.sha256(vector["canonical_json"].encode("utf-8")).hexdigest()
        == vector["expected_digest"]
    )
    assert _codec().registration_digest(metadata) == vector["expected_digest"]


def test_digest_normalizes_only_documented_arrays_before_hashing() -> None:
    codec = _codec()
    raw = _available()
    expected = codec.registration_digest(codec.parse_registration_metadata(raw, _dispatch()))
    raw["company_legal_identifiers"] = list(
        reversed(raw["company_legal_identifiers"] + ["registration_number:KR-SYNTHETIC-01"])
    )
    raw["company_identity_evidence_refs"] = list(
        reversed(raw["company_identity_evidence_refs"] + ["evidence:synthetic:alpha"])
    )

    assert (
        codec.registration_digest(codec.parse_registration_metadata(raw, _dispatch())) == expected
    )


def test_company_legal_name_is_part_of_registration_digest() -> None:
    codec = _codec()
    original = _available()
    changed = _available()
    changed["company_legal_name"] = "Synthetic Meridian A Holdings Co., Ltd."

    assert codec.registration_digest(
        codec.parse_registration_metadata(original, _dispatch())
    ) != codec.registration_digest(codec.parse_registration_metadata(changed, _dispatch()))


@pytest.mark.parametrize(
    ("wire_value", "expected"),
    [
        ("JOB_POSTING", SourceType.JOB_POSTING),
        ("COMPANY_PROFILE", SourceType.COMPANY_WEBSITE),
    ],
)
def test_only_the_two_w1_source_types_are_mapped(wire_value: str, expected: SourceType) -> None:
    assert _codec().map_w1_source_type(wire_value) is expected


@pytest.mark.parametrize("wire_value", ["job_posting", "PRESS_RELEASE", "", None, True])
def test_unknown_w1_source_types_are_rejected(wire_value: object) -> None:
    with pytest.raises(W1WireContractError):
        _codec().map_w1_source_type(wire_value)


def test_ready_ack_requires_positive_policy_and_rule_revisions() -> None:
    codec = _codec()
    raw = _load(ONBOARDING, "registration-ack-ready.json")
    ack = codec.RegistrationAck.model_validate(raw)
    assert ack.model_dump(mode="json") == raw

    for field in ["policy_revision", "approval_rule_revision"]:
        for invalid in [None, 0, True, "1"]:
            changed = deepcopy(raw)
            changed[field] = invalid
            with pytest.raises(ValidationError):
                codec.RegistrationAck.model_validate(changed)


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        ("HELD", "POLICY_RULE_MISSING"),
        ("HELD", "COMPANY_UNVERIFIED"),
        ("HELD", "URL_NORMALIZATION_MISMATCH"),
        ("HELD", "UNSUPPORTED_SOURCE_TYPE"),
        ("REJECTED", "SOURCE_ID_CONFLICT"),
        ("REJECTED", "CANONICAL_URL_CONFLICT"),
        ("REJECTED", "EXPLICIT_POLICY_DENIAL"),
    ],
)
def test_held_and_rejected_ack_require_null_policy_and_rule_revisions(
    status: str, reason_code: str
) -> None:
    codec = _codec()
    raw = _load(ONBOARDING, "registration-ack-ready.json")
    raw.update(
        status=status,
        reason_code=reason_code,
        policy_revision=None,
        approval_rule_id=None,
        approval_rule_revision=None,
    )
    ack = codec.RegistrationAck.model_validate(raw)
    assert ack.model_dump(mode="json") == raw

    raw["policy_revision"] = 1
    with pytest.raises(ValidationError):
        codec.RegistrationAck.model_validate(raw)


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        ("READY", "POLICY_RULE_MISSING"),
        ("HELD", "APPROVED"),
        ("REJECTED", "UNSUPPORTED_SOURCE_TYPE"),
    ],
)
def test_ack_reason_codes_are_exactly_partitioned_by_status(status: str, reason_code: str) -> None:
    codec = _codec()
    raw = _load(ONBOARDING, "registration-ack-ready.json")
    raw.update(status=status, reason_code=reason_code)
    if status != "READY":
        raw.update(policy_revision=None, approval_rule_id=None, approval_rule_revision=None)
    with pytest.raises(ValidationError):
        codec.RegistrationAck.model_validate(raw)


def test_ack_schema_and_model_reject_unknown_fields() -> None:
    codec = _codec()
    raw = _load(ONBOARDING, "registration-ack-ready.json")
    schema = _load(CONTRACTS, "source-registration-ack.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(raw)

    raw["unexpected"] = "synthetic-private-marker"
    assert list(validator.iter_errors(raw))
    with pytest.raises(ValidationError):
        codec.RegistrationAck.model_validate(raw)


def test_proposed_lookup_schema_matches_model_and_status_shapes() -> None:
    schema_path = CONTRACTS / "w1-source-registration-lookup.proposed.schema.json"
    assert schema_path.is_file(), "W2 proposed W1 lookup schema is missing"

    codec = _codec()
    schema = _load(CONTRACTS, schema_path.name)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    assert set(schema["properties"]) == set(codec.RegistrationMetadata.model_fields)
    validator.validate(_available())
    validator.validate(_unavailable())

    invalid_available = _available()
    invalid_available["company_legal_name"] = ""
    assert list(validator.iter_errors(invalid_available))

    for field in ("company_official_domain", "company_legal_name"):
        for value in (" \t", " leading", "trailing ", "\nleading", "trailing\n"):
            invalid_available = _available()
            invalid_available[field] = value
            assert list(validator.iter_errors(invalid_available))

    for field in ("company_legal_identifiers", "company_identity_evidence_refs"):
        for value in (" \t", " leading", "trailing ", "\nleading", "trailing\n"):
            invalid_available = _available()
            invalid_available[field] = [*invalid_available[field], value]
            assert list(validator.iter_errors(invalid_available))

    for identifier in (
        "KR-SYNTHETIC-01",
        ":KR-SYNTHETIC-01",
        "registration_number:",
        "registration_number :KR-SYNTHETIC-01",
        "registration_number: KR-SYNTHETIC-01",
    ):
        invalid_available = _available()
        invalid_available["company_legal_identifiers"] = [identifier]
        assert list(validator.iter_errors(invalid_available))

    invalid_unavailable = _unavailable() | {"company_legal_name": "Synthetic Meridian A Co., Ltd."}
    assert list(validator.iter_errors(invalid_unavailable))
