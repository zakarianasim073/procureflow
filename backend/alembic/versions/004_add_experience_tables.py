"""add_experience_tables

Create eexperience_completed and ecms_ongoing tables.

Revision ID: 004
Revises: 003
Create Date: 2026-06-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eexperience_completed",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tender_id", sa.String(50), nullable=True, index=True),
        sa.Column("package_no", sa.String(300), nullable=False, index=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("pe_office", sa.String(300), nullable=True),
        sa.Column("agency_code", sa.String(20), nullable=True, index=True),
        sa.Column("procurement_method", sa.String(100), nullable=True),
        sa.Column("contractor_name", sa.String(300), nullable=True, index=True),
        sa.Column("company_unique_id", sa.String(50), nullable=True),
        sa.Column("experience_certificate_no", sa.String(200), nullable=True),
        sa.Column("contract_value_bdt", sa.Float(), nullable=False, server_default="0"),
        sa.Column("completed_value_bdt", sa.Float(), nullable=False, server_default="0"),
        sa.Column("contract_start_date", sa.String(20), nullable=True),
        sa.Column("contract_end_date", sa.String(20), nullable=True),
        sa.Column("planned_completion_date", sa.String(20), nullable=True),
        sa.Column("actual_completion_date", sa.String(20), nullable=True),
        sa.Column("published_date", sa.String(20), nullable=True),
        sa.Column("award_date", sa.String(20), nullable=True),
        sa.Column("completion_status", sa.String(50), nullable=True),
        sa.Column("work_status", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("completed_on_time", sa.Boolean(), nullable=True),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("procurement_tender_id", sa.String(36), nullable=True, index=True),
        sa.Column("data_source", sa.String(50), nullable=False, server_default="EEXPERIENCE_ALL"),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "ecms_ongoing",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tender_id", sa.String(50), nullable=True, index=True),
        sa.Column("package_no", sa.String(300), nullable=False, index=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("pe_office", sa.String(300), nullable=True),
        sa.Column("agency_code", sa.String(20), nullable=True, index=True),
        sa.Column("procurement_method", sa.String(100), nullable=True),
        sa.Column("contractor_name", sa.String(300), nullable=True, index=True),
        sa.Column("company_unique_id", sa.String(50), nullable=True),
        sa.Column("experience_certificate_no", sa.String(200), nullable=True),
        sa.Column("contract_value_bdt", sa.Float(), nullable=False, server_default="0"),
        sa.Column("completed_value_bdt", sa.Float(), nullable=False, server_default="0"),
        sa.Column("contract_start_date", sa.String(20), nullable=True),
        sa.Column("contract_end_date", sa.String(20), nullable=True),
        sa.Column("planned_completion_date", sa.String(20), nullable=True),
        sa.Column("actual_completion_date", sa.String(20), nullable=True),
        sa.Column("published_date", sa.String(20), nullable=True),
        sa.Column("award_date", sa.String(20), nullable=True),
        sa.Column("completion_status", sa.String(50), nullable=True),
        sa.Column("work_status", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("completed_on_time", sa.Boolean(), nullable=True),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("procurement_tender_id", sa.String(36), nullable=True, index=True),
        sa.Column("data_source", sa.String(50), nullable=False, server_default="ECMS_ONGOING"),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ecms_ongoing")
    op.drop_table("eexperience_completed")
