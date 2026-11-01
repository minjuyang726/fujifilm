from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Product(Base):
    """쿠팡 상품. 제품군(family_id)은 제품군 목록이 정해지는 Phase 1(G1)에서 추가한다."""

    __tablename__ = "product"

    product_name: Mapped[str] = mapped_column(Text, primary_key=True)
