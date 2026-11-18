"""Initial ParkTwin schema with observations index, optimistic concurrency, idempotency, and audit trail.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_metadata",
        sa.Column("model_version", sa.String(length=64), primary_key=True),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("assumptions_version", sa.String(length=64), nullable=False),
        sa.Column("adapter_type", sa.String(length=32), nullable=False),
        sa.Column("artifact_checksum", sa.String(length=128), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "twins",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("external_reference", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="insufficient_data"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("latest_state_id", sa.String(length=36), nullable=True),
        sa.Column("data_quality_summary", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_twins_external_reference", "twins", ["external_reference"])
    op.create_index("ix_twins_owner_id", "twins", ["owner_id"])

    op.create_table(
        "observations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("twin_id", sa.String(length=36), sa.ForeignKey("twins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("is_partial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("observed_total_updrs", sa.Float(), nullable=True),
        sa.Column("observed_motor_updrs", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="api"),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("twin_id", "observed_at", name="uq_observations_twin_timestamp"),
    )
    op.create_index("ix_observations_twin_observed_at", "observations", ["twin_id", "observed_at"])

    op.create_table(
        "state_estimates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("twin_id", sa.String(length=36), sa.ForeignKey("twins.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "observation_id",
            sa.String(length=36),
            sa.ForeignKey("observations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("estimated_total_updrs", sa.Float(), nullable=True),
        sa.Column("estimated_motor_updrs", sa.Float(), nullable=True),
        sa.Column("total_updrs_ci_low", sa.Float(), nullable=True),
        sa.Column("total_updrs_ci_high", sa.Float(), nullable=True),
        sa.Column("motor_updrs_ci_low", sa.Float(), nullable=True),
        sa.Column("motor_updrs_ci_high", sa.Float(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_state_estimates_twin_created", "state_estimates", ["twin_id", "created_at"])

    op.create_table(
        "simulation_scenarios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("twin_id", sa.String(length=36), sa.ForeignKey("twins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("step_days", sa.Integer(), nullable=False),
        sa.Column("assumptions_version", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("baseline_twin_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("hypothetical", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("baseline_series", sa.JSON(), nullable=False),
        sa.Column("scenario_series", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulation_scenarios_twin_created", "simulation_scenarios", ["twin_id", "created_at"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_resource", "audit_events", ["resource_type", "resource_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_resource", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_table("idempotency_records")

    op.drop_index("ix_simulation_scenarios_twin_created", table_name="simulation_scenarios")
    op.drop_table("simulation_scenarios")

    op.drop_index("ix_state_estimates_twin_created", table_name="state_estimates")
    op.drop_table("state_estimates")

    op.drop_index("ix_observations_twin_observed_at", table_name="observations")
    op.drop_table("observations")

    op.drop_index("ix_twins_owner_id", table_name="twins")
    op.drop_index("ix_twins_external_reference", table_name="twins")
    op.drop_table("twins")

    op.drop_table("model_metadata")
