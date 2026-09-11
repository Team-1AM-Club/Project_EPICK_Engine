"""RED contract for T032's semantic static-posting parser.

Fixed public boundary::

    parse_static_posting(parsed: StaticParseResult) -> StaticPostingParseResult

The semantic parser consumes T023's locator-verified ``StaticParseResult``; it
does not reparse the original HTML.  Its result exposes ordered ``sections``
whose drafts carry ``section_key``, ``kind``, ``heading_raw``, ``text_raw``,
``evidence_keys``, ``order``, and ``relation_text``.  ``evidence_keys`` refer
to input ``EvidenceDraft.evidence_key`` values until persistence assigns UUIDs.
It also exposes evidence-aware ``job_title`` and ``organization`` values,
``published_at``, ``deadline``, and ordered ``deadline_candidates``.

This W2 contract deliberately preserves source language and relationships.  It
does not require a Requirement AST, Skill normalization, or eligibility
decisions; those remain W3 responsibilities.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import epick_engine.source_collection.parsing as parsing_module
from epick_engine.source_collection.collector import StaticResponseCandidate
from epick_engine.source_collection.contracts import (
    DatePrecision,
    DateStatus,
    ExtractionStatus,
    LocatorKind,
    PostingSectionKind,
)
from epick_engine.source_collection.parsing import (
    EvidenceDraft,
    StaticParseResult,
    extract_static_candidate,
)
from epick_engine.source_collection.policy import (
    Representation,
    UntrustedDocument,
    ValidatedTarget,
)

_FIXTURES_PATH = Path(__file__).parents[2] / "fixtures" / "synthetic_sources"
_ANNOTATIONS_PATH = _FIXTURES_PATH / "annotated_postings.json"
_POSTING_PATH = _FIXTURES_PATH / "static_posting.html"
_TARGET = ValidatedTarget(
    url="https://synthetic-meridian-careers.test/jobs/static-posting",
    hostname="synthetic-meridian-careers.test",
    port=443,
    resolved_addresses=frozenset({"8.8.8.8"}),
)


def _candidate(document: str) -> StaticResponseCandidate:
    document_size = len(document.encode("utf-8"))
    return StaticResponseCandidate(
        final_target=_TARGET,
        representation=Representation.HTML,
        document=UntrustedDocument(document),
        http_status=200,
        raw_size=document_size,
        decompressed_size=document_size,
    )


def _annotations() -> dict[str, Any]:
    return json.loads(_ANNOTATIONS_PATH.read_text(encoding="utf-8"))


def _static_parse_result(document: str | None = None) -> StaticParseResult:
    parsed = extract_static_candidate(
        _candidate(document or _POSTING_PATH.read_text(encoding="utf-8"))
    )

    assert parsed.extraction_status is ExtractionStatus.COMPLETE
    return parsed


def _evidence_by_annotation_ref(
    parsed: StaticParseResult,
    annotations: dict[str, Any],
) -> dict[str, EvidenceDraft]:
    evidence_by_ref: dict[str, EvidenceDraft] = {}
    for expected in annotations["expected"]["evidence"]:
        matching_evidence = [
            evidence
            for evidence in parsed.evidence
            if evidence.text_excerpt == expected["text_excerpt"]
        ]

        assert len(matching_evidence) == 1
        evidence = matching_evidence[0]
        assert evidence.locator.kind is LocatorKind.XPATH
        assert evidence.text_excerpt == expected["text_excerpt"]
        assert evidence.section_title == expected["section_heading"]
        assert evidence.locator.value == expected["xpath"]
        assert evidence.chunk_order == expected["chunk_order"]
        evidence_by_ref[expected["ref"]] = evidence

    return evidence_by_ref


def _parse_static_posting(parsed: StaticParseResult) -> Any:
    return parsing_module.parse_static_posting(parsed)


def test_annotation_evidence_refs_are_exact_static_parse_inputs() -> None:
    annotations = _annotations()
    evidence_by_ref = _evidence_by_annotation_ref(_static_parse_result(), annotations)

    expected_refs = {item["ref"] for item in annotations["expected"]["evidence"]}

    assert set(evidence_by_ref) == expected_refs
    assert len(evidence_by_ref) == 15


def test_semantic_sections_match_annotations_and_bind_actual_evidence() -> None:
    annotations = _annotations()
    parsed = _static_parse_result()
    semantic = _parse_static_posting(parsed)
    evidence_by_ref = _evidence_by_annotation_ref(parsed, annotations)
    expected_sections = annotations["expected"]["posting_sections"]

    for expected, section in zip(expected_sections, semantic.sections, strict=True):
        assert section.kind is PostingSectionKind(expected["kind"])
        assert section.order == expected["order"]
        assert section.heading_raw == expected.get("heading_raw")
        assert section.text_raw == expected["text_raw"]
        assert tuple(section.evidence_keys) == tuple(
            evidence_by_ref[ref].evidence_key for ref in expected["evidence_refs"]
        )
        assert section.relation_text == expected.get("relation_text")


def test_semantic_section_keys_are_nonempty_unique_and_deterministic() -> None:
    parsed = _static_parse_result()
    first = _parse_static_posting(parsed)
    second = _parse_static_posting(parsed)
    first_keys = tuple(section.section_key for section in first.sections)

    assert all(first_keys)
    assert len(first_keys) == len(set(first_keys))
    assert first_keys == tuple(section.section_key for section in second.sections)
    assert all(key.startswith("posting_section:") for key in first_keys)


def test_requirement_classification_preserves_source_logic_without_ast() -> None:
    annotations = _annotations()
    semantic = _parse_static_posting(_static_parse_result())
    sections_by_id = {
        expected["section_id"]: section
        for expected, section in zip(
            annotations["expected"]["posting_sections"],
            semantic.sections,
            strict=True,
        )
    }
    requirements_by_id = {
        requirement["requirement_id"]: requirement
        for requirement in annotations["expected"]["requirements"]["items"]
    }
    relations_by_id = {
        relation["relation_id"]: relation
        for relation in annotations["expected"]["requirements"]["relations"]
    }

    aws = sections_by_id["aws_required"]
    gcp = sections_by_id["gcp_general_context"]
    python_and_sql = sections_by_id["python_and_sql_required"]
    kubernetes_or_docker = sections_by_id["kubernetes_or_docker_required"]
    same_experience = sections_by_id["same_experience_relation"]

    assert aws.kind is PostingSectionKind.REQUIRED
    assert aws.text_raw == requirements_by_id["aws_experience"]["text_raw"]
    assert gcp.kind is PostingSectionKind.GENERAL
    assert gcp.text_raw == requirements_by_id["gcp_cloud_platform_example"]["text_raw"]
    assert all(
        section.text_raw != gcp.text_raw or section.kind is not PostingSectionKind.REQUIRED
        for section in semantic.sections
    )
    assert python_and_sql.kind is PostingSectionKind.REQUIRED
    assert python_and_sql.relation_text == relations_by_id["python_and_sql"]["relation_text"]
    assert kubernetes_or_docker.kind is PostingSectionKind.REQUIRED
    assert (
        kubernetes_or_docker.relation_text
        == relations_by_id["kubernetes_or_docker"]["relation_text"]
    )
    assert same_experience.kind is PostingSectionKind.GENERAL
    assert (
        same_experience.relation_text
        == relations_by_id["same_experience_may_satisfy_aws_and_python_sql"]["relation_text"]
    )


def test_unknown_identity_and_dates_do_not_be_invented_from_ambiguous_source_text() -> None:
    annotations = _annotations()
    parsed = _static_parse_result()
    semantic = _parse_static_posting(parsed)
    evidence_by_ref = _evidence_by_annotation_ref(parsed, annotations)

    assert semantic.job_title.status == "unknown"
    assert semantic.job_title.value is None
    assert tuple(semantic.job_title.evidence_keys) == (
        evidence_by_ref["document_title"].evidence_key,
        evidence_by_ref["role_and_organization_status"].evidence_key,
    )
    assert semantic.organization.status == "unknown"
    assert semantic.organization.value is None
    assert tuple(semantic.organization.evidence_keys) == (
        evidence_by_ref["role_and_organization_status"].evidence_key,
    )
    assert all(
        section.kind not in {PostingSectionKind.ROLE, PostingSectionKind.ORGANIZATION}
        for section in semantic.sections
    )
    assert semantic.published_at.status is DateStatus.UNKNOWN
    assert semantic.published_at.raw_text == "The posting date is unknown."
    assert semantic.published_at.value is None
    assert semantic.published_at.precision is None
    assert semantic.published_at.timezone is None
    assert semantic.deadline.status is DateStatus.CONFLICTING
    assert semantic.deadline.value is None
    assert semantic.deadline.precision is None
    assert semantic.deadline.timezone is None
    assert [
        (
            candidate.value,
            candidate.raw_text,
            tuple(candidate.evidence_keys),
        )
        for candidate in semantic.deadline_candidates
    ] == [
        (
            "2030-02-01",
            "Applications close on 2030-02-01.",
            (evidence_by_ref["deadline_primary"].evidence_key,),
        ),
        (
            "2030-02-02",
            "A secondary synthetic notice says applications close on 2030-02-02.",
            (evidence_by_ref["deadline_secondary"].evidence_key,),
        ),
    ]


def test_numeric_requirement_preserves_value_unit_target_duration_and_comparison() -> None:
    requirement_text = (
        "Applicants must maintain at least 99.9% availability across 12 production services "
        "over a 6-month period, compared with the previous 6-month period."
    )
    document = f"""
    <html><body><main><section>
      <h2>Requirements</h2>
      <p>{requirement_text}</p>
    </section></main></body></html>
    """
    parsed = _static_parse_result(document)
    semantic = _parse_static_posting(parsed)
    requirement_evidence = next(
        evidence for evidence in parsed.evidence if evidence.text_excerpt == requirement_text
    )
    numeric_section = next(
        section for section in semantic.sections if section.text_raw == requirement_text
    )

    assert numeric_section.kind is PostingSectionKind.REQUIRED
    assert numeric_section.relation_text is None
    assert tuple(numeric_section.evidence_keys) == (requirement_evidence.evidence_key,)
    assert requirement_evidence.locator.kind is LocatorKind.XPATH
    assert requirement_evidence.text_excerpt == requirement_text
    assert "99.9%" in numeric_section.text_raw
    assert "12 production services" in numeric_section.text_raw
    assert "over a 6-month period" in numeric_section.text_raw
    assert "compared with the previous 6-month period" in numeric_section.text_raw


def test_duties_heading_takes_precedence_over_requirement_lexicon() -> None:
    responsibility_text = "You must own the incident-response rotation."
    document = f"""
    <html><body><main><section>
      <h2>Responsibilities</h2>
      <p>{responsibility_text}</p>
    </section></main></body></html>
    """

    semantic = _parse_static_posting(_static_parse_result(document))
    responsibility_section = next(
        section for section in semantic.sections if section.text_raw == responsibility_text
    )

    assert responsibility_section.kind is PostingSectionKind.DUTIES


def test_explicit_identity_headings_bind_known_values() -> None:
    job_title = "Senior Platform Engineer"
    organization = "Meridian Systems"
    document = f"""
    <html><body><main>
      <section><h2>Job title</h2><p>{job_title}</p></section>
      <section><h2>Organization</h2><p>{organization}</p></section>
    </main></body></html>
    """
    parsed = _static_parse_result(document)
    semantic = _parse_static_posting(parsed)
    title_heading_evidence = next(
        evidence for evidence in parsed.evidence if evidence.text_excerpt == "Job title"
    )
    title_value_evidence = next(
        evidence for evidence in parsed.evidence if evidence.text_excerpt == job_title
    )
    organization_heading_evidence = next(
        evidence for evidence in parsed.evidence if evidence.text_excerpt == "Organization"
    )
    organization_value_evidence = next(
        evidence for evidence in parsed.evidence if evidence.text_excerpt == organization
    )

    assert semantic.job_title.status == "known"
    assert semantic.job_title.value == job_title
    assert tuple(semantic.job_title.evidence_keys) == (
        title_heading_evidence.evidence_key,
        title_value_evidence.evidence_key,
    )
    assert semantic.organization.status == "known"
    assert semantic.organization.value == organization
    assert tuple(semantic.organization.evidence_keys) == (
        organization_heading_evidence.evidence_key,
        organization_value_evidence.evidence_key,
    )


def test_exact_role_and_company_headings_bind_known_values() -> None:
    job_title = "Data Engineer"
    organization = "Meridian Systems"
    document = f"""
    <html><body><main>
      <section><h2>Role</h2><p>{job_title}</p></section>
      <section><h2>Company</h2><p>{organization}</p></section>
    </main></body></html>
    """

    semantic = _parse_static_posting(_static_parse_result(document))

    assert semantic.job_title.status == "known"
    assert semantic.job_title.value == job_title
    assert semantic.organization.status == "known"
    assert semantic.organization.value == organization


def test_iso_dates_under_explicit_headings_are_semantic_dates() -> None:
    published_date = "2030-01-15"
    deadline_date = "2030-02-15"
    document = f"""
    <html><body><main>
      <section><h2>Published</h2><p>{published_date}</p></section>
      <section><h2>Deadline</h2><p>{deadline_date}</p></section>
    </main></body></html>
    """
    parsed = _static_parse_result(document)
    semantic = _parse_static_posting(parsed)
    published_section = next(
        section for section in semantic.sections if section.text_raw == published_date
    )
    deadline_section = next(
        section for section in semantic.sections if section.text_raw == deadline_date
    )
    deadline_evidence = next(
        evidence for evidence in parsed.evidence if evidence.text_excerpt == deadline_date
    )

    assert published_section.kind is PostingSectionKind.PUBLISHED
    assert semantic.published_at.status is DateStatus.KNOWN
    assert semantic.published_at.raw_text == published_date
    assert semantic.published_at.value == published_date
    assert semantic.published_at.precision is DatePrecision.DATE
    assert semantic.published_at.timezone is None
    assert deadline_section.kind is PostingSectionKind.DEADLINE
    assert semantic.deadline.status is DateStatus.KNOWN
    assert semantic.deadline.raw_text == deadline_date
    assert semantic.deadline.value == deadline_date
    assert semantic.deadline.precision is DatePrecision.DATE
    assert semantic.deadline.timezone is None
    assert [
        (candidate.value, candidate.raw_text, tuple(candidate.evidence_keys))
        for candidate in semantic.deadline_candidates
    ] == [(deadline_date, deadline_date, (deadline_evidence.evidence_key,))]


def test_conflicting_published_dates_fail_closed() -> None:
    document = """
    <html><body><main><section>
      <h2>Published</h2>
      <p>2030-01-15</p>
      <p>2030-01-16</p>
    </section></main></body></html>
    """

    semantic = _parse_static_posting(_static_parse_result(document))

    assert semantic.published_at.status is DateStatus.CONFLICTING
    assert semantic.published_at.value is None
    assert semantic.published_at.precision is None
    assert semantic.published_at.timezone is None


def test_required_and_relation_is_preserved_when_modal_follows_terms() -> None:
    requirement_text = "AWS and GCP experience is required."
    document = f"""
    <html><body><main><section>
      <h2>Requirements</h2>
      <p>{requirement_text}</p>
    </section></main></body></html>
    """

    semantic = _parse_static_posting(_static_parse_result(document))
    requirement_section = next(
        section for section in semantic.sections if section.text_raw == requirement_text
    )

    assert requirement_section.kind is PostingSectionKind.REQUIRED
    assert requirement_section.relation_text == requirement_text


def test_required_or_relation_is_preserved_when_modal_follows_terms() -> None:
    requirement_text = "Python or SQL proficiency is mandatory."
    document = f"""
    <html><body><main><section>
      <h2>Requirements</h2>
      <p>{requirement_text}</p>
    </section></main></body></html>
    """

    semantic = _parse_static_posting(_static_parse_result(document))
    requirement_section = next(
        section for section in semantic.sections if section.text_raw == requirement_text
    )

    assert requirement_section.kind is PostingSectionKind.REQUIRED
    assert requirement_section.relation_text == requirement_text


def test_calendar_invalid_iso_looking_dates_are_not_known() -> None:
    document = """
    <html><body><main>
      <section><h2>Published</h2><p>2030-99-99</p></section>
      <section><h2>Deadline</h2><p>2030-02-30</p></section>
    </main></body></html>
    """

    semantic = _parse_static_posting(_static_parse_result(document))

    assert semantic.published_at.status is not DateStatus.KNOWN
    assert semantic.deadline.status is not DateStatus.KNOWN
    assert semantic.deadline_candidates == ()


def test_descriptive_role_and_company_headings_remain_general_and_unknown() -> None:
    document = """
    <html><body><main>
      <section><h2>Role overview</h2><p>Build reliable platform services.</p></section>
      <section><h2>Company benefits</h2><p>Comprehensive health coverage.</p></section>
    </main></body></html>
    """

    semantic = _parse_static_posting(_static_parse_result(document))
    sections_by_text = {section.text_raw: section for section in semantic.sections}

    assert sections_by_text["Build reliable platform services."].kind is PostingSectionKind.GENERAL
    assert sections_by_text["Comprehensive health coverage."].kind is PostingSectionKind.GENERAL
    assert semantic.job_title.status == "unknown"
    assert semantic.job_title.value is None
    assert semantic.organization.status == "unknown"
    assert semantic.organization.value is None
