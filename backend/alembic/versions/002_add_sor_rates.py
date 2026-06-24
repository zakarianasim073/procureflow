"""add_sor_rates

Revision ID: 002
Revises: 001
Create Date: 2026-06-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sor_rates",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("agency", sa.Enum("BWDB", "PWD", "LGED", "RHD", "CUSTOM", name="soragency"), nullable=False, index=True),
        sa.Column("code", sa.String(100), nullable=False, index=True),
        sa.Column("normalized_code", sa.String(100), nullable=False, index=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("zone_a", sa.Float(), nullable=False, server_default="0"),
        sa.Column("zone_b", sa.Float(), nullable=False, server_default="0"),
        sa.Column("zone_c", sa.Float(), nullable=False, server_default="0"),
        sa.Column("zone_d", sa.Float(), nullable=False, server_default="0"),
        sa.Column("edition_year", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("source_file", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sor_agency_code", "sor_rates", ["agency", "code"])
    op.create_index("ix_sor_normalized", "sor_rates", ["agency", "normalized_code"])
    op.create_index("ix_sor_active", "sor_rates", ["agency", "is_active"])


def downgrade() -> None:
    op.drop_table("sor_rates")
    op.execute("DROP TYPE IF EXISTS soragency")
