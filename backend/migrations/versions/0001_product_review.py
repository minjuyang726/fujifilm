"""product and review tables

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product",
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("product_name"),
    )
    op.create_table(
        "review",
        sa.Column("review_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("variant", sa.Text(), nullable=True),
        sa.Column("helpful_count", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating"),
        sa.CheckConstraint("helpful_count >= 0", name="ck_review_helpful_count"),
        sa.ForeignKeyConstraint(["product_name"], ["product.product_name"]),
        sa.PrimaryKeyConstraint("review_id"),
    )
    op.create_index("ix_review_product_name_date", "review", ["product_name", "date"])
    op.create_index("ix_review_rating", "review", ["rating"])


def downgrade() -> None:
    op.drop_index("ix_review_rating", table_name="review")
    op.drop_index("ix_review_product_name_date", table_name="review")
    op.drop_table("review")
    op.drop_table("product")
