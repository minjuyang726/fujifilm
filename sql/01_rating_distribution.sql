-- 01_rating_distribution.sql
--
-- 목적: 상품별 리뷰 수와 평점 1~5점 건수를 센다. 부록 B(docs/plan.md)의 SQL 교차검증 쿼리 1.
--        파이썬 집계(backend/app/services/review_stats.py의 aggregate_review_stats)와 건수 단위로 대조한다.
--
-- 집계 기준 (파이썬 쪽 기준을 그대로 옮김):
--   * 상품 단위: review.product_name. product와 외래키(review.product_name -> product.product_name)로 JOIN한다.
--   * 평점 분포는 1~5점 다섯 칸이고, 없는 점수는 0이다.
--   * 상품 순서는 이름순이다. 파이썬 sorted()는 유니코드 코드포인트 순서라서 COLLATE "C"로 맞춘다.
--   * 평점이 1~5 밖인 행은 파이썬이 오류를 내므로, 여기서는 out_of_range_count로 센다(0이어야 한다).
--   * INNER JOIN을 쓴다. 리뷰가 없는 상품은 파이썬 결과에도 나오지 않으므로 같은 기준이다.
--     리뷰가 0건인 상품까지 보이게 하려면 LEFT JOIN으로 바꿔야 한다(plan.md 부록 B의 확인 필요 항목).
--
-- 사용한 구조: JOIN, GROUP BY
-- 방언: PostgreSQL 전용 (COUNT(...) FILTER, COLLATE "C"). SQLite에서는 실행하지 않는다.
-- 실행: BEGIN READ ONLY / ROLLBACK 래퍼를 쓰지 않고 파일의 SELECT를 그대로 실행한다.
--        파일에는 SELECT만 있고 쓰기 구문이 없다(실행 전 눈으로 확인).
--        편집기가 마지막 구문 결과만 보여 줄 수 있어 래퍼는 결과를 가릴 수 있음(확인 필요).
-- 결과: 집계 수치만 나온다. 리뷰 원문, 제목, 작성자는 SELECT 목록에 없다.

SELECT
    p.product_name,
    COUNT(r.review_id)                                   AS review_count,
    COUNT(r.review_id) FILTER (WHERE r.rating = 1)       AS rating_1,
    COUNT(r.review_id) FILTER (WHERE r.rating = 2)       AS rating_2,
    COUNT(r.review_id) FILTER (WHERE r.rating = 3)       AS rating_3,
    COUNT(r.review_id) FILTER (WHERE r.rating = 4)       AS rating_4,
    COUNT(r.review_id) FILTER (WHERE r.rating = 5)       AS rating_5,
    COUNT(r.review_id) FILTER (WHERE r.rating NOT BETWEEN 1 AND 5) AS out_of_range_count
FROM product AS p
JOIN review AS r
    ON r.product_name = p.product_name
GROUP BY p.product_name
ORDER BY p.product_name COLLATE "C";
