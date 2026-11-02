-- 04_whitespace_check.sql
--
-- 목적: 파이썬 strip()과 SQL 공백 처리가 달라질 수 있는 행의 "건수만" 센다. 부록 B(docs/plan.md)의 결정 2
--        (본문 판정 동등성 검증)에 해당하는 쿼리 4. 원문과 행은 출력하지 않는다.
--
-- 판정 방식:
--   본문 있음을 세 가지 SQL 정의로 각각 센다. 세 정의가 같은 건수를 내면 그 데이터에서는 정의 차이가 없다.
--     (P) 파이썬 동등: btrim(review_text, 파이썬 isspace 문자 목록) <> ''        <- 03_text_presence.sql과 같은 정의
--     (N) 단순 trim:   trim(review_text) <> ''                                    <- PostgreSQL trim은 스페이스(U+0020)만 지운다
--     (R) 정규식:      review_text !~ '^\s*$'                                      <- \s의 범위는 DB 로케일에 따라 다를 수 있다
--   (N)이 (P)와 다르면 탭, 줄바꿈, 전각 공백 같은 다른 공백만 있는 본문이 있다는 뜻이다(단순 trim은 이를 "본문 있음"으로 센다).
--   (R)이 (P)와 다르면 로케일의 공백 범위가 파이썬과 다르다는 뜻이다.
--   파이썬 strip()은 U+200B(너비 없는 공백), U+FEFF는 지우지 않는다. 이 문자들만 있는 본문은 파이썬에서 "본문 있음"이다.
--   그래서 (P)는 이 문자를 목록에 넣지 않았고, only_zero_width_count로 그런 행이 있는지 따로 센다.
--   * 이 파일은 파이썬 쪽 결과와 직접 비교하지 않는다. (P)의 건수가 파이썬 has_text=참 건수와 같은지는
--     docs/sql_crosscheck.md의 대조표로 확인한다(2026-11-02 실행해 docs/sql_crosscheck.md에 대조함).
--
-- 사용한 구조: 단일 SELECT, COUNT(...) FILTER (행은 한 줄만 나온다)
-- 방언: PostgreSQL 전용. SQLite에서는 실행하지 않는다.
-- 실행: BEGIN READ ONLY / ROLLBACK 래퍼를 쓰지 않고 파일의 SELECT를 그대로 실행한다.
--        파일에는 SELECT만 있고 쓰기 구문이 없다(실행 전 눈으로 확인).
--        편집기가 마지막 구문 결과만 보여 줄 수 있어 래퍼는 결과를 가릴 수 있음(확인 필요).
-- 결과: 건수만 나온다(한 줄). review_text는 FILTER 조건 안에서만 쓰고 SELECT 목록에 없다.

SELECT
    COUNT(*)                                                         AS total_rows,
    COUNT(*) FILTER (WHERE r.review_text IS NULL)                    AS null_text_count,
    COUNT(*) FILTER (WHERE r.review_text = '')                       AS empty_string_count,

    -- 세 가지 정의별 "본문 있음" 건수
    COUNT(*) FILTER (WHERE r.review_text IS NOT NULL AND btrim(
        r.review_text,
        E'\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'
    ) <> '')                                                         AS has_text_python_equivalent,
    COUNT(*) FILTER (WHERE r.review_text IS NOT NULL
                       AND trim(r.review_text) <> '')                AS has_text_plain_trim,
    COUNT(*) FILTER (WHERE r.review_text IS NOT NULL
                       AND r.review_text !~ '^\s*$')                 AS has_text_regex_s,

    -- 정의가 달라지는 행 수 (0이면 이 데이터에서는 차이가 없다)
    COUNT(*) FILTER (WHERE r.review_text IS NOT NULL
                       AND trim(r.review_text) <> ''
                       AND btrim(
                           r.review_text,
                           E'\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'
                       ) = '')                                       AS plain_trim_says_text_but_python_says_empty,
    COUNT(*) FILTER (WHERE r.review_text IS NOT NULL
                       AND (r.review_text !~ '^\s*$') <> (btrim(
                           r.review_text,
                           E'\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'
                       ) <> ''))                                     AS regex_differs_from_python_equivalent,

    -- 파이썬 strip()이 지우지 않는 보이지 않는 문자만 있는 본문 (파이썬에서는 "본문 있음"이다)
    COUNT(*) FILTER (WHERE r.review_text ~ E'^[\\u200b\\u200c\\u200d\\u2060\\ufeff]+$') AS only_zero_width_count
FROM review AS r;
