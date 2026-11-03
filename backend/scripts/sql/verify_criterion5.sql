-- plan.md Phase 4 완료 확인 기준 5를 Supabase SQL Editor에서 직접 확인하는 읽기 전용 SELECT.
-- 서비스 코드를 거치지 않고 ad_judgement 테이블의 ad_weight만 읽는다. 쓰기 문장은 없다. 리뷰 본문과 제목은 읽지 않는다.
-- 화면 값과 비교: 합계 행의 weight_with_floor 합이 화면의 "가중 건수"(소수 2자리)와 같으면 통과.

-- (1) 제품군 2(인스탁스 즉석카메라) x 2026-Q1: 판정 묶음의 review_id 4개 (1606, 2123, 2138, 2141), 기대 합계 3.56
with w as (
  select review_id, ad_weight, greatest(0.1, ad_weight) as weight_with_floor
  from ad_judgement
  where status = 'ok'
    and review_id in (1606, 2123, 2138, 2141)
)
select review_id::text as review_id, ad_weight, weight_with_floor from w
union all
select '합계', sum(ad_weight), sum(weight_with_floor) from w
order by 1;

-- (2) 하한이 실제로 적용되는 조합: 제품군 2 x 2026-Q2 (review_id 7개), 기대: ad_weight 합 3.72 / weight_with_floor 합 3.99
with w as (
  select review_id, ad_weight, greatest(0.1, ad_weight) as weight_with_floor
  from ad_judgement
  where status = 'ok'
    and review_id in (2059, 2062, 2070, 2080, 2082, 2084, 2088)
)
select review_id::text as review_id, ad_weight, weight_with_floor from w
union all
select '합계', sum(ad_weight), sum(weight_with_floor) from w
order by 1;

-- (3) review_id 목록을 직접 확인하는 쿼리 (제품군 2, 2026-Q1). 제목 또는 본문이 있고 성공한 판정이 있는 글의 id만 나온다.
select r.review_id
from review r
join product p on p.product_name = r.product_name
join ad_judgement j on j.review_id = r.review_id and j.status = 'ok'
where p.family_id = 2
  and r.date between '2026-01-01' and '2026-03-31'
  and (r.title is not null or r.review_text is not null)
order by r.review_id;
