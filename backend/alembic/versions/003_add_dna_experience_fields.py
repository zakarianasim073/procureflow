"""add_dna_experience_fields

Add completion/on-time/delay fields to contractor_dna
and procurement_tender_id to econtract_execution.

Revision ID: 003
Revises: 002
Create Date: 2026-06-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contractor_dna", sa.Column("completion_rate", sa.Float(), nullable=False, server_default="0"))
    op.add_column("contractor_dna", sa.Column("on_time_rate", sa.Float(), nullable=False, server_default="0"))
    op.add_column("contractor_dna", sa.Column("avg_delay_days", sa.Float(), nullable=False, server_default="0"))
    op.add_column("contractor_dna", sa.Column("total_experience_contracts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("contractor_dna", sa.Column("total_experience_value_bdt", sa.Float(), nullable=False, server_default="0"))
    op.add_column("econtract_execution", sa.Column("procurement_tender_id", sa.String(36), nullable=True, index=True))


def downgrade() -> None:
    op.drop_column("contractor_dna", "completion_rate")
    op.drop_column("contractor_dna", "on_time_rate")
    op.drop_column("contractor_dna", "avg_delay_days")
    op.drop_column("contractor_dna", "total_experience_contracts")
    op.drop_column("contractor_dna", "total_experience_value_bdt")
    op.drop_column("econtract_execution", "procurement_tender_id")
