"""survey tables and product family

Revision ID: c50a52659d39
Revises: 2c6efdf1a38e
Create Date: 2026-11-03 00:15:09.276845

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c50a52659d39'
down_revision: Union[str, Sequence[str], None] = '2c6efdf1a38e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TABLES = ("product_family", "survey_question", "survey_response", "survey_answer")


def upgrade() -> None:
    op.create_table('product_family',
    sa.Column('family_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('family_id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('survey_question',
    sa.Column('question_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('round_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('options_json', sa.JSON(), nullable=False),
    sa.CheckConstraint("type IN ('scale5', 'single', 'multi')", name='ck_survey_question_type'),
    sa.ForeignKeyConstraint(['round_id'], ['round.round_id'], ),
    sa.PrimaryKeyConstraint('question_id'),
    sa.UniqueConstraint('round_id', 'code', name='uq_survey_question_round_code')
    )
    op.create_table('survey_response',
    sa.Column('response_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('round_id', sa.Integer(), nullable=False),
    sa.Column('family_id', sa.Integer(), nullable=True),
    sa.Column('is_synthetic', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['family_id'], ['product_family.family_id'], ),
    sa.ForeignKeyConstraint(['round_id'], ['round.round_id'], ),
    sa.PrimaryKeyConstraint('response_id')
    )
    op.create_index('ix_survey_response_round_id', 'survey_response', ['round_id'], unique=False)
    op.create_table('survey_answer',
    sa.Column('answer_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('response_id', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.Integer(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['survey_question.question_id'], ),
    sa.ForeignKeyConstraint(['response_id'], ['survey_response.response_id'], ),
    sa.PrimaryKeyConstraint('answer_id')
    )
    op.create_index('ix_survey_answer_question_id', 'survey_answer', ['question_id'], unique=False)
    op.create_index('ix_survey_answer_response_id', 'survey_answer', ['response_id'], unique=False)

    # Supabase는 RLS가 꺼진 테이블을 공개 API로 열어 둔다. 기존 테이블과 같이 켠다(PostgreSQL만).
    if op.get_bind().dialect.name == "postgresql":
        for table in NEW_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # 테이블을 지우면 RLS 설정도 함께 사라진다.
    op.drop_index('ix_survey_answer_response_id', table_name='survey_answer')
    op.drop_index('ix_survey_answer_question_id', table_name='survey_answer')
    op.drop_table('survey_answer')
    op.drop_index('ix_survey_response_round_id', table_name='survey_response')
    op.drop_table('survey_response')
    op.drop_table('survey_question')
    op.drop_table('product_family')
