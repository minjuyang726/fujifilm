-- 02_quarterly_counts.sql
--
-- 목적: 리뷰 날짜의 달력 분기별 건수를 센다. 빈 분기는 0건으로 채운다. 부록 B(docs/plan.md)의 SQL 교차검증 쿼리 2.
--        파이썬 집계(backend/app/services/review_stats.py의 aggregate_review_stats)와 대조한다.
--
-- 집계 기준 (파이썬 쪽 기준을 그대로 옮김):
--   * 분기는 review."date"의 달력 분기이다(1~3월 Q1, 4~6월 Q2, 7~9월 Q3, 10~12월 Q4). 회차 기준이 아니다.
--   * 표기는 YYYY-Qn (예: 2025-Q1).
--   * 데이터의 첫 분기부터 마지막 분기까지 빈 분기를 0건으로 채운다.
--   * 리뷰가 하나도 없으면 결과가 비어 있다(파이썬도 빈 목록을 돌려준다).
--   * review."date"는 date 타입이고 NOT NULL이다(backend/migrations/versions/0001_product_review.py).
--
-- 사용한 구조: CTE(bounds, quarters, counts), LEFT JOIN, GROUP BY
-- 방언: PostgreSQL 전용 (date_trunc, generate_series, to_char). SQLite에서는 실행하지 않는다.
-- 시간대: date를 timestamp(시간대 없음)로 바꾼 뒤 date_trunc를 써서 세션 시간대의 영향을 받지 않게 했다.
-- 실행: BEGIN READ ONLY / ROLLBACK 래퍼를 쓰지 않고 파일의 SELECT를 그대로 실행한다.
--        파일에는 SELECT만 있고 쓰기 구문이 없다(실행 전 눈으로 확인).
--        편집기가 마지막 구문 결과만 보여 줄 수 있어 래퍼는 결과를 가릴 수 있음(확인 필요).
-- 결과: 집계 수치만 나온다. 리뷰 원문, 제목, 작성자는 SELECT 목록에 없다.

WITH bounds AS (
    SELECT
        date_trunc('quarter', MIN(r."date")::timestamp) AS first_quarter,
        date_trunc('quarter', MAX(r."date")::timestamp) AS last_quarter
    FROM review AS r
),
quarters AS (
    SELECT generate_series(b.first_quarter, b.last_quarter, interval '3 months') AS quarter_start
    FROM bounds AS b
),
counts AS (
    SELECT
        date_trunc('quarter', r."date"::timestamp) AS quarter_start,
        COUNT(*)                                   AS review_count
    FROM review AS r
    GROUP BY 1
)
SELECT
    to_char(q.quarter_start, 'YYYY') || '-Q' || to_char(q.quarter_start, 'Q') AS quarter,
    COALESCE(c.review_count, 0)                                              AS review_count
FROM quarters AS q
LEFT JOIN counts AS c
    ON c.quarter_start = q.quarter_start
ORDER BY q.quarter_start;
