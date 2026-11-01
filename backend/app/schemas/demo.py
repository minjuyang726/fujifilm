"""A-11(포트폴리오 데모) 응답 모델. 집계 숫자만 담고, 리뷰 본문·제목·작성자 필드는 없다."""

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RatingCount(_Strict):
    rating: int
    count: int


class ProductStats(_Strict):
    product_name: str
    review_count: int
    rating_distribution: list[RatingCount]
    with_text_count: int
    with_text_ratio: float | None


class QuarterCount(_Strict):
    quarter: str
    count: int


class TotalStats(_Strict):
    review_count: int
    with_text_count: int
    with_text_ratio: float | None


class ReviewStatsResponse(_Strict):
    products: list[ProductStats]
    quarters: list[QuarterCount]
    total: TotalStats
