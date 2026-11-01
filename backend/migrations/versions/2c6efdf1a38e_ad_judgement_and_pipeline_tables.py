"""ad judgement and pipeline tables

Revision ID: 2c6efdf1a38e
Revises: 5a1ca17b06eb
Create Date: 2026-11-01 18:51:34.645086

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c6efdf1a38e'
down_revision: Union[str, Sequence[str], None] = '5a1ca17b06eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TABLES = ("round", "pipeline_run", "ad_judgement", "llm_call_log")


def upgrade() -> None:
    op.create_table(
        "round",
        sa.Column("round_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("round_id"),
    )
    op.create_table(
        "pipeline_run",
        sa.Column("run_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.Integer(), nullable=True),
        sa.Column("step", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("counters", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed')",
            name="ck_pipeline_run_status",
        ),
        sa.ForeignKeyConstraint(["round_id"], ["round.round_id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "ad_judgement",
        sa.Column("judgement_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ad_probability", sa.Float(), nullable=True),
        sa.Column("ad_weight", sa.Float(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("judged_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('ok', 'failed', 'skipped')", name="ck_ad_judgement_status"),
        sa.CheckConstraint(
            "ad_probability IS NULL OR (ad_probability >= 0 AND ad_probability <= 1)",
            name="ck_ad_judgement_probability",
        ),
        sa.CheckConstraint(
            "(status = 'ok' AND ad_probability IS NOT NULL) OR (status <> 'ok' AND ad_probability IS NULL)",
            name="ck_ad_judgement_ok_has_probability",
        ),
        sa.ForeignKeyConstraint(["review_id"], ["review.review_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_run.run_id"]),
        sa.PrimaryKeyConstraint("judgement_id"),
        sa.UniqueConstraint("review_id", "run_id", name="uq_ad_judgement_review_run"),
    )
    op.create_index("ix_ad_judgement_run_id", "ad_judgement", ["run_id"])
    op.create_table(
        "llm_call_log",
        sa.Column("call_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("call_type", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_run.run_id"]),
        sa.PrimaryKeyConstraint("call_id"),
    )
    op.create_index("ix_llm_call_log_run_id", "llm_call_log", ["run_id"])

    # Supabase는 RLS가 꺼진 테이블을 공개 API로 열어 둔다. product, review와 같이 켠다(PostgreSQL만).
    if op.get_bind().dialect.name == "postgresql":
        for table in NEW_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # 테이블을 지우면 RLS 설정도 함께 사라진다.
    op.drop_index("ix_llm_call_log_run_id", table_name="llm_call_log")
    op.drop_table("llm_call_log")
    op.drop_index("ix_ad_judgement_run_id", table_name="ad_judgement")
    op.drop_table("ad_judgement")
    op.drop_table("pipeline_run")
    op.drop_table("round")
