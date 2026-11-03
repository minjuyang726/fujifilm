"""hypothesis and next survey question

Revision ID: c50aa015e072
Revises: fd2af39e3e2a
Create Date: 2026-11-03 10:27:38.254790

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c50aa015e072'
down_revision: Union[str, Sequence[str], None] = 'fd2af39e3e2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TABLES = ("hypothesis", "next_survey_question")


def upgrade() -> None:
    op.create_table('hypothesis',
    sa.Column('hypothesis_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('snapshot_id', sa.Integer(), nullable=False),
    sa.Column('round_id', sa.Integer(), nullable=False),
    sa.Column('family_id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('related_row_ids', sa.JSON(), nullable=False),
    sa.CheckConstraint("kind IN ('uncertain', 'contradictory')", name='ck_hypothesis_kind'),
    sa.ForeignKeyConstraint(['family_id'], ['product_family.family_id'], ),
    sa.ForeignKeyConstraint(['round_id'], ['round.round_id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['pipeline_run.run_id'], ),
    sa.ForeignKeyConstraint(['snapshot_id'], ['analysis_snapshot.snapshot_id'], ),
    sa.PrimaryKeyConstraint('hypothesis_id')
    )
    op.create_index('ix_hypothesis_snapshot_id', 'hypothesis', ['snapshot_id'], unique=False)
    op.create_table('next_survey_question',
    sa.Column('question_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('hypothesis_id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=True),
    sa.Column('order_no', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('options_json', sa.JSON(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.CheckConstraint("status = 'draft'", name='ck_next_survey_question_status'),
    sa.CheckConstraint("type IN ('scale5', 'single', 'multi')", name='ck_next_survey_question_type'),
    sa.ForeignKeyConstraint(['hypothesis_id'], ['hypothesis.hypothesis_id'], ),
    sa.ForeignKeyConstraint(['report_id'], ['report.report_id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['pipeline_run.run_id'], ),
    sa.PrimaryKeyConstraint('question_id')
    )
    op.create_index('ix_next_survey_question_report_run', 'next_survey_question', ['report_id', 'run_id'], unique=False)

    # Supabase는 RLS가 꺼진 테이블을 공개 API로 열어 둔다. 기존 테이블과 같이 켠다(PostgreSQL만).
    if op.get_bind().dialect.name == "postgresql":
        for table in NEW_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # 테이블을 지우면 RLS 설정도 함께 사라진다.
    op.drop_index('ix_next_survey_question_report_run', table_name='next_survey_question')
    op.drop_table('next_survey_question')
    op.drop_index('ix_hypothesis_snapshot_id', table_name='hypothesis')
    op.drop_table('hypothesis')
