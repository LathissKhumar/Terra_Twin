"""Persist discovery job lifecycle state.

Revision ID: 0002_discovery_jobs
Revises: 0001_initial_postgis_setup
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_discovery_jobs"
down_revision: str | None = "0001_initial_postgis_setup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovery_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("result_run_id", sa.String(length=20), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discovery_jobs_status", "discovery_jobs", ["status"])
    op.create_index(
        "ix_discovery_jobs_request_fingerprint",
        "discovery_jobs",
        ["request_fingerprint"],
    )
    op.create_index(
        "uq_discovery_jobs_active_fingerprint",
        "discovery_jobs",
        ["request_fingerprint"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_discovery_jobs_active_fingerprint", table_name="discovery_jobs")
    op.drop_index("ix_discovery_jobs_request_fingerprint", table_name="discovery_jobs")
    op.drop_index("ix_discovery_jobs_status", table_name="discovery_jobs")
    op.drop_table("discovery_jobs")
