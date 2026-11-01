from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 테이블 정의의 부모. 테이블은 Phase 0b부터 추가한다."""
