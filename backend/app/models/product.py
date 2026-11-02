from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Product(Base):
    """쿠팡 상품. family_id는 제품군 시드(scripts/seed_families.py, G1)가 채운다. 정해지기 전에는 NULL."""

    __tablename__ = "product"

    product_name: Mapped[str] = mapped_column(Text, primary_key=True)
    family_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("product_family.family_id"), nullable=True)
