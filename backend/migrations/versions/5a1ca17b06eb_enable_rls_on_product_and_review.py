"""enable rls on product and review

Revision ID: 5a1ca17b06eb
Revises: 0001
Create Date: 2026-11-01 18:35:02.291551

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a1ca17b06eb'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE product ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE review ENABLE ROW LEVEL SECURITY")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE review DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE product DISABLE ROW LEVEL SECURITY")
