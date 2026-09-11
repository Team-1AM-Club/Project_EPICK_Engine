from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from epick_engine.source_collection.persistence import Base, PostingSection

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config() -> Config:
    return Config(PROJECT_ROOT / "alembic.ini")


def test_alembic_uses_the_project_migration_directory_without_a_stored_url() -> None:
    config = _alembic_config()

    assert Path(config.get_main_option("script_location")) == PROJECT_ROOT / "migrations"
    assert not config.get_main_option("sqlalchemy.url")


def test_source_collection_migration_is_the_only_head() -> None:
    scripts = ScriptDirectory.from_config(_alembic_config())

    assert scripts.get_heads() == ["0003_source_retention_origin"]
    assert scripts.get_revision("0003_source_retention_origin").down_revision == "0002_job_posting"


def test_job_posting_metadata_matches_the_normalized_migration_boundary() -> None:
    job_postings = Base.metadata.tables["job_postings"]
    posting_sections = Base.metadata.tables["posting_sections"]
    section_evidence = Base.metadata.tables["posting_section_evidence"]

    assert list(job_postings.columns) == [
        job_postings.c.job_posting_id,
        job_postings.c.company_id,
        job_postings.c.source_id,
    ]
    assert posting_sections.c.section_key.type.__class__.__name__ == "Text"
    assert PostingSection.order.property.columns[0].name == "section_order"
    assert {constraint.name for constraint in posting_sections.constraints} == {
        "pk_posting_sections",
        "fk_posting_sections_extraction_revision_id",
        "uq_posting_sections_revision_order",
        "ck_posting_sections_nonempty_section_key",
        "ck_posting_sections_valid_kind",
        "ck_posting_sections_nonempty_heading_raw",
        "ck_posting_sections_nonempty_text_raw",
        "ck_posting_sections_nonnegative_section_order",
        "ck_posting_sections_nonempty_relation_text",
    }
    assert {constraint.name for constraint in section_evidence.constraints} == {
        "pk_posting_section_evidence",
        "fk_posting_section_evidence_section",
        "fk_posting_section_evidence_revision_evidence",
        "uq_posting_section_evidence_section_order",
        "ck_posting_section_evidence_nonnegative_evidence_order",
    }
    assert not job_postings.indexes
    assert not posting_sections.indexes
    assert not section_evidence.indexes


def test_job_posting_migration_downgrade_is_unsupported() -> None:
    scripts = ScriptDirectory.from_config(_alembic_config())

    with pytest.raises(RuntimeError, match="Destructive downgrade"):
        scripts.get_revision("0002_job_posting").module.downgrade()


def test_retention_origin_migration_downgrade_is_unsupported() -> None:
    scripts = ScriptDirectory.from_config(_alembic_config())

    with pytest.raises(RuntimeError, match="Destructive downgrade"):
        scripts.get_revision("0003_source_retention_origin").module.downgrade()
