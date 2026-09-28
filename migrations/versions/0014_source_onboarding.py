"""Add versioned Source onboarding approval and private ACK storage.

Revision ID: 0014_source_onboarding
Revises: 0013_deletion_ack_confirmed
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_source_onboarding"
down_revision: str | None = "0013_deletion_ack_confirmed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_approval_rule_heads",
        sa.Column("approval_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "current_revision > 0",
            name=op.f("ck_source_approval_rule_heads_positive_current_revision"),
        ),
        sa.PrimaryKeyConstraint("approval_rule_id", name=op.f("pk_source_approval_rule_heads")),
    )
    op.create_table(
        "source_approval_rule_revisions",
        sa.Column("approval_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_official_domain", sa.Text(), nullable=False),
        sa.Column("company_legal_identifiers", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("company_identity_evidence_refs", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("exact_host", sa.Text(), nullable=False),
        sa.Column("path_mode", sa.String(length=32), nullable=False),
        sa.Column("path_value", sa.Text(), nullable=False),
        sa.Column("allowed_query_strings", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("official_status", sa.String(length=32), nullable=False),
        sa.Column("access_class", sa.String(length=32), nullable=False),
        sa.Column("collection_permission", sa.String(length=16), nullable=False),
        sa.Column("excerpt_storage_permission", sa.String(length=16), nullable=False),
        sa.Column("body_storage_permission", sa.String(length=16), nullable=False),
        sa.Column("redistribution_permission", sa.String(length=16), nullable=False),
        sa.Column("evidence_refs", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("robots_permission", sa.String(length=16), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("redirect_robots_permissions", postgresql.JSONB(), nullable=False),
        sa.Column("limits", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision > 0", name=op.f("ck_source_approval_rule_revisions_positive_revision")
        ),
        sa.CheckConstraint(
            "path_mode IN ('EXACT', 'SEGMENT_PREFIX')",
            name=op.f("ck_source_approval_rule_revisions_valid_path_mode"),
        ),
        sa.CheckConstraint(
            "length(exact_host) > 0",
            name=op.f("ck_source_approval_rule_revisions_nonempty_exact_host"),
        ),
        sa.CheckConstraint(
            "left(path_value, 1) = '/'",
            name=op.f("ck_source_approval_rule_revisions_absolute_path_value"),
        ),
        sa.CheckConstraint(
            "result_version > 0",
            name=op.f("ck_source_approval_rule_revisions_positive_result_version"),
        ),
        sa.CheckConstraint(
            "official_status IN ('verified', 'unverified', 'rejected')",
            name=op.f("ck_source_approval_rule_revisions_valid_official_status"),
        ),
        sa.CheckConstraint(
            "access_class IN ('public', 'restricted', 'unavailable', 'unknown')",
            name=op.f("ck_source_approval_rule_revisions_valid_access_class"),
        ),
        sa.CheckConstraint(
            "collection_permission IN ('allowed', 'denied', 'unknown')",
            name=op.f("ck_source_approval_rule_revisions_valid_collection_permission"),
        ),
        sa.CheckConstraint(
            "excerpt_storage_permission IN ('allowed', 'denied', 'unknown')",
            name=op.f("ck_source_approval_rule_revisions_valid_excerpt_storage_permission"),
        ),
        sa.CheckConstraint(
            "body_storage_permission IN ('allowed', 'denied', 'unknown')",
            name=op.f("ck_source_approval_rule_revisions_valid_body_storage_permission"),
        ),
        sa.CheckConstraint(
            "redistribution_permission IN ('allowed', 'denied', 'unknown')",
            name=op.f("ck_source_approval_rule_revisions_valid_redistribution_permission"),
        ),
        sa.CheckConstraint(
            "robots_permission IN ('allowed', 'denied', 'unknown')",
            name=op.f("ck_source_approval_rule_revisions_valid_robots_permission"),
        ),
        sa.ForeignKeyConstraint(
            ["approval_rule_id"],
            ["source_approval_rule_heads.approval_rule_id"],
            name="fk_source_approval_rule_revisions_head",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint(
            "approval_rule_id", "revision", name=op.f("pk_source_approval_rule_revisions")
        ),
    )
    op.create_index(
        "ix_source_approval_rule_revisions_match_scope",
        "source_approval_rule_revisions",
        ["company_id", "source_type", "exact_host"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_source_approval_rule_heads_current_revision",
        "source_approval_rule_heads",
        "source_approval_rule_revisions",
        ["approval_rule_id", "current_revision"],
        ["approval_rule_id", "revision"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.execute(
        """
        CREATE FUNCTION epick_deny_source_approval_rule_revision_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'source approval rule revisions are immutable'
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER source_approval_rule_revisions_immutable
        BEFORE UPDATE OR DELETE ON source_approval_rule_revisions
        FOR EACH ROW
        EXECUTE FUNCTION epick_deny_source_approval_rule_revision_mutation()
        """
    )

    op.create_table(
        "source_runtime_approvals",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_rule_revision", sa.Integer(), nullable=False),
        sa.Column("policy_revision", sa.Integer(), nullable=False),
        sa.Column("robots_permission", sa.String(length=16), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("redirect_robots_permissions", postgresql.JSONB(), nullable=False),
        sa.Column("limits", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "policy_revision > 0", name=op.f("ck_source_runtime_approvals_positive_policy_revision")
        ),
        sa.CheckConstraint(
            "result_version > 0", name=op.f("ck_source_runtime_approvals_positive_result_version")
        ),
        sa.CheckConstraint(
            "robots_permission IN ('allowed', 'denied', 'unknown')",
            name=op.f("ck_source_runtime_approvals_valid_robots_permission"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.source_id"], name="fk_source_runtime_approvals_source_id"
        ),
        sa.ForeignKeyConstraint(
            ["source_id", "policy_revision"],
            ["source_policy_decisions.source_id", "source_policy_decisions.revision"],
            name="fk_source_runtime_approvals_policy_revision",
        ),
        sa.ForeignKeyConstraint(
            ["approval_rule_id", "approval_rule_revision"],
            [
                "source_approval_rule_revisions.approval_rule_id",
                "source_approval_rule_revisions.revision",
            ],
            name="fk_source_runtime_approvals_rule_revision",
        ),
        sa.PrimaryKeyConstraint("source_id", name=op.f("pk_source_runtime_approvals")),
    )

    op.create_table(
        "source_registration_receipts",
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authenticated_owner_ref", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_ref", sa.Text(), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_fence", sa.BigInteger(), nullable=False),
        sa.Column("owner_deletion_epoch", sa.BigInteger(), nullable=False),
        sa.Column("registration_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("policy_revision", sa.Integer(), nullable=True),
        sa.Column("approval_rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_rule_revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "execution_fence > 0",
            name=op.f("ck_source_registration_receipts_positive_execution_fence"),
        ),
        sa.CheckConstraint(
            "owner_deletion_epoch >= 0",
            name=op.f("ck_source_registration_receipts_nonnegative_owner_deletion_epoch"),
        ),
        sa.CheckConstraint(
            "registration_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_source_registration_receipts_registration_digest_format"),
        ),
        sa.CheckConstraint(
            "status IN ('READY', 'HELD', 'REJECTED')",
            name=op.f("ck_source_registration_receipts_valid_status"),
        ),
        sa.CheckConstraint(
            "(status = 'READY' AND reason_code = 'APPROVED' "
            "AND policy_revision IS NOT NULL AND approval_rule_id IS NOT NULL "
            "AND approval_rule_revision IS NOT NULL) OR "
            "(status = 'HELD' AND reason_code IN "
            "('POLICY_RULE_MISSING', 'COMPANY_UNVERIFIED', "
            "'URL_NORMALIZATION_MISMATCH', 'UNSUPPORTED_SOURCE_TYPE') "
            "AND policy_revision IS NULL AND approval_rule_id IS NULL "
            "AND approval_rule_revision IS NULL) OR "
            "(status = 'REJECTED' AND reason_code IN "
            "('SOURCE_ID_CONFLICT', 'CANONICAL_URL_CONFLICT', "
            "'EXPLICIT_POLICY_DENIAL') AND policy_revision IS NULL "
            "AND approval_rule_id IS NULL AND approval_rule_revision IS NULL)",
            name=op.f("ck_source_registration_receipts_valid_result_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["authenticated_owner_ref"],
            ["private_deletion_owner_states.owner_user_id"],
            name="fk_source_registration_receipts_owner_state",
        ),
        sa.ForeignKeyConstraint(
            ["source_id", "policy_revision"],
            ["source_policy_decisions.source_id", "source_policy_decisions.revision"],
            name="fk_source_registration_receipts_policy_revision",
        ),
        sa.ForeignKeyConstraint(
            ["approval_rule_id", "approval_rule_revision"],
            [
                "source_approval_rule_revisions.approval_rule_id",
                "source_approval_rule_revisions.revision",
            ],
            name="fk_source_registration_receipts_rule_revision",
        ),
        sa.PrimaryKeyConstraint("command_id", name=op.f("pk_source_registration_receipts")),
    )
    op.create_index(
        "ix_source_registration_receipts_owner_project",
        "source_registration_receipts",
        ["authenticated_owner_ref", "project_ref"],
        unique=False,
    )

    op.create_table(
        "source_registration_ack_outbox",
        sa.Column("ack_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("delivery_state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ack_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "delivery_state IN ('PENDING', 'DELIVERED')",
            name=op.f("ck_source_registration_ack_outbox_valid_delivery_state"),
        ),
        sa.ForeignKeyConstraint(
            ["command_id"],
            ["source_registration_receipts.command_id"],
            name="fk_source_registration_ack_outbox_command_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ack_message_id", name=op.f("pk_source_registration_ack_outbox")),
        sa.UniqueConstraint("command_id", name="uq_source_registration_ack_outbox_command_id"),
    )
    op.create_index(
        "ix_source_registration_ack_outbox_delivery_created",
        "source_registration_ack_outbox",
        ["delivery_state", "created_at", "ack_message_id"],
        unique=False,
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade is intentionally unsupported; use a forward corrective migration."
    )
