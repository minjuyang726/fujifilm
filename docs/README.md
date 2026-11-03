# docs 색인

프로젝트 소개와 실행 명령은 루트의 [README.md](../README.md)에 있습니다. 이 폴더에는 아래 문서가 있습니다. 설명은 각 문서의 첫 부분에 적힌 내용입니다.

| 문서 | 설명 |
| --- | --- |
| [service-definition.md](service-definition.md) | 서비스 정의. 사용자, 불편, 핵심 행동을 정리한 문서 |
| [mvp.md](mvp.md) | MVP 정의. MVP 범위를 정리한 문서이고 범위의 근거는 service-definition.md |
| [prd.md](prd.md) | 제품 요구사항(PRD). 범위의 근거는 mvp.md이고, 확인이 필요한 항목은 문서 안에 번호로 모아 둠 |
| [spec.md](spec.md) | 기술 명세. 요구사항의 근거는 prd.md이고, 확인이 필요한 항목은 문서 안에 SQ 번호로 모아 둠 |
| [plan.md](plan.md) | 구현 계획. Phase별로 무엇을 만들고 어떻게 확인하는지를 적었고 코드는 없음. 범위의 근거는 mvp.md, 요구사항은 prd.md, 구현 계약은 spec.md |
| [data_quality.md](data_quality.md) | 데이터 품질 점검. 적재 리뷰와 회차 집계 대상의 구분, 무결성 결과, 표본 크기, 합성 설문 구조, 수집 기록(미확인 항목 포함), 월·분기별 건수 |
| [sql_crosscheck.md](sql_crosscheck.md) | SQL 교차검증(plan.md 부록 B). 부록 A 데모(`GET /api/demo/review-stats`)가 파이썬으로 센 집계를 SQL로 다시 세어 건수 단위로 대조한 기록 |

문서 사이의 근거 관계는 각 문서 첫머리에 적힌 대로입니다: mvp.md ← service-definition.md, prd.md ← mvp.md, spec.md ← prd.md, plan.md ← mvp.md·prd.md·spec.md. 문서를 읽는 순서는 문서 안에 적혀 있지 않아 이 색인에서도 정하지 않았습니다.

표기 규칙(결정, 가정, 설계 제안, 확인 필요 등)은 각 문서의 "표기 규칙" 절을 따릅니다.
