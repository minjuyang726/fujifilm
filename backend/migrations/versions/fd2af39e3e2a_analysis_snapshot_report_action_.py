"""analysis snapshot report action suggestion

Revision ID: fd2af39e3e2a
Revises: 4d7cdf97c911
Create Date: 2026-11-03 09:22:51.339864

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd2af39e3e2a'
down_revision: Union[str, Sequence[str], None] = '4d7cdf97c911'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TABLES = ("analysis_snapshot", "report", "action_suggestion")


def upgrade() -> None:
    op.create_table('analysis_snapshot',
    sa.Column('snapshot_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('round_id', sa.Integer(), nullable=False),
    sa.Column('family_id', sa.Integer(), nullable=False),
    sa.Column('table_json', sa.JSON(), nullable=False),
    sa.Column('allowed_evidence_json', sa.JSON(), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['family_id'], ['product_family.family_id'], ),
    sa.ForeignKeyConstraint(['round_id'], ['round.round_id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['pipeline_run.run_id'], ),
    sa.PrimaryKeyConstraint('snapshot_id')
    )
    op.create_index('ix_analysis_snapshot_round_family', 'analysis_snapshot', ['round_id', 'family_id'], unique=False)
    op.create_table('report',
    sa.Column('report_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('round_id', sa.Integer(), nullable=False),
    sa.Column('family_id', sa.Integer(), nullable=True),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['family_id'], ['product_family.family_id'], ),
    sa.ForeignKeyConstraint(['round_id'], ['round.round_id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['pipeline_run.run_id'], ),
    sa.PrimaryKeyConstraint('report_id')
    )
    op.create_index('ix_report_round_family', 'report', ['round_id', 'family_id'], unique=False)
    op.create_table('action_suggestion',
    sa.Column('suggestion_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('snapshot_id', sa.Integer(), nullable=False),
    sa.Column('order_no', sa.Integer(), nullable=False),
    sa.Column('sentence', sa.Text(), nullable=False),
    sa.Column('row_ids', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['report_id'], ['report.report_id'], ),
    sa.ForeignKeyConstraint(['snapshot_id'], ['analysis_snapshot.snapshot_id'], ),
    sa.PrimaryKeyConstraint('suggestion_id'),
    sa.UniqueConstraint('report_id', 'order_no', name='uq_action_suggestion_report_order')
    )

    # Supabase는 RLS가 꺼진 테이블을 공개 API로 열어 둔다. 기존 테이블과 같이 켠다(PostgreSQL만).
    if op.get_bind().dialect.name == "postgresql":
        for table in NEW_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # 테이블을 지우면 RLS 설정도 함께 사라진다.
    op.drop_table('action_suggestion')
    op.drop_index('ix_report_round_family', table_name='report')
    op.drop_table('report')
    op.drop_index('ix_analysis_snapshot_round_family', table_name='analysis_snapshot')
    op.drop_table('analysis_snapshot')
