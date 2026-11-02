"""product family id

Revision ID: 4d7cdf97c911
Revises: c50a52659d39
Create Date: 2026-11-03

product.family_id(FK -> product_family, NULL 허용)를 추가한다. 값은 scripts/seed_families.py가 채운다.
RLS는 product 테이블에 이미 켜져 있어 다시 하지 않는다. SQLite는 ALTER로 제약을 못 달아 batch 모드를 쓴다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d7cdf97c911'
down_revision: Union[str, Sequence[str], None] = 'c50a52659d39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_product_family_id"


def upgrade() -> None:
    with op.batch_alter_table("product") as batch:
        batch.add_column(sa.Column("family_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(FK_NAME, "product_family", ["family_id"], ["family_id"])


def downgrade() -> None:
    with op.batch_alter_table("product") as batch:
        batch.drop_constraint(FK_NAME, type_="foreignkey")
        batch.drop_column("family_id")
