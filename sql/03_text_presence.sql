-- 03_text_presence.sql
--
-- 목적: 상품별과 전체의 "본문 있는 리뷰" 건수와 비율을 센다. 부록 B(docs/plan.md)의 SQL 교차검증 쿼리 3.
--        파이썬 집계(backend/app/services/review_stats.py의 has_text, aggregate_review_stats)와 대조한다.
--
-- 집계 기준 (파이썬 쪽 기준을 그대로 옮김):
--   * 본문 있음 = review_text가 NULL이 아니고, 파이썬 strip()으로 공백을 제거한 뒤 비어 있지 않음.
--   * 파이썬 strip()의 공백 범위는 str.isspace()가 참인 문자이다. 아래 btrim의 문자 목록은 그 범위를
--     옮긴 것이다: U+0009~000D, U+001C~001F, U+0020, U+0085, U+00A0, U+1680, U+2000~200A,
--     U+2028, U+2029, U+202F, U+205F, U+3000. 이 목록이 파이썬과 일치하는지는 04_whitespace_check.sql로 검증한다.
--   * 비율은 소수 넷째 자리까지 반올림한다. 리뷰가 0건이면 비율은 NULL(비율 없음)이다.
--   * 합계 행은 상품별 행의 합이다.
--   * 반올림 차이 가능성: 2026-11-02 실행에서는 드러나지 않음(상품별 비율의 다섯째 자리가 중간값이 아님). 다른 데이터에서의 일치는 보장하지 않는다.
--     (원리: 파이썬 round()는 이진 부동소수점을 짝수 쪽으로 반올림하고, PostgreSQL ROUND(numeric)는 0.5를 올린다.
--      정확히 다섯째 자리가 5로 끝나는 경우(예: 1/32)만 다를 수 있다.)
--
-- 사용한 구조: CTE(flagged, per_product), 서브쿼리(합계와 비율 분모), GROUP BY, UNION ALL
-- 방언: PostgreSQL 전용 (btrim(문자열, 문자 목록), COUNT(...) FILTER, COLLATE "C"). SQLite에서는 실행하지 않는다.
-- 실행: BEGIN READ ONLY / ROLLBACK 래퍼를 쓰지 않고 파일의 SELECT를 그대로 실행한다.
--        파일에는 SELECT만 있고 쓰기 구문이 없다(실행 전 눈으로 확인).
--        편집기가 마지막 구문 결과만 보여 줄 수 있어 래퍼는 결과를 가릴 수 있음(확인 필요).
-- 결과: 집계 수치만 나온다. review_text는 본문 있음 여부(참/거짓)를 계산하는 데만 쓰고 SELECT 목록에 없다.

WITH flagged AS (
    SELECT
        r.product_name,
        (
            r.review_text IS NOT NULL
            AND btrim(
                r.review_text,
                E'\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'
            ) <> ''
        ) AS has_text
    FROM review AS r
),
per_product AS (
    SELECT
        f.product_name,
        COUNT(*)                         AS review_count,
        COUNT(*) FILTER (WHERE f.has_text) AS with_text_count
    FROM flagged AS f
    GROUP BY f.product_name
)
SELECT
    result.label,
    result.review_count,
    result.with_text_count,
    result.with_text_ratio
FROM (
    SELECT
        0 AS sort_group,
        pp.product_name AS label,
        pp.review_count,
        pp.with_text_count,
        CASE WHEN pp.review_count = 0 THEN NULL
             ELSE ROUND(pp.with_text_count::numeric / pp.review_count, 4)
        END AS with_text_ratio
    FROM per_product AS pp

    UNION ALL

    SELECT
        1 AS sort_group,
        E'\ud569\uacc4' AS label,  -- 합계
        COALESCE(t.review_count, 0)     AS review_count,
        COALESCE(t.with_text_count, 0)  AS with_text_count,
        CASE WHEN COALESCE(t.review_count, 0) = 0 THEN NULL
             ELSE ROUND(t.with_text_count::numeric / t.review_count, 4)
        END AS with_text_ratio
    FROM (
        SELECT
            SUM(pp.review_count)::bigint    AS review_count,
            SUM(pp.with_text_count)::bigint AS with_text_count
        FROM per_product AS pp
    ) AS t
) AS result
ORDER BY result.sort_group, result.label COLLATE "C";
