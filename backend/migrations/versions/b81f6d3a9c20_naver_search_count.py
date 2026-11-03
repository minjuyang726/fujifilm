"""naver search count

Revision ID: b81f6d3a9c20
Revises: c50aa015e072
Create Date: 2026-11-03 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b81f6d3a9c20'
down_revision: Union[str, Sequence[str], None] = 'c50aa015e072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('naver_search_count',
    sa.Column('count_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('query', sa.Text(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("source IN ('blog', 'cafearticle')", name='ck_naver_search_count_source'),
    sa.CheckConstraint('total >= 0', name='ck_naver_search_count_total'),
    sa.PrimaryKeyConstraint('count_id')
    )
    op.create_index('ix_naver_search_count_query', 'naver_search_count', ['source', 'query', 'collected_at'], unique=False)

    # Supabase는 RLS가 꺼진 테이블을 공개 API로 열어 둔다. 기존 테이블과 같이 켠다(PostgreSQL만).
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE naver_search_count ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index('ix_naver_search_count_query', table_name='naver_search_count')
    op.drop_table('naver_search_count')
