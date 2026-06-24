"""initial_migration

Revision ID: 001
Revises:
Create Date: 2026-06-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Users ---
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("plan", sa.Enum("free", "pro", "enterprise", name="user_plan"), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("gpt_quota_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gpt_quota_limit", sa.Integer(), nullable=False, server_default="50000"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # --- Tenders ---
    op.create_table(
        "tenders",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("tender_id", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("procuring_entity", sa.String(255), nullable=True),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("division", sa.String(100), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("tender_security", sa.Float(), nullable=True),
        sa.Column("closing_date", sa.DateTime(), nullable=True),
        sa.Column("opening_date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("sor_agency", sa.String(20), nullable=False, server_default="BWDB"),
        sa.Column("zone", sa.String(10), nullable=True),
        sa.Column("extracted_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("comparison_results", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tenders_owner_status", "tenders", ["owner_id", "status"])

    # --- Tender Documents ---
    op.create_table(
        "tender_documents",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tender_id", sa.String(36), sa.ForeignKey("tenders.id"), nullable=False, index=True),
        sa.Column("doc_type", sa.String(20), nullable=False, index=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tender_docs_tender_type", "tender_documents", ["tender_id", "doc_type"])

    # --- BOQ Items ---
    op.create_table(
        "boq_items",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tender_id", sa.String(36), sa.ForeignKey("tenders.id"), nullable=False, index=True),
        sa.Column("item_no", sa.String(50), nullable=True),
        sa.Column("code", sa.String(100), nullable=True, index=True),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("quoted_rate", sa.Float(), nullable=True),
        sa.Column("sor_rate", sa.Float(), nullable=True),
        sa.Column("sor_code", sa.String(100), nullable=True),
        sa.Column("diff", sa.Float(), nullable=True),
        sa.Column("pct_diff", sa.Float(), nullable=True),
        sa.Column("flag", sa.String(50), nullable=True, index=True),
        sa.Column("work_type", sa.String(100), nullable=True),
        sa.Column("section", sa.String(100), nullable=True),
        sa.Column("agency", sa.String(20), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_boq_items_tender_flag", "boq_items", ["tender_id", "flag"])

    # --- BOQ Comparisons ---
    op.create_table(
        "boq_comparisons",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("tender_id", sa.String(36), sa.ForeignKey("tenders.id"), nullable=True, index=True),
        sa.Column("boq_file_id", sa.String(100), nullable=False),
        sa.Column("sor_agency", sa.String(20), nullable=False, server_default="BWDB"),
        sa.Column("zone", sa.String(10), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("variances", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mismatches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("below_sor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_sor_amount", sa.Float(), nullable=True),
        sa.Column("total_quoted_amount", sa.Float(), nullable=True),
        sa.Column("discount_pct", sa.Float(), nullable=True),
        sa.Column("summary_by_work_type", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("excel_path", sa.String(500), nullable=True),
        sa.Column("docx_path", sa.String(500), nullable=True),
        sa.Column("tenderai_dir", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # --- Award Records ---
    op.create_table(
        "award_records",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="egp", index=True),
        sa.Column("source_id", sa.String(100), nullable=False, index=True),
        sa.Column("tender_id", sa.String(100), nullable=True, index=True),
        sa.Column("award_date", sa.DateTime(), nullable=True),
        sa.Column("award_notice_no", sa.String(100), nullable=True),
        sa.Column("procuring_entity", sa.String(255), nullable=False, index=True),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("ministry", sa.String(255), nullable=True),
        sa.Column("work_name", sa.String(500), nullable=False),
        sa.Column("work_type", sa.String(100), nullable=True),
        sa.Column("district", sa.String(100), nullable=True, index=True),
        sa.Column("division", sa.String(100), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("awarded_amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="BDT"),
        sa.Column("contractor_name", sa.String(255), nullable=False, index=True),
        sa.Column("contractor_license", sa.String(100), nullable=True),
        sa.Column("contractor_address", sa.String(500), nullable=True),
        sa.Column("contract_period_days", sa.Integer(), nullable=True),
        sa.Column("work_start_date", sa.DateTime(), nullable=True),
        sa.Column("work_completion_date", sa.DateTime(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("boq_items", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("discount_pct", sa.Float(), nullable=True, index=True),
        sa.Column("unit_rates", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_award_entity_date", "award_records", ["procuring_entity", "award_date"])
    op.create_index("ix_award_contractor_date", "award_records", ["contractor_name", "award_date"])
    op.create_index("ix_award_district_type", "award_records", ["district", "work_type"])

    # --- Competitor Profiles ---
    op.create_table(
        "competitor_profiles",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("normalized_name", sa.String(255), nullable=False, index=True),
        sa.Column("license_number", sa.String(100), nullable=True, index=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("district", sa.String(100), nullable=True, index=True),
        sa.Column("division", sa.String(100), nullable=True),
        sa.Column("contact_person", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("specializations", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("total_awards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_awarded_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_discount_pct", sa.Float(), nullable=True),
        sa.Column("avg_project_size", sa.Float(), nullable=True),
        sa.Column("first_award_date", sa.DateTime(), nullable=True),
        sa.Column("last_award_date", sa.DateTime(), nullable=True),
        sa.Column("active_districts", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("work_types", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("predicted_win_probability", sa.Float(), nullable=True),
        sa.Column("predicted_price_range", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_competitor_district_category", "competitor_profiles", ["district", "category"])
    op.create_index("ix_competitor_active_amount", "competitor_profiles", ["last_award_date", "total_awarded_amount"])

    # --- Competitor Awards (link table) ---
    op.create_table(
        "competitor_awards",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("competitor_id", sa.String(36), sa.ForeignKey("competitor_profiles.id"), nullable=False, index=True),
        sa.Column("award_id", sa.String(36), sa.ForeignKey("award_records.id"), nullable=False, index=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="prime"),
        sa.Column("is_jv", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("jv_partners", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("bid_amount", sa.Float(), nullable=True),
        sa.Column("share_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_competitor_award_unique", "competitor_awards", ["competitor_id", "award_id"], unique=True)


def downgrade() -> None:
    op.drop_table("competitor_awards")
    op.drop_table("competitor_profiles")
    op.drop_table("award_records")
    op.drop_table("boq_comparisons")
    op.drop_table("boq_items")
    op.drop_table("tender_documents")
    op.drop_table("tenders")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_plan")
