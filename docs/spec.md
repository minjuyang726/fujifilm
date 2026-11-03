# 기술 명세 (Spec)

한국후지필름형 정기 설문 폐루프 에이전트의 기술 명세입니다. 요구사항의 근거는 [prd.md](prd.md)이고, 그 근거는 [mvp.md](mvp.md)와 [service-definition.md](service-definition.md)입니다. 이 문서에는 코드가 없고, 구현 전에 정해야 할 구조와 계약만 적었습니다.

## 표기 규칙

| 표기 | 의미 |
| --- | --- |
| 결정 | 사용자가 정한 내용 또는 prd.md에서 이미 결정된 내용 |
| 가정 | 설계를 위해 둔 값. 출처 없음 |
| 설계 제안 | prd.md에 없는 구현 선택. 승인 전까지 확정이 아님 |
| 확인 필요 | 값이나 사실을 모르는 항목. 12절 목록에 SQ 번호로 모았다 (prd.md의 Q 번호와 구분) |

- prd.md에 없는 기능은 넣지 않았습니다. 필요해 보이는 것은 11절 "제안"에 따로 분리했고, 승인 전까지 명세가 아닙니다.
- 수치에는 실측/가정/합성 중 하나를 붙입니다.
- 요구사항 번호(FR, DR, NFR)는 prd.md의 번호입니다.

## 1. 기술 스택

| 영역 | 선택 | 비고 |
| --- | --- | --- |
| Backend | FastAPI (Python) | 개발용 실행 포트 8000 (결정). Python 3.13(이 컴퓨터에 설치된 3.13.14 확인), pip + `requirements.txt` (결정, SQ-10). 다른 팀원 환경은 확인하지 못함 |
| Frontend | React | 개발용 실행 포트 5173 (결정). JavaScript(TypeScript 아님), Vite, React Router (결정, SQ-10). 5173은 Vite의 기본 포트와 같다. 차트 라이브러리는 확인 필요: 대시보드 집계 지표(SQ-1)가 먼저 정해져야 한다 |
| DB | Supabase (PostgreSQL) | 접속 문자열 `DATABASE_URL`은 session pooler 방식이며 `backend/.env`에만 둔다 (결정). 풀 크기와 보안 설정은 확인 필요 SQ-11 |
| 테스트 | SQLite | 테스트는 Supabase가 아니라 SQLite로 돈다 (결정). 파이썬 표준 `sqlite3`를 쓰며 따로 설치하지 않는다 (이 컴퓨터에서 3.50.4 확인). 프레임워크는 pytest (결정, SQ-10) |
| 정기 실행 | n8n | 회차별 정기 실행과 단계 연결을 맡는다 (결정). 리포트 생성의 실행 방식으로 확정된 것은 아님(prd.md Q-4, 확인 필요 SQ-8) |
| LLM | OpenAI API | 키는 `backend/.env`에만 둔다 (결정). 광고성 판정 모델은 `gpt-5.6-luna`(prd.md Q-12, 2026-11-02, 판정 품질은 파일럿과 골든셋으로 확인 예정). 문항·제안 호출의 모델 이름은 정해지지 않음 (확인 필요 SQ-9) |

**PostgreSQL과 SQLite를 함께 쓰므로 지켜야 할 규칙 (설계 제안)**
- 두 DB에서 모두 동작하는 자료형만 쓴다: 정수, 텍스트, 날짜, 실수(또는 고정 소수), 불리언, JSON. DB 고유의 배열형, 열거형, JSONB 전용 연산은 쓰지 않는다.
- 열거형은 텍스트 열과 CHECK 제약으로 표현한다.
- 테이블은 ORM의 메타데이터에서 만들어 테스트와 운영이 같은 정의를 쓰게 한다. ORM과 마이그레이션 도구는 SQLAlchemy와 Alembic이다 (결정). Postgres 드라이버는 psycopg 3, 파이썬 가상환경은 `backend/.venv`이다 (결정). 나머지 도구는 확인 필요 SQ-10.
- Supabase session pooler 연결에는 SSL이 필요하다. 연결 문자열 형식과 풀 설정은 확인 필요 SQ-11.

**비밀 값 (prd.md NFR-K1, NFR-K2)**
- `OPENAI_API_KEY`(변수 이름은 가정)와 `DATABASE_URL`은 `backend/.env`에만 둔다. 저장소에는 `.env.example`만 올린다.
- n8n의 자격 증명은 n8n credential에만 둔다. n8n은 backend API를 호출하므로 OpenAI 키를 가질 필요가 없다 (설계 제안).
- 프런트엔드에는 비밀 값이 없고, backend API 주소만 환경 값으로 둔다.

## 2. 폴더 구조

루트에는 `frontend`, `backend`, `database`, `docs`가 있습니다. 루트에 원래 있던 `쿠팡 크롤러` 폴더는 이 명세의 범위 밖이며 건드리지 않습니다.

```
fujifilm/
├── .gitignore
├── backend/
│   ├── .env                  (미추적: OPENAI_API_KEY, DATABASE_URL)
│   ├── .env.example          (추적)
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py         환경 값 읽기
│   │   ├── db.py             DB 연결
│   │   ├── core/             오류 처리, 로깅, request_id
│   │   ├── models/           테이블 정의
│   │   ├── schemas/          요청·응답 형태
│   │   ├── routers/          families, rounds, dashboard, evidence, reports, pipeline
│   │   ├── services/         aggregation, weighting, ad_judgement, snapshot, suggestions, survey_draft, report_builder
│   │   └── llm/              client, prompts/, output_schemas/, validators
│   ├── scripts/              Phase 0 적재 스크립트 (리뷰, 설문 응답, 합성 응답)
│   ├── n8n/                  n8n 워크플로 내보내기 JSON (자격 증명 제외, 기본안)
│   ├── tests/
│   └── logs/                 (미추적)
├── frontend/
│   └── src/                  api/, pages/, components/
├── database/                 역할은 확인 필요 SQ-11
└── docs/
```

- `scripts/`는 담당자 업로드 화면이 MVP에서 제외되어서 필요한 폴더입니다(prd.md 7절, DR-1). API로 적재하는 엔드포인트는 두지 않습니다.
- n8n 워크플로 파일 위치는 정해지지 않았습니다(확인 필요 SQ-8). 기본안(설계 제안)은 `backend/n8n/`입니다. 워크플로가 backend의 단계 엔드포인트(A-8)를 호출하므로 두 파일을 함께 보기 쉽고, 루트 폴더를 늘리지 않습니다. 내보낸 JSON에는 자격 증명(credential)을 넣지 않습니다(NFR-K2).
- 원본 CSV와 합성 응답 결과는 `database/data/`에 두고 `.gitignore`로 추적에서 뺍니다(결정, SQ-11). CSV에는 작성자 열이 있어서 결정 전에는 추적 폴더에 넣지 않는 편이 안전합니다 (설계 제안).

## 3. 데이터 모델

### 3.1 리뷰 테이블과 실제 CSV 열의 대조

요청하신 기준 열(review_id, product_name, rating, date, variant, helpful_count, title, review_text)을 실제 CSV(`coupang_fujifilm_reviews_merged.csv`, 12개 열, 1,302행)와 대조했습니다. 아래 값은 모두 CSV를 직접 집계한 실측입니다.

| CSV 열 | 대조 결과 | 리뷰 테이블 처리 |
| --- | --- | --- |
| review_id | 정수, 1,302개 모두 고유, 1043~2344에 빠짐없이 연속 | 기본 키 |
| product_name | 3개 값, 최대 52자 | 상품 테이블과 연결 (3.2) |
| rating | 1~5 정수 1,302건 | 정수, 1~5 CHECK |
| date | `YYYY-MM-DD` 형식 1,302건, 2017-06-24 ~ 2026-10-27 | 날짜 |
| variant | 351건에만 값이 있고(MINI12만), 상품명에 "1세트"가 붙은 문구. 빈 값 951건 | 문자열, 빈 값은 NULL. 화면 표시와 LLM 입력에서 제외(FR-2.5) |
| helpful_count | 정수 1,302건, 최댓값 154 | 정수, 0 이상 |
| title | 값이 있는 것 150건, 빈 값 1,152건, 최대 33자 | 문자열, 빈 값은 NULL |
| review_text | 값이 있는 것 297건, 빈 값 1,005건, 최대 2,580자, 줄바꿈 포함 40건 | 문자열, 빈 값은 NULL |
| source_file | 상품과 1:1 대응(3개 값) | **적재하지 않음.** 상품이 같은 정보를 가진다. 적재 출처는 스크립트 로그에 남긴다 (설계 제안) |
| original_no | 정수, 1,302개 모두 고유 | **적재하지 않음.** 기준 열에 없다. 원본 추적이 필요하면 CSV에 남아 있다 (설계 제안) |
| author | 1,302건 모두 값이 있음, 고유값 903개 | **적재하지 않음(결정, SQ-7).** 표시와 LLM 입력에서도 제외한다(P-4). 적재 스크립트는 이 열을 읽지 않는다 |
| seller | 1,302건 모두 빈 값 | **적재하지 않음** |

- CSV에서 빈 값은 NULL이 아니라 빈 문자열로 들어 있습니다(title 1,152건, review_text 1,005건, variant 951건). 적재할 때 NULL로 바꿉니다.
- prd.md는 "텍스트가 있는 리뷰 297건", "제목이나 본문이 있는 리뷰 310건, 둘 다 빈 리뷰 992건"이라고 했고, 이 대조로 같은 수를 확인했습니다. 광고성 판정 대상은 제목이나 본문이 있는 310건입니다(6.2 호출 A). 제목·본문이 모두 없는 992건은 집계에서 "제목·본문 없음" 묶음으로 따로 표시합니다(P-5 승인, FR-1.11).
- `date`라는 열 이름은 PostgreSQL과 SQLite 모두 열 이름으로 쓸 수 있어 CSV 이름 그대로 둡니다. 불편하면 이름을 바꿀 수 있습니다.

### 3.2 테이블 정의

모든 테이블은 3.1의 규칙(두 DB에서 동작하는 자료형)을 따릅니다. "FK"는 외래 키입니다.

**product_family (제품군)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| family_id | 정수, 기본 키 | |
| name | 텍스트, 고유 | 목록은 미정(prd.md Q-3). 제안은 "일회용 카메라" / "인스탁스 즉석카메라" 2개이나 결정이 아님 |

**product (상품)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| product_name | 텍스트, 기본 키 | 쿠팡 CSV의 상품명 3개 |
| family_id | FK → product_family, NULL 허용 | 제품군이 정해지기 전에는 NULL. 구현됨(마이그레이션 `4d7cdf97c911`). 값은 `scripts/seed_families.py`가 채우며, 대응은 상품명이 근거이고 대응표에 없는 상품은 NULL로 둔다 |

**review (쿠팡 리뷰)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| review_id | 정수, 기본 키 | CSV 값 그대로 |
| product_name | FK → product | |
| rating | 정수 | 1~5 CHECK |
| date | 날짜 | |
| variant | 텍스트, NULL 허용 | |
| helpful_count | 정수 | 0 이상 |
| title | 텍스트, NULL 허용 | |
| review_text | 텍스트, NULL 허용 | |

- 인덱스: (product_name, date), rating.
- 네이버 블로그·카페 글은 열 구성이 정해지지 않아 테이블을 정의하지 않았다(확인 필요 SQ-12).(취소됨, 결정 2026-11-03)

**round (회차)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| round_id | 정수, 기본 키 | |
| label | 텍스트 | 예: 회차 이름 |
| period_start, period_end | 날짜, NULL 허용 | 리뷰를 회차에 어떻게 대응시킬지 정해지지 않아 NULL 허용(확인 필요 SQ-6) |

**survey_question / survey_response / survey_answer (설문)**

KOSSDA 자료의 변수 구조 개요는 확인되었습니다(전달받은 값, 실측). 변수 단위의 열 정의는 아직 확정하지 않았습니다(확인 필요 SQ-5).
- 15683(주): 변수 177개, 1,500행. 국가 변수 `CONTURY`로 한국 응답자 500명을 걸러야 한다.
- 14488(보조): 변수 80개, 417행. 국적 변수 `nationality`로 한국인 234명을 걸러야 한다.
- 두 자료 모두 가중치 변수가 없다.
- 14488은 설문지가 7점 척도인데 데이터 값은 1~5뿐이다. 노션에 남아 있는 불일치이며 아직 해소되지 않았다.
- 적재 스크립트(Phase 0)는 위 변수로 한국 응답자만 걸러 적재한다.

| 테이블 | 열 | 비고 |
| --- | --- | --- |
| survey_question | question_id(PK), round_id(FK), code, text, type, options_json | `type`은 `scale5` / `single` / `multi` 세 가지다(예/아니오와 빈도는 `single`). `options_json`은 `[{"code": "1", "label": "…"}, …]` 형태이고 순서를 유지한다. **UNIQUE(round_id, code)** (이 명세에 없던 제약을 추가함). 인덱스는 없다. (결정 2026-11-03, 사용자 승인) |
| survey_response | response_id(PK), round_id(FK), family_id(FK → product_family, NULL 허용), is_synthetic(불리언, NOT NULL). 인덱스: `round_id` (구현에서 추가) | 합성 응답에는 "합성" 표시를 데이터에 고정(DR-2). 합성 응답을 제품군에 연결하는 방식은 확인 필요 SQ-5. 기본안(설계 제안)은 제품군과 무관한 공통 설문이라 `family_id`는 NULL |
| survey_answer | answer_id(PK), response_id(FK), question_id(FK), value | `value`는 문자열(선택지 코드)이다. 다중선택(`multi`)은 선택 하나당 한 행이다. 인덱스: `response_id`, `question_id` (구현에서 추가). (결정 2026-11-03, 사용자 승인) |

**ad_judgement (광고성 판정)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| judgement_id | 정수, 기본 키 | |
| review_id | FK → review | |
| run_id | FK → pipeline_run | |
| ad_probability | 실수, NULL 허용 | 0~1 CHECK |
| ad_weight | 실수, NULL 허용 | 1 − ad_probability(FR-1.5, 1.7). 구현(Phase 3)은 하한 없이 `1 − 확률`을 저장한다. 하한은 임시 0.1로 둔다(2026-11-02). 근거는 약하다. 하한은 집계 시점에 적용하고 저장된 `ad_weight`(1 − 확률)는 바꾸지 않는다(Phase 4에서 구현, 설정 `AD_WEIGHT_FLOOR` 기본 0.1). prd.md Q-7 |
| model_name, prompt_version | 텍스트, NULL 허용 | 반복 실행 일치율(NFR-R1) 측정용. `skipped`는 LLM을 부르지 않아 NULL |
| status | 텍스트 | `ok`, `failed`, `skipped` CHECK. 제목·본문이 모두 없는 글은 LLM에 보내지 않고 `skipped`로 기록한다 |
| error_code | 텍스트, NULL 허용 | |
| judged_at | 시각 | |

- 구현에서 추가한 제약: `(review_id, run_id)` 유일, `status = 'ok'`일 때만 `ad_probability`가 NULL이 아님(CHECK), `run_id` 색인.
- `weight_floor_used`(하한 값 기록)와 `rule_signals`(규칙 신호)는 구현하지 않았다. 규칙 신호는 골든셋 결과를 본 뒤 정하고(SQ-3 결정 A, 2026-11-02), 하한은 임시 0.1로 둔다(2026-11-02, 근거는 약하다, prd.md Q-7). 하한은 집계 시점에 적용하므로 Phase 4에서 구현한다.

- 글은 삭제하지 않고 가중만 낮춥니다(FR-1.6, DR-3). 이 테이블은 리뷰를 바꾸지 않습니다.
- 이전 실행의 판정을 남길지 덮어쓸지는 정해지지 않았습니다(확인 필요 SQ-8). 기본안(설계 제안)은 남기는 것입니다.

**analysis_snapshot (분석 스냅샷, 설계 제안)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| snapshot_id | 정수, 기본 키 | |
| run_id, round_id, family_id | FK | |
| table_json | JSON | 코드가 계산한 표. LLM의 입력(FR-0.2) |
| allowed_evidence_json | JSON | 표의 각 행이 가리킬 수 있는 근거 ID 목록 |
| computed_at | 시각 | |

- 서술 속 수치가 코드 계산값과 일치하는지(FR-0.3), 근거 ID가 실제로 있는지(FR-2.4)를 검사하려면 LLM에 준 표를 나중에도 확인할 수 있어야 해서 저장합니다. prd.md의 DR에는 없는 테이블입니다.

**구현에서 정함 (Phase 5, 스냅샷, 결정 2026-11-03, 사용자 승인)**
- 스냅샷은 제품군 x 회차마다 하나다(`family_id` NOT NULL). `analysis-snapshot`을 실행할 때마다 쌓는다. 계산은 코드가 하고(`app/services/snapshot.py`) LLM을 쓰지 않는다. 같은 입력이면 `table_json`이 같다.
- `table_json` = `{family, round, rows}`. 행은 `{row_id, group, source, item, metrics, small_sample}`이다. `group`은 설문 또는 VOC, `source`는 설문이 "합성"이고 VOC가 "실측", `metrics`는 지표 이름 → 숫자, `small_sample`은 판정 묶음 행에서 판정 n이 임계값 미만일 때 참이다. 리뷰 본문과 작성자는 담지 않는다.
- 설문 행: `survey:respondents`(응답자 수), 문항 x 선택지마다 `survey:{문항코드}:{선택지코드}`(응답 수, 비율(%) 소수 1자리, 선택지 번호). 문항 10개의 선택지 47개 + 1 = 48행.
- VOC 행: `voc:total:count`(리뷰 수), `voc:judged:count`(건수, 표본 적음 기준(건)), `voc:unjudged:count`(건수, 판정 실패 건수), `voc:no_text:count`(건수), `voc:judged:mean_unweighted`(평균 평점), `voc:judged:mean_weighted`(가중 평균 평점, 가중치 하한), `voc:judged:count_weighted`(가중 건수), `voc:judged:dist_unweighted:{1..5}`(평점, 건수, 비율(%)), `voc:judged:dist_weighted:{1..5}`(평점, 가중 건수). 판정이 0건이면 평균 행은 빠진다. 17행. 합계 65행.
- `allowed_evidence_json` = `{row_id: {kind: "survey" | "review", ids: [정수 오름차순]}}`. 설문 행은 그 행에 들어간 `response_id`(응답 전체 단위, SQ-4b 기본안), VOC 행은 그 행에 들어간 `review_id`다. `voc:judged:*`는 판정 묶음, `voc:total:count`는 선택한 제품군·회차의 모든 리뷰, 미판정·제목·본문 없음 행은 각 묶음의 리뷰다. LLM에는 보내지 않는다(SP-3).

**hypothesis (불확실·모순 가설)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| hypothesis_id | 정수, 기본 키 | |
| snapshot_id, round_id, family_id | FK | |
| kind | 텍스트 | `uncertain`, `contradictory` CHECK |
| statement | 텍스트 | |
| related_row_ids | JSON | 스냅샷 표의 행 ID |

- 가설을 어떻게 가려내는지는 정해지지 않았습니다(prd.md Q-5, 확인 필요 SQ-4). 이 테이블은 가려낸 결과를 담는 자리일 뿐입니다. (결정 전 기록. Phase 6 결정은 아래)

**구현에서 정함 (Phase 6, 가설, 결정 2026-11-03, 사용자 승인)**
- 가설은 코드 규칙만으로 찾는다(FR-0.1). LLM은 가설을 찾는 데 관여하지 않는다. 입력은 스냅샷의 표(과 문항 유형)이고, 진술문은 코드가 템플릿으로 만들며 `related_row_ids`를 붙인다. 설문 행에 기반한 진술문에는 "합성", 표본 적음에 기반한 진술문에는 "표본"이 들어간다. 임계값은 모두 근거 없는 임시 가정이다(Q-7처럼 이 데이터로 검증하지 않았다).
  - R1 uncertain: 판정 묶음의 n이 `VOC_SMALL_SAMPLE_THRESHOLD`(30) 미만이다.
  - R2 uncertain: `single` 유형 문항에서 1위와 2위 선택지의 비율 차이가 5%p 이하다(`scale5`와 `multi`는 뺀다. 점수형은 인접 점수라 경쟁하는 선택지가 아니고, 복수응답은 비율의 합이 100%를 넘어 순위 비교가 맞지 않는다).
  - R3 contradictory: 전반 만족도 문항(q01)의 4·5점 비율 합이 60% 이상이고 추천 경험 문항(q09)의 "아니오" 비율이 50% 이상이다.
  - R4 contradictory: q01의 4·5점 비율 합(만족)이 60% 이상인데 VOC 판정 묶음의 비가중 평균 평점이 3.5 이하이거나, 만족이 50% 미만인데 평균 평점이 4.5 이상이다(판정이 1건 이상일 때만). 현재 데이터(제품군 2 x 회차 2)에서는 해당 없다.
- 한 스냅샷에서 가설은 최대 5개다. 우선순위는 contradictory(R3, R4) > uncertain R2(차이가 작은 순) > R1이다. 임계값(5%p, 60%, 50%, 3.5, 4.5, 5개)은 코드의 상수로 분리한다.
- 문항 유형은 표에 없어서 `survey_question`에서 읽는다(R2가 `single`만 보기 위해서).
- "이전 회차"는 선택한 제품군 x 회차의 스냅샷이다. 회차 간 비교는 하지 않는다. 화면에는 "다음 회차 설문지(초안)"만 쓰고 회차 이름은 쓰지 않는다.
- 가설이 0개면 `next-survey-draft` 실행은 `failed`(`error_code` `NO_HYPOTHESES`)다.
- `hypothesis`와 `next_survey_question`에 NULL 허용 `run_id`(FK -> `pipeline_run`)를 더한다(위 열 정의에 없던 변경이다). 초안을 다시 실행하면 쌓이고, 최신 초안은 해당 `report`에 속한 문항 중 가장 큰 `run_id`의 것이다.

**report (회차 리포트)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| report_id | 정수, 기본 키 | |
| round_id | FK → round | |
| family_id | FK → product_family, NULL 허용 | 리포트가 회차 전체인지 제품군별인지는 확인 필요 SQ-13 |
| run_id | FK → pipeline_run | |
| generated_at | 시각 | |

**action_suggestion / suggestion_evidence (액션 제안과 근거)**

| 테이블 | 열 | 비고 |
| --- | --- | --- |
| action_suggestion | suggestion_id(PK), report_id(FK), snapshot_id(FK), order_no, sentence, row_ids(JSON) | 근거가 없는 문장은 저장하지 않는다(FR-2.4). `row_ids`는 문장이 참조한 스냅샷 표의 행 |
| suggestion_evidence | suggestion_id(FK), evidence_kind, evidence_id | 기본 키는 세 열의 조합. evidence_kind는 `review`, `survey` CHECK. SP-3 승인으로 문장당 수백~천 건이 될 수 있어 저장할지, 스냅샷의 허용 목록에서 계산할지 정해야 한다(기본안은 계산, 확인 필요 SQ-17) |

- evidence_kind에 따라 가리키는 테이블이 달라 DB 외래 키로 묶을 수 없습니다. 존재 여부는 서비스 코드가 검사합니다(FR-2.4).
- 근거 ID의 형식은 `(종류, 정수 ID)` 쌍입니다. 설문 근거의 단위(응답 전체인지 문항별 응답인지)는 확인 필요 SQ-4입니다.

**구현에서 정함 (Phase 5, 리포트와 제안, 결정 2026-11-03, 사용자 승인)**
- `report`는 `action-suggestions` 실행이 성공할 때마다 1행을 만들고(`family_id` 포함, SQ-13 기본안 대신) 쌓는다. 화면은 제품군 x 회차의 가장 최근 성공한 리포트를 보여준다. 실패한 실행은 리포트를 만들지 않는다. Phase 6에서 회차 리포트로 합치는 방식은 그때 정한다.
- `action_suggestion`에 `(report_id, order_no)` 유일 제약을 두었다. 제안은 통과한 문장만 저장한다. `suggestion_evidence` 테이블은 만들지 않았다. 근거는 `row_ids`로 스냅샷의 `allowed_evidence_json`에서 계산한다(SQ-17 기본안).
- 마이그레이션 `fd2af39e3e2a`: `analysis_snapshot`, `report`, `action_suggestion`(PostgreSQL에서는 RLS를 켠다).

**next_survey_question (다음 회차 설문지 초안)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| question_id | 정수, 기본 키 | |
| report_id | FK → report | |
| hypothesis_id | FK → hypothesis | 문항이 어느 가설에서 나왔는지 |
| order_no | 정수 | |
| text | 텍스트 | |
| type | 텍스트 | 값은 확인 필요 SQ-5 |
| options_json | JSON, NULL 허용 | |
| status | 텍스트 | `draft`로 고정 CHECK (FR-3.3) |

**구현에서 정함 (Phase 6, 문항 열, 결정 2026-11-03, 사용자 승인)**: `type`은 `scale5` / `single` / `multi` 세 가지(CHECK)다. `options_json`은 `[{"code": "1", "label": "…"}, …]`이고 순서를 유지한다. `scale5`는 LLM이 `options`를 내지 않으며(null) 코드가 1~5(`code` "1"~"5", `label` "1점"~"5점")를 채운다. 열 `run_id`(NULL 허용, FK)를 더했다.

**pipeline_run (실행 기록)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| run_id | 정수, 기본 키 | |
| round_id, family_id | round_id는 FK, family_id는 NULL 허용 | 구현은 `family_id`를 FK 없는 정수로 둔다(`product_family` 테이블이 아직 없음) |
| step | 텍스트 | 5.2절의 단계 이름 |
| status | 텍스트 | `queued`, `running`, `succeeded`, `partial`, `failed` CHECK |
| counters | JSON | 처리 건수, 실패 건수, 제외된 제안 문장 수 등. `ad-judgement`는 `eligible`, `skipped`, `sent`, `ok`, `failed`, `not_run` |
| error_code | 텍스트, NULL 허용 | 비밀 값과 본문을 포함하지 않는다. 구현은 `error_message` 열을 두지 않는다(메시지에 본문이 섞이는 것을 막기 위함) |
| started_at, finished_at | 시각 | |

**llm_call_log (LLM 호출 기록)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| call_id | 정수, 기본 키 | |
| run_id | FK → pipeline_run | |
| call_type | 텍스트 | 호출 종류. 구현은 호출 A만 있어 `A`. 다른 호출은 해당 Phase에서 추가(이전 명세의 `purpose` 값 `ad_judgement` 등을 대체) |
| model_name, prompt_version | 텍스트 | |
| attempt_no | 정수 | |
| status | 텍스트 | `ok`, `invalid_output`, `api_error`. 시간 초과는 `api_error`이고 `error_code`가 `TIMEOUT` |
| item_count | 정수 | 한 호출에 넣은 항목 수 |
| input_tokens, output_tokens | 정수, NULL 허용 | 비용 점검용(NFR-C2, C3) |
| latency_ms | 정수 | |
| error_code | 텍스트, NULL 허용 | |
| created_at | 시각 | |

- 요청·응답 원문은 저장하지 않습니다(6.4절).

### 3.3 관계

```
product_family 1 ─ N product 1 ─ N review 1 ─ N ad_judgement
round 1 ─ N survey_question
round 1 ─ N survey_response 1 ─ N survey_answer N ─ 1 survey_question
round 1 ─ N analysis_snapshot 1 ─ N hypothesis
round 1 ─ N report 1 ─ N action_suggestion 1 ─ N suggestion_evidence ··> review | survey_response
report 1 ─ N next_survey_question N ─ 1 hypothesis
pipeline_run 1 ─ N ad_judgement | analysis_snapshot | report | llm_call_log
```

- `suggestion_evidence`의 점선(··>)은 DB 외래 키가 아니라 서비스 코드가 검사하는 관계입니다.
- 집계와 가중 합계는 테이블에 저장하지 않고 요청 때 코드가 계산합니다(FR-0.1). 분석 스냅샷만 LLM 입력과 검증용으로 저장합니다.

## 4. REST API 목록

모든 경로는 `/api`로 시작합니다. 응답은 JSON입니다(내보내기 제외). 로그인이 없으므로 인증 헤더는 없습니다(NFR-S1).

### 4.1 상태 코드 규칙

| 코드 | 쓰는 경우 |
| --- | --- |
| 200 | 조회 성공 |
| 201 | 실행 기록 생성 성공 (POST) |
| 400 | 형식은 맞지만 규칙에 맞지 않는 요청. 예: 지원하지 않는 내보내기 형식, 해당 제품군에 속하지 않는 회차 조합 |
| 404 | 요청한 제품군·회차·근거·리포트·실행이 없음 |
| 422 | 요청 형식 오류. 예: 경로·쿼리 값의 자료형이 틀림, 허용되지 않는 값 (FastAPI의 검증 오류) |
| 500 | 예상하지 못한 서버 오류, DB 연결 오류 |

### 4.2 화면용 API

| 번호 | 메서드 | 경로 | 요청 | 응답 | 상태 코드 | 요구사항 |
| --- | --- | --- | --- | --- | --- | --- |
| A-1 | GET | `/api/families` | 없음 | `families`: 제품군 목록 `{family_id, name}` (`family_id` 오름차순, 구현에서 정함. 시드 전에는 빈 목록) | 200, 500 | FR-1.1 |
| A-2 | GET | `/api/rounds` | 없음 | `rounds`: 회차 목록 `{round_id, label, period_start, period_end}`. label이 `[파일럿-임시]`로 시작하는 행은 목록에서 뺀다 (결정 2026-11-03, 사용자 승인) | 200, 500 | FR-1.3 |
| A-3 | GET | `/api/families/{family_id}/dashboard` | 쿼리 `round_id`(정수, 필수) | 대시보드 (아래) | 200, 400, 404, 422, 500 | FR-1.2~1.10 |
| A-4 | GET | `/api/evidence/{kind}/{evidence_id}` | 경로 `kind`(`review` 또는 `survey`), `evidence_id`(정수) | 근거 (아래) | 200, 404, 422, 500 | FR-2.2, FR-2.5 |
| A-5 | GET | `/api/reports` | 쿼리 `round_id`(선택), `family_id`(선택) | `reports`: `{report_id, round_id, family_id, generated_at}` 목록 | 200, 422, 500 | FR-3.1 |
| A-6 | GET | `/api/reports/{report_id}` | 없음 | 리포트 (아래) | 200, 404, 422, 500 | FR-3.1~3.4 |
| A-7 | GET | `/api/reports/{report_id}/export` | 쿼리 `format`(필수) | 독립형 HTML 파일 본문(기본안, 설계 제안). 근거는 문장마다 건수만 적는다(기본안). 형식은 확인 필요 SQ-14 | 200, 400, 404, 422, 500 | FR-3.5 |
| A-10 | GET | `/api/suggestions/{suggestion_id}/evidence` | 쿼리 `page`(정수, 기본 1), `page_size`(정수), `kind`(선택: `review` 또는 `survey`) | `{total, page, page_size, items: [{kind, evidence_id, rating, date}]}`. `rating`과 `date`는 리뷰 항목에만 있다. 정렬은 `evidence_id` 오름차순(설계 제안). 설문 항목의 필드는 확인 필요 SQ-5 | 200, 404, 422, 500 | FR-2.2, FR-2.6 |
| A-11(데모 전용, 부록 A 참조) | GET | `/api/demo/review-stats` | 없음 | `products`: 상품별 `{product_name, review_count, rating_distribution: [{rating, count}], with_text_count, with_text_ratio}`, `quarters`: 리뷰 달력 분기별 `{quarter, count}`, `total`. 응답에는 집계 숫자만 있고 리뷰 본문, 제목, `author`는 없다. 경로와 필드 이름은 설계 제안이며 구현 때 확정(확인 필요) | 200, 500 | plan.md 부록 A (본 설계의 FR이 아님) |

**A-3 응답 (대시보드)**

| 필드 | 설명 |
| --- | --- |
| `family` | `{family_id, name}` |
| `round` | `{round_id, label}` |
| `survey` | `{respondent_count, synthetic_label, scope, questions}`. `scope`는 설문이 제품군과 무관하면 `common`이다(기본안, 확인 필요 SQ-5). 설문 집계는 항상 비가중(FR-1.9). `synthetic_label`은 합성 응답일 때 `"합성"`(FR-1.10). `questions`는 `{question_id, text, type, results: [{option, count, ratio}]}` 목록 |
| `voc.unweighted` | 외부 VOC의 비가중 집계 `{count, mean_rating, rating_distribution: [{rating, count}]}`. 판정 묶음(광고성 판정에 성공한 글)만 대상이다(P-5, FR-1.11). 판정이 0건이면 `mean_rating`은 null이다 |
| `voc.weighted` | 외부 VOC의 가중 집계 `{count, mean_rating, rating_distribution}`. `unweighted`와 같은 글이 대상이고 `count`는 가중치의 합, `mean_rating`은 가중 평균, `rating_distribution`은 점수별 가중치의 합이다. 가중치 = max(`weight_floor`, 저장된 `ad_weight`) |
| `voc.weight_floor` | 계산에 쓴 하한 값(임시 0.1, 설정 `AD_WEIGHT_FLOOR`, prd.md Q-7) |
| `voc.counts` | `{total, judged, unjudged, no_text}`. `total = judged + unjudged + no_text`. 선택한 제품군 × 회차의 리뷰 수다 |
| `voc.unjudged` | `{count, failed_count, rating_distribution}`. **미판정**: 판정 대상(제목 또는 본문이 있는 글)이지만 성공한 판정이 없는 글. `failed_count`는 그중 판정이 실패한 글이다. 토글과 무관하게 항상 같은 값이다(P-5, FR-1.11) |
| `voc.no_text` | `{count, rating_distribution}`. **제목·본문 없음**: 제목과 본문이 모두 없는 글. 토글과 무관하게 항상 같은 값이다 |
| `voc.excluded` | `{count, other_round_count, outside_rounds_count}`. 선택한 제품군의 리뷰 중 선택한 회차에 포함되지 않은 글. `other_round_count`는 다른 회차에 속한 글, `outside_rounds_count`는 어느 회차에도 속하지 않는 글이다 |
| `voc.small_sample_threshold`, `voc.small_sample` | 표본 적음 임계값(코드 상수, 기본 30, 임시 가정)과 `judged < 임계값`인지 여부 |

**`voc.undetermined`를 바꾼 이유 (Phase 4, 결정 2026-11-03, 사용자 승인):** 이전 정의는 "제목·본문 없음"과 "판정 실패"를 `undetermined` 하나로 묶고 `count = no_text_count + failed_count`로 정했다. 그러나 FR-1.11(PQ-13 결정)은 화면을 판정 / 미판정 / 제목·본문 없음 세 묶음으로 보이고, 미판정에는 판정 실패뿐 아니라 판정하지 않은 글(표본 밖)이 들어가며 건수도 크게 다르다(예: 판정 대상 중 미판정이 대부분이다). 옛 구조로는 "판정하지 않은 글"을 둘 곳이 없고 "제목·본문 없음"의 평점 분포를 따로 낼 수 없어서 `voc.unjudged`와 `voc.no_text`로 나누었다.

- 가중 집계와 비가중 집계를 **항상 둘 다** 돌려줍니다(FR-1.8). 토글은 화면에서 어느 쪽을 보여줄지만 고르고, 서버에 토글 값을 보내지 않습니다.
- VOC 집계의 지표는 SQ-1에서 정했다(결정 2026-11-03, 사용자 승인): 건수, 평균 평점, 평점 분포. (결정 전 기록) VOC 집계에 어떤 지표를 담을지는 정해지지 않았습니다(확인 필요 SQ-1). 문서에 있는 것은 "가중/비가중 토글로 VOC 집계 결과가 바뀐다"는 확인 기준뿐입니다.
  - 후보는 리뷰 수, 평균 평점, 평점 분포입니다. 가중 쪽은 리뷰 수를 가중치의 합으로, 평균 평점을 가중 평균으로 바꾸는 방식이 자연스럽지만 문서에 적힌 것은 아니고 추론입니다.
  - 가중 집계를 어떤 지표로 보일지는 광고성 판정 파일럿(Phase 3) 결과와 함께 정합니다.
  - 평점 분포를 쓰면 표본이 적은 칸이 생깁니다. 1~2점은 전체 1,302건 중 22건, 본문이 있는 리뷰 297건 중 10건입니다(실측). 건수를 함께 표시하거나 칸을 묶는 규칙이 필요하며, 이 규칙도 정해지지 않았습니다.
- 가중 평균은 가중치와 평점의 곱을 합해 가중치의 합으로 나눈 값이고, 계산은 코드가 합니다(FR-0.1).
- 400은 `round_id`가 요청한 제품군과 맞지 않는 경우(데이터가 없는 조합)에 씁니다. 회차가 아예 없으면 404입니다.

**구현에서 정함 (Phase 4, voc 부분, 결정 2026-11-03, 사용자 승인)**
- 판정 읽기: 글마다 `status`가 `ok`인 판정 중 가장 최근(`judged_at`, 같으면 `judgement_id`가 큰 쪽) 1건만 쓴다. `round_id`로 거르지 않는다. 최신 실행이 실패해도 이전 성공 판정이 있으면 그것을 쓴다(SQ-8).
- 하한은 집계 시점에 적용한다: 가중치 = max(`AD_WEIGHT_FLOOR`, `ad_weight`). 저장된 `ad_weight`는 바꾸지 않는다. `AD_WEIGHT_FLOOR`의 기본은 0.1이고 0 이상 1 미만이어야 한다(벗어나면 서버가 시작하지 않는다).
- 서버는 소수 4자리로 반올림해서 주고, 화면은 소수 2자리로 보인다. 미판정과 제목·본문 없음은 가중치를 주지 않고 건수와 평점 분포만 낸다.
- 회차의 `period_start` 또는 `period_end`가 비어 있으면 그 회차에는 VOC가 속하지 않는다(건수 0).
- 설문 부분(`survey`)은 이 변경의 영향을 받지 않는다.

**구현에서 정함 (Phase 2, 설문 부분만, 결정 2026-11-03, 사용자 승인)**
- 응답은 `family`, `round`, `survey`만 담는다. `voc` 필드는 이번 응답에서 뺀다(Phase 4에서 채운다).
- `survey.respondent_count`는 해당 회차의 `survey_response` 행 수다. `synthetic_label`은 회차의 응답이 있고 모두 `is_synthetic`이 참이면 `"합성"`, 아니면(합성이 아닌 응답이 섞였거나 응답이 없으면) null이다. `scope`는 항상 `common`이다.
- `questions`는 `question_id` 순이다. 각 `results` 항목은 `{code, option, count, ratio}`이고 `code`는 선택지 코드(`survey_answer.value`와 같은 문자열), `option`은 선택지 라벨이다(`code`는 명세의 `{option, count, ratio}`에 더한 필드). 선택 수가 0인 선택지도 `options_json` 순서대로 `count` 0으로 포함한다.
- `ratio` = 선택 수 / `respondent_count`를 소수 4자리로 반올림한 값이다. 다중선택(`multi`)도 응답자 수로 나누므로 비율의 합이 1을 넘을 수 있다. 응답이 0건이면 0.0이다.
- 문항별 응답자 수(n)는 응답에 따로 담지 않고 화면이 `respondent_count`를 쓴다(모든 응답이 모든 문항에 답하는 합성 데이터 기준).
- 제품군은 존재 확인(없으면 404)에만 쓴다. 회차가 없거나 label이 `[파일럿-임시]`로 시작하는 임시 회차면 404다. 설문 쪽에서는 400을 내지 않는다. `round_id`가 없거나 정수가 아니면 422다.

**A-4 응답 (근거)**

| kind | 필드 | 비고 |
| --- | --- | --- |
| `review` | `kind`, `review_id`, `rating`, `date`, `review_text`, `text_source` | FR-2.5. `review_text`가 비어 있으면 `title` 값을 `review_text` 자리에 넣고 `text_source`를 `title`로 한다(`text_source`는 `review_text` 또는 `title`). 기본안이며 설계 제안이다(확인 필요 SQ-15). 그 밖의 `title`과 `author`, `variant`는 담지 않는다. **구현에서 정함 (Phase 1)**: 제목과 본문이 모두 없는 글은 200으로 `review_text`와 `text_source`를 null로 돌려준다. `kind=survey`는 Phase 1 범위 밖이라 400 `BAD_REQUEST`로 거절한다 |
| `survey` | `kind`, `response_id`, `synthetic_label`, `round`, `answers: [{question_text, value}]` | 합성 응답이면 `synthetic_label`이 `"합성"`. 필드는 설문 구조를 확인한 뒤 확정(확인 필요 SQ-5). **구현에서 정함 (Phase 5, 결정 2026-11-03, 사용자 승인)**: `answers`는 문항 순서대로이고 `value`는 선택지 라벨이다(코드가 아니다). 다중선택은 선택 하나당 한 항목이다. `round`는 `{round_id, label}`. 없는 응답은 404 |

**A-6 응답 (리포트)**

| 필드 | 설명 |
| --- | --- |
| `report_id`, `round`, `family`, `generated_at` | 기본 정보. `family`는 NULL일 수 있음(확인 필요 SQ-13) |
| `action_plan` | `{suggestion_id, order_no, sentence, evidence_count: {review, survey}}` 목록. 모든 문장이 근거를 하나 이상 가진다(FR-2.3, 2.4). 근거 목록은 문장당 수백~천 건이 될 수 있어 응답에 담지 않고 A-10으로 조회한다(SP-3) |
| `next_survey` | `{status: "draft", questions: [{order_no, text, type, options}]}`. `status`는 항상 `draft`(FR-3.3) |

**구현에서 정함 (Phase 5, 근거 목록과 액션플랜 API, 결정 2026-11-03, 사용자 승인)**
- A-10 `GET /api/suggestions/{suggestion_id}/evidence?page=&page_size=&kind=`: 근거 = 문장의 `row_ids`가 가리키는 행들의 허용 목록의 합집합(저장하지 않고 계산, SQ-17). `page` 기본 1(1 이상), `page_size` 기본 50, 상한 200(가정, 근거 없음)이며 벗어나면 422. 정렬은 종류(review, survey) 다음 `evidence_id` 오름차순. 필터는 `kind`만. 리뷰 항목은 `{kind, evidence_id, rating, date}`, 설문 항목은 `{kind, evidence_id, synthetic_label}`이다. 작성자·`variant`·제목·본문은 없다. 없는 제안은 404.
- 액션플랜 조회(A-6 대신 Phase 5용 가장 단순한 형태) `GET /api/families/{family_id}/action-plan?round_id=`: 제품군 x 회차의 가장 최근 성공한 리포트의 문장 목록 `{suggestion_id, order_no, sentence, evidence_count: {review, survey}, has_synthetic}`. `has_synthetic`은 설문(합성) 행을 근거로 하는 문장이면 참이다. 리포트가 없으면 200으로 `report`가 null이고 목록이 비어 있다. 제품군·회차가 없거나 임시 회차면 404, `round_id`가 없으면 422.

**구현에서 정함 (Phase 6, 리포트 API, 결정 2026-11-03, 사용자 승인)**
- A-5 `GET /api/reports?round_id=&family_id=`: 리포트 목록(`report_id` 내림차순). 항목은 `{report_id, round_id, family_id, generated_at}`에 `suggestion_count`, `question_count`를 더했다(화면이 문항이 있는 가장 최근 리포트를 고르기 위해).
- A-6 `GET /api/reports/{report_id}`: `{report_id, round, family, generated_at, action_plan, next_survey}`. `action_plan` 항목은 `{suggestion_id, order_no, sentence, evidence_count: {review, survey}, has_synthetic, sources}`다(`sources`는 근거 행의 출처 "합성"/"실측"). `next_survey`는 `{status: "draft", run_id, questions, no_question_hypotheses}`이고(`no_question_hypotheses`는 최신 초안 실행에서 저장됐지만 문항이 없는 가설 `{hypothesis_id, kind, statement, note}`이며 R1은 `note`가 "표본 적음 — 데이터 보강 필요(문항 없음)", 그 밖에 검증으로 문항이 빠진 가설은 "문항 없음(검증을 통과한 문항이 없음)"이다. 내보내기 HTML에도 "문항이 없는 가설"로 나온다) 문항은 `{order_no, text, type, options, hypothesis_id, hypothesis_kind, hypothesis_statement}`다. 문항은 해당 리포트의 가장 큰 `run_id`의 것만 담고, 초안이 없으면 문항 목록이 비어 있다.
- A-7 `GET /api/reports/{report_id}/export?format=html`: `format`이 없으면 422, `html`이 아니면 400 `UNSUPPORTED_FORMAT`, 리포트가 없으면 404. 응답은 `text/html` 독립형 한 파일이고 `Content-Disposition: attachment; filename="report-{id}.html"`이다. 생성한 HTML을 표준 라이브러리 HTML 파서로 검사해 외부 참조(URL 속성 `src`/`href` 등, `on*` 속성, `url()`·`@import`·`http(s)://`를 담은 속성이나 `<style>` 내용, script/link/iframe/img 등 태그)가 하나라도 나오면 내보내지 않고 500으로 처리한다. 본문 글은 이스케이프되어 있으므로 글 속의 `http://`나 `src=` 같은 문자열은 검사 대상이 아니다.

### 4.3 실행용 API (n8n이 호출, 설계 제안)

n8n은 "회차별 정기 실행과 단계 연결"을 맡습니다. 단계를 backend에서 하나씩 호출할 수 있도록 엔드포인트를 둡니다. 이 엔드포인트를 담당자 화면에서 호출하는지는 정해지지 않았습니다(prd.md Q-4, 확인 필요 SQ-8). 담당자 업로드나 데이터 수정 API는 없습니다(prd.md 7절).

| 번호 | 메서드 | 경로 | 요청 | 응답 | 상태 코드 |
| --- | --- | --- | --- | --- | --- |
| A-8 | POST | `/api/rounds/{round_id}/pipeline/{step}` | 경로 `step`, 본문 `{family_id?}` | `{run_id, step, status, started_at}` | 201, 400, 404, 422, 500 |
| A-9 | GET | `/api/runs/{run_id}` | 없음 | `{run_id, round_id, family_id, step, status, counters, error_code, started_at, finished_at}` | 200, 404, 422, 500 |

`step`의 값 (설계 제안, 이름과 개수는 확인 필요 SQ-8):

| step | 하는 일 | 관련 요구사항 |
| --- | --- | --- |
| `ad-judgement` | 외부 VOC의 광고성 확률과 가중치를 계산해 저장 | FR-1.4~1.7 |
| `analysis-snapshot` | 코드가 집계 표를 계산해 저장 | FR-0.1, 0.2 |
| `action-suggestions` | 스냅샷으로 액션 제안 문장을 서술하고 근거를 검사 | FR-0.2, 2.1~2.4 |
| `next-survey-draft` | 불확실·모순 가설로 다음 회차 문항 초안을 만듦 | FR-3.2, 3.3 |
| `report-assembly` | 액션플랜과 문항 초안을 하나의 리포트로 묶음 | FR-3.1, 3.4 |

- 단계는 시간이 오래 걸릴 수 있어(LLM 호출) POST는 실행 기록을 만들고 바로 201로 돌려주며, 진행은 A-9로 확인합니다. 백그라운드 실행 방식은 설계 제안입니다.
- 400은 `step`이 목록에 없거나 선행 단계가 끝나지 않았을 때 씁니다.
- 구현 현황(Phase 3): `ad-judgement`만 있고 경로가 `/api/rounds/{round_id}/pipeline/ad-judgement`로 고정입니다(다른 step과 400은 아직 없음). 서버가 요청 안에서 끝까지 실행한 뒤 201을 돌려줍니다(백그라운드 실행 아님). 본문은 `{family_id?, review_ids}`이고 `review_ids`는 필수입니다. 비었거나 없거나, 존재하지 않는 번호가 있거나, 한 번에 보낼 상한(`AD_JUDGEMENT_MAX_ITEMS`, 기본 100건, 설계 제안)을 넘으면 422(`TOO_MANY_REVIEWS`, `UNKNOWN_REVIEW_IDS`)로 거절하고 아무것도 보내지 않습니다. 모델 이름이나 OpenAI 키가 없으면 500(`MODEL_NOT_CONFIGURED`, `LLM_NOT_CONFIGURED`)입니다. 오류 본문은 `detail={code, message}`이고 7.1절의 통일 형식은 Phase 1에서 만듭니다.
- **구현에서 정함 (Phase 5, 단계 API, 결정 2026-11-03, 사용자 승인)**: `POST /api/rounds/{round_id}/pipeline/{step}`를 일반화했다. 기존 `ad-judgement` 경로는 그대로 유지한다(본문 `review_ids`). `analysis-snapshot`과 `action-suggestions`의 본문은 `{"family_id": 정수}`이며 필수다(스냅샷이 제품군 x 회차 단위라서 A-8의 `family_id?` 선택 규정 대신 이 두 단계에서는 필수). 목록에 없는 step은 400 `BAD_REQUEST`, 목록에 있지만 아직 구현되지 않은 step(`next-survey-draft`, `report-assembly`)도 400 `BAD_REQUEST`다. 회차·제품군이 없거나 임시 회차면 404. `action-suggestions`는 해당 제품군 x 회차의 스냅샷이 없으면 400 `STEP_NOT_READY`다. 서버가 요청 안에서 끝까지 실행한 뒤 201을 돌려준다.
- **구현에서 정함 (Phase 6, 단계 API, 결정 2026-11-03, 사용자 승인)**: `next-survey-draft`는 본문 `{"family_id": 정수}`가 필수이고, 해당 제품군 x 회차의 스냅샷과, 성공한 `action-suggestions`로 만들어진 가장 최근 `report`가 없으면 400 `STEP_NOT_READY`다. 가설이 0개면 실행은 `failed`(`NO_HYPOTHESES`)이고 LLM을 부르지 않는다. 초안은 해당 `report`에 붙고 `run_id`로 구분한다. `report-assembly`도 `family_id`가 필수이며 가장 최근 리포트에 제안과 문항이 모두 1개 이상이어야 하고, 아니면 400 `STEP_NOT_READY`다. 이 단계는 실행 기록만 남기고 새 데이터를 만들지 않는다.
- 같은 단계를 다시 실행할 때 이전 결과를 어떻게 처리할지는 정해지지 않았습니다(확인 필요 SQ-8). 기본안(설계 제안)은 쌓는 것입니다: 실행마다 새 결과를 만들고 이전 결과를 지우지 않습니다. 읽기 규칙은 글마다 가장 최근의 성공한 판정을 쓴다. 최신 실행이 실패해도 이전 성공 판정이 있으면 그것을 쓴다. 실행을 합쳐서 읽는다(run 1과 run 2). (결정 2026-11-03, 사용자 승인)

## 5. 화면별 구성과 사용하는 API

화면을 이렇게 나눌지는 정해지지 않았습니다(prd.md Q-9). 아래는 prd.md의 S-1~S-4를 따른 구성입니다.

| 화면 | 구성 | 사용하는 API |
| --- | --- | --- |
| S-1 제품군 선택 | 제품군 목록. 별도 화면 또는 대시보드 안의 영역은 확인 필요 Q-9 | A-1 |
| S-2 제품군 대시보드 | 상단: 제품군, 회차 선택. 설문 집계 영역(합성 라벨 포함, 설문이 제품군과 무관하다는 표시는 기본안). 외부 VOC 집계 영역. 가중/비가중 토글(판정에 성공한 VOC에만 적용). VOC 영역 안의 "미판정"과 "제목·본문 없음" 섹션: 건수와 평점 분포, 토글과 무관(P-5, FR-1.11, PQ-13) | A-2, A-3 |
| S-3 근거 뷰어 | 근거 하나를 보여준다. 리뷰는 review_id, 평점, 날짜, 본문만(본문이 없으면 제목, 기본안). 합성 응답은 "합성" 라벨 | A-4 |
| S-4 회차 리포트 | 액션플랜(문장마다 근거 건수와 근거 목록 링크, 목록은 페이지 단위), 다음 회차 설문지(초안 표시), 내보내기 버튼 | A-5, A-6, A-7, A-10, A-4 |

**화면 동작 규칙**
- 가중/비가중 토글은 화면 안에서만 바뀐다. 서버를 다시 부르지 않는다(A-3이 둘 다 준다).
- 설문 집계 영역은 토글의 영향을 받지 않고, 비가중이라는 표시를 둔다(FR-1.9).
- 문장의 근거 건수를 누르면 근거 목록이 열리고(A-10, 페이지 단위), 목록의 항목을 누르면 S-3이 A-4를 호출한다. 근거를 찾을 수 없으면(404) "근거를 찾을 수 없음"을 보여준다.
- 라우팅은 React Router를 쓴다(결정). 라우팅 주소, 상태 관리, 차트 라이브러리는 확인 필요 SQ-10. **(구현에서 정함, Phase 2, 결정 2026-11-03, 사용자 승인) 현재 `frontend`에는 React Router가 설치되어 있지 않다(문서의 결정과 설치 상태가 어긋나 있었다). Phase 2는 단일 화면이라 라우터와 차트 라이브러리를 쓰지 않고, 제품군 대시보드와 포트폴리오 데모를 `App.jsx`의 탭 상태로 오간다. 여러 화면이 필요해지는 Phase(근거 뷰어, 리포트)에서 라우터를 설치할지 다시 정한다.**

## 6. LLM 호출 명세

### 6.1 공통

| 항목 | 내용 |
| --- | --- |
| 서비스 | OpenAI API. 호출은 backend의 `llm/client`만 한다. 프런트엔드와 n8n은 LLM을 직접 부르지 않는다 (설계 제안) |
| 키 | `backend/.env`에서만 읽는다. 로그와 응답에 넣지 않는다 |
| 모델 | 광고성 판정(호출 A)은 `gpt-5.6-luna`(prd.md Q-12, 2026-11-02, 환경 값 `OPENAI_MODEL_AD`). 문항 초안·액션 제안 서술 호출의 모델은 정해지지 않음 (확인 필요 SQ-9). 기본안(설계 제안): 모델 이름을 코드에 박지 않고 호출 종류별(광고성 판정, 액션 제안 서술, 문항 초안) 환경 값으로 둔다. 같은 모델을 쓸지 다르게 쓸지는 나중에 정하고, 호출마다 모델 이름을 `ad_judgement.model_name`과 `llm_call_log.model_name`에 남겨 모델별로 반복 실행 일치율(NFR-R1)을 비교할 수 있게 한다 |
| 입력 제한 | `author`와 `variant`는 어떤 호출에도 넣지 않는다(NFR-S2). 필요한 열만 허용 목록으로 골라 보낸다 |
| 출력 | JSON만 받는다. 출력 스키마를 호출에 지정하는 방식(구조화 출력)은 시험 호출(2026-11-02, 영어 가짜 문장 1건)에서 엄격한 JSON 스키마 응답이 동작함. 10건 묶음과 한국어 입력은 미확인(확인 필요 SQ-9) |
| 무작위성 | 반복 실행 일치율(NFR-R1)을 위해 낮게 둔다. 값은 확인 필요 SQ-9 |
| 원칙 | LLM은 수치를 만들거나 바꾸지 않는다. 가중치 계산과 집계는 코드가 한다(FR-0.1, 0.2, 0.4) |
| 비용 가드 | 실행당 한도 $0.5(환경 값 `AD_JUDGEMENT_COST_LIMIT_USD`). 호출 전: 글자 수(제목+본문, 길이만 읽음)로 입력·출력 토큰 상한을 계산해 (입력 비용 + 출력 비용) × 재시도 배수 3이 한도를 넘으면 422 `COST_LIMIT_EXCEEDED`로 중단하고 실행 기록을 만들지 않는다. 단가(`OPENAI_PRICE_INPUT_PER_M`, `OPENAI_PRICE_OUTPUT_PER_M`)가 없으면 호출 없이 500 `PRICE_NOT_CONFIGURED`. 실행 중: 호출이 돌려준 실제 토큰으로 누적해 한도를 넘으면 남은 묶음과 재요청을 보내지 않고 `partial`/`COST_LIMIT`으로 끝낸다. 계수는 `app/llm/cost.py`의 `CALIBRATION` 한 곳이고 처음에는 시험 호출 2회로 보정했고, 2026-11-02 파일럿 10개 묶음(각 10건)의 실측으로 다시 보정했다: 고정 입력 470(이전 611에서 임시 여유 300을 뺀 값), 항목 오버헤드 30(가정), 글자당 토큰 0.80(유지), 출력 호출당 20 / 항목당 50(이전 40), 재시도 배수 3(유지). 근거: 파일럿 10개 묶음의 입력 토큰 = 714 + 0.623 × 글자 수(R² 0.9988, 최대 잔차 54토큰). 한계: 모든 묶음이 10건이라 고정 입력과 항목 오버헤드를 분리하지 못했다(절편 714 = 고정 + 10 × 오버헤드). 470은 오버헤드 30을 가정해 뺀 414에 여유 56을 더한 값이다. 표본이 한 프롬프트 버전(ad-v2)의 100건이다. 일시 오류 재시도는 청구되지 않는다고 가정한다(가정). 호출 전 추정은 가장 긴 글을 모든 항목에 적용한 상한이라 실제 비용보다 크다 |
| 기록 | 호출마다 llm_call_log에 모델, 프롬프트 버전, 시도 횟수, 상태, 토큰 수, 지연 시간만 남긴다. 입력·출력 원문은 남기지 않는다 |
| 프롬프트 | `backend/app/llm/prompts/`에 두고 버전을 붙인다 |

### 6.2 호출 3종

**호출 A: 광고성 판정 (FR-1.4)**

입력 (항목마다):

| 필드 | 형식 | 비고 |
| --- | --- | --- |
| `review_id` | 정수 | |
| `title` | 문자열 또는 null | |
| `review_text` | 문자열 또는 null | `title`과 `review_text` 중 하나 이상 값이 있는 리뷰만 판정 대상이다(310건, 실측). 제목만 있는 13건(310 − 297, 실측)도 포함한다. 둘 다 없는 992건(실측)은 LLM에 보내지 않는다 |

출력 스키마:

| 필드 | 형식 | 제약 |
| --- | --- | --- |
| `results` | 배열 | 길이가 입력 항목 수와 같다 |
| `results[].review_id` | 정수 | 입력에 있는 값이며 중복이 없다 |
| `results[].ad_probability` | 숫자 | 0 이상 1 이하 |

- 위 세 항목만 보냅니다. 작성자(`author`), 옵션(`variant`), 상품명, 평점, 날짜는 보내지 않습니다(NFR-S2, 6.1 입력 제한). 구현은 `llm/prompts/ad_judgement.py`의 허용 키 목록으로 이를 지킵니다.
- 파일럿은 규칙 신호(`rule_signals`) 없이 LLM 단독으로 판정합니다(SQ-3 결정 A, 2026-11-02). 규칙 신호를 넘길지는 골든셋 결과를 본 뒤 정합니다. 지금 구현은 넘기지 않습니다.
- 한 호출에 몇 건을 넣을지는 확인 필요 SQ-9입니다.
- 한 실행에서 LLM에 보내는 글 수에는 상한을 둡니다. 기본 100건(파일럿, 가정)이며 환경 값으로 바꿉니다. 이름이 든 본문은 보내지 않습니다. 판정 대상 310건 전체 실행은 prd.md Q-17-3이 해결된 뒤에만 상한을 올려서 합니다 (설계 제안, plan.md Phase 3).
- 코드가 `ad_probability`로 가중치(1 − 확률, 하한 적용)를 계산합니다. 하한은 임시 0.1로 둡니다(2026-11-02). 근거는 약합니다(prd.md Q-7).
- 파일럿에서는 LLM이 낸 확률이 곧 광고성 확률입니다. 규칙과의 결합은 골든셋 결과를 본 뒤 정합니다(SQ-3).

**호출 B: 액션 제안 서술 (FR-0.2, FR-2.1)**

입력:

| 필드 | 형식 | 비고 |
| --- | --- | --- |
| `family`, `round` | 문자열 | 이름만 |
| `table` | 배열 | 분석 스냅샷의 표. 행마다 `row_id`, 지표 이름, 지표 값(코드가 계산). 근거 ID 목록은 LLM에 보내지 않는다(SP-3) |

출력 스키마:

| 필드 | 형식 | 제약 |
| --- | --- | --- |
| `suggestions` | 배열 | |
| `suggestions[].sentence` | 문자열 | 한국어 한 문장. 길이 상한은 확인 필요 SQ-9 |
| `suggestions[].row_ids` | 문자열 배열 | 입력 표에 있는 `row_id`만. 하나 이상 |

- LLM은 근거 ID를 출력하지 않습니다. 코드가 `row_ids`에 해당하는 행들의 허용 목록을 합쳐 문장의 근거로 붙입니다(SP-3, FR-2.6).

**구현에서 정함 (Phase 5, 호출 B, 결정 2026-11-03, 사용자 승인)**
- 모델은 환경 값 `OPENAI_MODEL_SUGGEST`에서만 읽는다(없으면 500 `MODEL_NOT_CONFIGURED`). 프롬프트 버전은 `suggest-v3`(v1→v2: 한글 수량 표현 금지, v2→v3: 숫자 뒤 변화 표현과 표에 없는 인과 연결 금지, 결정 2026-11-03, 사용자 승인)이고 `app/llm/prompts/suggestion.py`의 고정 문구 지문을 테스트가 고정한다. 단가는 호출 A의 `OPENAI_PRICE_*`를 재사용한다.
- 입력은 스냅샷의 표(행마다 `row_id`, `group`, `source`, `item`, `metrics`, `small_sample`)와 제품군·회차 이름뿐이다. 근거 ID, 리뷰 본문, 작성자는 보내지 않는다. 문장은 한국어 한 문장 120자 이내, 한 호출에서 최대 5문장이다.
- 문장별 검증(`app/llm/suggestion_validators.py`): (a) `row_ids`가 비었거나 표에 없는 값이 있거나 행들의 근거 합집합이 비면 `dropped_no_evidence`. (b) 길이 초과, 한 문장이 아님, 중복, 5문장 초과, 설문(합성) 행을 참조했는데 문장에 "합성"이 없음, 판정 묶음의 `small_sample` 행을 참조했는데 문장에 "표본"이 없음은 `dropped_other`. (c) 문장 속 아라비아 숫자가 참조한 행의 지표 값과 일치하지 않거나 한글 수량 표현(절반, 반절, 과반, 곱절, 몇 배, 고유어 수·한자어 수 + 건/명/점/개/배/문항/가지/퍼센트)이 있으면 `dropped_number_mismatch`. 표현 목록은 사용자가 정했고(2026-11-03) 문항·선택지 라벨 속 글자는 뺀다. "대부분", "소수" 같은 질적 표현은 막지 않는다. 지시어 "이"(이 점) 같은 정상 문장이 제외될 수 있는 것이 알려진 한계다. (d) suggest-v3: 숫자 바로 뒤(단위 %·건·명·점·개·배·포인트 허용)에 개선|증가|감소|확대|축소|향상|상승|하락|인상|인하가 오는 문장(비율을 달성 목표나 변화 폭으로 읽게 하고 표에 없는 비교를 만든다), 그리고 므로(이므로·했으므로 포함)|때문에|따라서|그래서|덕분에가 들어 있는 문장(표에 없는 인과 단정)은 `dropped_other`. 라벨 속 글자는 뺀다. `므로`는 사용자 목록의 "이므로"에 더해 같은 인과 연결(했으므로 등)을 막으려고 넓힌 것이다.
- 숫자 일치 규칙: 문장의 숫자를 모두 뽑아 참조한 행의 지표 값과 비교한다. 쓴 소수 자리(0~2)로 반올림한 값이 같으면 통과한다(예: 비율 28.4는 28, 28.4, 28.40 통과, 29와 28.5는 실패). 문항·선택지 라벨, 회차·제품군 이름, 문항 코드(q09 등) 속 숫자는 비교에서 뺀다. 설문 선택지 행의 `선택지 번호`와 평점 행의 `평점`도 지표 값이라 "5점" 같은 표현이 통과한다.
- 재시도: 일시 오류는 대기 1, 2, 4초로 최대 3회 다시 보낸다. 통과한 문장이 0개이거나 JSON·스키마가 깨지면 전체를 최대 2회 다시 요청한다(총 3번 요청). 통과한 문장이 하나도 없으면 실행은 `failed`(`error_code` `NO_SUGGESTIONS` 또는 `INVALID_OUTPUT`)이고 리포트를 만들지 않는다. 누적 비용이 한도를 넘으면 더 요청하지 않는다(`COST_LIMIT`).
- 실행 기록 `counters`: `proposed`, `accepted`, `dropped_no_evidence`, `dropped_number_mismatch`, `dropped_other`(마지막으로 검증한 시도의 건수), `attempts`(전체 요청 횟수), `llm_calls`(일시 오류 재시도를 포함한 호출 수). `llm_call_log`의 `call_type`은 `B`다.
- 비용 가드: 호출 전에 실제 프롬프트 글자 수로 (입력 + 출력 비용) x 재시도 배수 3을 계산해 실행당 한도(`SUGGESTION_COST_LIMIT_USD`, 기본 $0.5, 임시, NFR-C2)를 넘으면 422 `COST_LIMIT_EXCEEDED`로 호출하지 않는다. 계수(글자당 0.80토큰, 출력 문장당 120자 x 1.0 + 40토큰, 고정 20토큰)는 모두 가정이며 호출 B를 실제로 불러 본 적이 없어 실측으로 보정하지 않았다(`app/llm/cost.py` `SuggestionCalibration`).

**호출 C: 다음 회차 문항 초안 (FR-3.2)**

입력:

| 필드 | 형식 | 비고 |
| --- | --- | --- |
| `hypotheses` | 배열 | `{hypothesis_id, kind, statement}`. 가설은 코드가 가려낸 결과(확인 필요 SQ-4) |
| `previous_questions` | 배열 | 같은 질문을 되풀이하지 않기 위한 이전 회차 문항. 넣을지는 확인 필요 SQ-9 |

출력 스키마:

| 필드 | 형식 | 제약 |
| --- | --- | --- |
| `questions` | 배열 | |
| `questions[].hypothesis_id` | 정수 | 입력에 있는 값 |
| `questions[].text` | 문자열 | 비어 있지 않음 |
| `questions[].type` | 문자열 | 허용 값은 설문 구조를 확인한 뒤 확정(확인 필요 SQ-5) |
| `questions[].options` | 문자열 배열 또는 null | 선택형 문항일 때만 값이 있다 |

**구현에서 정함 (Phase 6, 호출 C, 결정 2026-11-03, 사용자 승인)**
- 모델은 환경 값 `OPENAI_MODEL_QUESTION`에서만 읽는다(없으면 500 `MODEL_NOT_CONFIGURED`). 단가는 호출 A·B와 같은 `OPENAI_PRICE_*`를 쓴다. 프롬프트 버전은 `question-v2`(v1 -> v2: 아래 "문항 품질 규칙")이고 지문 테스트를 붙인다. 실행당 비용 한도는 $0.5(임시, `QUESTION_COST_LIMIT_USD`). 재시도 정책은 호출 B와 같다(일시 오류 대기 1·2·4초 최대 3회, 통과 문항 0개 또는 스키마 오류면 전체 최대 2회 재요청).
- 입력은 가설 목록 `{hypothesis_id, kind, statement}`뿐이다. 진술문은 집계된 수치로 코드가 만든 문장이고 리뷰 본문, 작성자, 근거 ID는 넣지 않는다. `previous_questions`는 입력하지 않는다.
- 출력의 `type`은 `scale5` / `single` / `multi`. `single`·`multi`는 `options` 2~6개(문자열), `scale5`는 `options` null이다. 문항 `text`는 비어 있지 않고 100자 이내(가정)다.
- 문항별 검증과 제외 사유: `hypothesis_id`가 입력에 없거나 같은 가설에 문항이 둘 이상이면 제외(첫 문항만 쓴다), `type`이나 `options` 형식이 틀리면 제외, 길이 초과·빈 문항이면 제외, 문항과 선택지에 아라비아 숫자나 한글 수량 표현이 있으면 제외한다("새 수치 없음"). 코드가 채우는 `scale5`의 1~5는 예외다.
- **문항 품질 규칙 (결정 2026-11-03, 사용자 승인)**: (1) R1(표본 적음) 가설은 `hypothesis`에는 저장하되 호출 C 입력에서 제외한다. 이유: 응답자가 답할 수 없는 데이터 부족 사안이다. 가설당 문항 1개 규칙은 문항 대상 가설(R1 제외)에만 적용하고, 문항 대상 가설이 0개이면 LLM을 부르지 않고 `failed`(`NO_HYPOTHESES`)다(R1만 있어도 R1은 저장된다). `counters`에 `question_hypotheses`(문항 대상 수)를 더했고 `llm_call_log.item_count`는 문항 대상 수다. (2) `question-v2` 프롬프트 규칙: 응답자 본인의 경험·의향·행동만 묻는다, 수집된 데이터·표본·VOC·분석 결과·가설을 응답자에게 언급하지 않는다, 응답 결과가 서로 어긋났다고 전제하는 표현을 쓰지 않는다. (3) 코드 검증: 문항·선택지에 `표본|VOC|수집된|판정|합성|가설`이 있으면 제외한다(사유 코드 `meta_word`, 범주 카운터 `dropped_meta`). `VOC`는 영문자 사이에 낀 경우(vocal 등)를 뺀다. 정상 단어에 이 글자가 들어 있으면(예: "가설치") 제외될 수 있는 것이 알려진 한계다.
- **알려진 한계 (결정 2026-11-03, 사용자 승인)**: 숫자 금지 규칙 때문에 R2 후속 문항의 보기는 원문항의 구간 보기와 비교할 수 없다(예: 원문항 q10의 "월 1회 미만", "월 1~3회" 같은 구간을 후속 문항 보기에 그대로 쓸 수 없고 "가끔", "자주" 같은 질적 표현이 된다). 이번에는 고치지 않는다.

### 6.3 검증과 재시도

LLM 출력은 아래 순서로 코드가 검증합니다. 통과하지 못한 항목은 서술이나 판정으로 쓰지 않습니다.

| 호출 | 검증 |
| --- | --- |
| 공통 | (1) JSON으로 읽힌다 (2) 스키마와 맞다: 필수 필드, 자료형, 허용하지 않는 추가 필드 없음 |
| A | (3) `results` 길이가 입력과 같다 (4) `review_id`가 입력에 있고 중복이 없다 (5) `ad_probability`가 0 이상 1 이하의 유한한 수다 |
| B | (3) `row_ids`가 입력 표에 있고 하나 이상이다 (4) 문장 속 숫자가 참조한 행의 값과 일치한다(FR-0.3). 숫자를 비교하는 표기·반올림 규칙은 확인 필요 SQ-9 (5) 코드가 `row_ids`에 해당하는 행들의 허용 목록 합집합을 문장의 근거로 붙이고(SP-3), 합집합이 비어 있으면 재시도하지 않고 코드가 리포트에서 뺀다(FR-2.4) |
| C | (3) `hypothesis_id`가 입력에 있다 (4) 선택형 문항에만 `options`가 있다 (5) 문항에 새 수치가 없다 (6) 가설마다 문항이 몇 개 나와야 하는지는 확인 필요 SQ-9 |

**재시도**

| 실패 종류 | 처리 | 횟수 |
| --- | --- | --- |
| 네트워크 오류, 시간 초과, 429, 5xx | 대기 시간을 늘려 가며 같은 요청을 다시 보낸다 | 최대 3회 (가정) |
| 출력 검증 실패 | 실패한 항목만 같은 프롬프트로 다시 요청한다(오류 내용은 프롬프트에 넣지 않는다. 구현과 같음. 파일럿에서 검증 실패율을 보고 필요하면 알려 주는 방식으로 바꾼다) | 최대 2회 (가정) |
| 재시도 후에도 실패 | 그 항목은 `failed`로 기록하고 값을 지어내지 않는다. 실행 기록은 `partial`(일부 성공) 또는 `failed`(전부 실패) | |

- 재시도 횟수와 대기 시간은 가정이며 확인 필요 SQ-9입니다.
- 광고성 판정이 실패한 글은 가중치가 없습니다. 판정에 실패한 글과 파일럿에서 판정하지 않은 글은 "미판정", 판정 대상이 아닌 992건은 "제목·본문 없음"으로, 집계에서는 토글과 무관하게 건수와 평점 분포만 따로 표시합니다(prd.md 9절 P-5 승인, FR-1.11, PQ-13).
- 근거 ID 검사로 문장을 뺀 뒤 제안이 거의 남지 않을 때의 처리는 정해지지 않았습니다(prd.md Q-16).

## 7. 오류 처리와 로그

### 7.1 오류 응답 형식

모든 오류 응답은 같은 형태입니다.

| 필드 | 설명 |
| --- | --- |
| `error.code` | 기계가 읽는 코드 |
| `error.message` | 사람이 읽는 짧은 설명(한국어). 내부 정보를 담지 않는다 |
| `error.details` | 422일 때 어떤 필드가 왜 틀렸는지. 그 밖에는 생략 |
| `error.request_id` | 요청 하나를 가리키는 ID. 로그와 연결된다 |

| 상태 코드 | `error.code` 예 | 원인 |
| --- | --- | --- |
| 400 | `BAD_REQUEST`, `UNSUPPORTED_FORMAT`, `STEP_NOT_READY` | 규칙에 맞지 않는 요청 |
| 404 | `NOT_FOUND` | 대상 없음 |
| 422 | `VALIDATION_ERROR` | 요청 형식 오류 |
| 500 | `INTERNAL_ERROR` | 예상하지 못한 오류, DB 오류 |

- 500 응답에는 스택 추적이나 DB 문장을 담지 않습니다. 자세한 내용은 로그에만 남깁니다.
- LLM 실패는 HTTP 오류가 아니라 실행 기록(A-9)의 `status`와 `error_code`로 알립니다.

**구현에서 정함 (Phase 1, 2026-11-03)** — 위 표와 7.3에 정해지지 않았던 부분을 가장 보수적으로 정했다.
- `request_id`는 서버가 요청마다 `uuid4` 16진수 32자로 새로 만든다. 요청 헤더로 들어온 값은 쓰지 않는다. 응답 헤더 `X-Request-ID`와 오류 본문 `error.request_id`가 같은 값이다(오류가 아닌 응답에도 헤더가 붙는다).
- `error.details`는 422일 때 `[{field, reason}]`이다. `field`는 위치(예: `path.evidence_id`), `reason`은 FastAPI 검증 메시지이고 입력 값은 담지 않는다.
- 표에 없는 405는 `METHOD_NOT_ALLOWED`로 낸다. 업무 규칙 오류의 `error.code`는 서비스가 정한 코드를 그대로 쓴다(예: 판정 실행의 `TOO_MANY_REVIEWS`, `COST_LIMIT_EXCEEDED`). 그래서 `error.code`가 위 표의 예 밖일 수 있다.
- 기존 판정 실행 API(`POST /api/rounds/{round_id}/pipeline/ad-judgement`, `GET /api/runs/{run_id}`)도 같은 형식으로 바뀌었다. 이전에는 `{"detail": {code, message}}`였다.
- 로그 파일은 `backend/logs/app.log`이고 자정마다 나누어 7일 보관한다(SQ-16 기본안을 그대로 쓴 것이며 결정이 아니다). 요청마다 `event: request` 한 줄(`method`, `path`, `status`, `duration_ms`)을 남기고 쿼리 문자열과 본문은 남기지 않는다. 처리되지 않은 예외는 `event: unhandled_error`로 예외 종류(`error_type`)와 위치(`location`: 파일·줄·함수)만 남기고 예외 메시지는 남기지 않는다(메시지에 SQL이나 접속 정보가 들어갈 수 있음).

### 7.2 처리 위치

| 위치 | 처리 |
| --- | --- |
| 요청 형식 | FastAPI가 자료형을 검증하고 422를 낸다 |
| 업무 규칙 | 서비스 계층이 400, 404를 낸다 |
| 예상 밖 오류 | 전역 오류 처리기가 잡아 500과 `INTERNAL_ERROR`로 바꾸고 로그를 남긴다 |
| 실행 단계 | 단계별로 실패를 실행 기록에 쓰고, 한 항목의 실패가 다른 항목을 멈추지 않게 한다 |
| 프런트엔드 | 404는 해당 화면의 안내 문구로, 422·500은 일반 안내 문구와 `request_id`로 보여준다 |

### 7.3 로그

| 항목 | 내용 |
| --- | --- |
| 형식 | 한 줄에 JSON 하나 |
| 위치 | 표준 출력과 `backend/logs/`(저장소에 올리지 않음). 보존 기간과 회전 방식은 정해지지 않았다(확인 필요 SQ-16). 기본안(설계 제안): 일 단위로 파일을 나누고 7일(가정, 근거 없음) 보관한다 |
| 공통 필드 | `timestamp`, `level`, `request_id`, `event`, `duration_ms` |
| 실행 단계 필드 | `run_id`, `step`, `status`, 처리·실패 건수, `error_code` |
| 수준 | 정상 흐름은 INFO, 재시도는 WARNING, 실패는 ERROR |

### 7.4 로그에 남기지 않는 것

- `OPENAI_API_KEY`, `DATABASE_URL`, 그 밖의 비밀 값 (NFR-K1)
- 리뷰의 `title`, `review_text`, `author`, 설문 응답 값 (NFR-S2, NFR-S4)
- LLM 요청과 응답의 원문. 필요하면 해시나 길이만 남긴다 (설계 제안)

### 7.5 n8n 쪽 실패

- backend가 2xx가 아닌 응답을 주거나 실행 기록이 `failed`면 n8n 워크플로는 실패로 끝난다.
- 실패했을 때 알림을 보낼지, n8n이 자동으로 재시도할지는 정해지지 않았다 (확인 필요 SQ-8). 기본안(설계 제안): 알림은 prd.md에 없는 기능이라 두지 않고, 실패는 실행 기록(A-9)과 로그로 확인한다. n8n은 자체 재시도를 하지 않고, 재시도는 단계 안의 LLM 호출 재시도(6.3절)만 쓴다.

## 8. prd.md 요구사항과의 대응

| 요구사항 | 이 명세에서 다루는 곳 |
| --- | --- |
| FR-0.1~0.4 | 6.1(원칙), 6.2 호출 A·B, 6.3 |
| FR-1.1 | A-1, S-1 |
| FR-1.2, 1.3 | A-2, A-3, S-2 |
| FR-1.4~1.7 | 호출 A, ad_judgement 테이블, step `ad-judgement` |
| FR-1.8, 1.9 | A-3 응답의 `voc.weighted`, `voc.unweighted`, `survey` |
| FR-1.10, DR-2, NFR-S3 | `survey_response.is_synthetic`, A-3·A-4의 `synthetic_label` |
| FR-1.11 (P-5) | A-3 응답의 `voc.undetermined`, `ad_judgement.status`, S-2의 "미판정"·"제목·본문 없음" 섹션 |
| FR-2.1~2.4, FR-2.6 | action_suggestion, suggestion_evidence, 호출 B, 6.3, A-10 |
| FR-2.5, NFR-S2 | A-4 응답, 6.1 입력 제한 |
| FR-3.1~3.4 | A-6, next_survey_question, 호출 C |
| FR-3.5 | A-7 |
| FR-3.6 | 4.3 (n8n 호출 구조, 실행 방식은 미정) |
| DR-1 | `scripts/` 적재 스크립트 |
| DR-3, DR-4, DR-5 | ad_judgement, review_id와 근거 쌍, round·product_family 연결 |
| NFR-K1, K2 | 1절 비밀 값 |
| NFR-C1~C3 | 6.1, llm_call_log |
| NFR-R1, R2 | ad_judgement의 model_name·prompt_version, 6.3 |

## 9. 테스트 (SQLite)

- 테스트는 SQLite로 돌고 Supabase에 접속하지 않습니다 (결정).
- 테스트 DB(SQLite)와 운영 DB(PostgreSQL)가 달라서 한쪽에서만 통과하는 문제가 생길 수 있습니다. 이를 막기 위해 1절의 자료형 규칙을 지키고, Phase 8 통합 점검에서 Supabase에서도 같은 확인을 합니다 (설계 제안).
- LLM 호출은 테스트에서 가짜 응답으로 대체해 실제 키와 비용 없이 검증 로직을 확인합니다 (설계 제안).
- 검증할 항목은 prd.md 8절의 통과/실패 기준에서 가져옵니다: 화면 수치와 원본 재집계값의 일치, 가중/비가중 전환 결과, 근거 ID 없는 문장의 제외, 합성 라벨.
- 테스트 프레임워크는 pytest입니다(결정). 샘플 데이터 구성은 확인 필요 SQ-10입니다.

## 10. 제외 범위

prd.md 7절과 같습니다. 이 명세에는 아래를 만들지 않습니다.

- 응답 업로드 API와 화면, 문항 초안 확정·수정 API, 액션 제안 선별·수정 API
- 로그인, 권한 분리
- 설문 발송, 리포트를 의사결정자에게 보내는 기능
- VOC 수집 실행 API (수집은 정기 자동 실행이 맡는다)
- 주제·감성 분류 (prd.md Q-15가 결정되기 전까지)
- 근거 뷰어의 광고성 확률·가중치 표시 (P-1, 보류)
- 데이터 확인 화면 (P-3, 거절)

## 11. 제안 (승인 대기)

| 번호 | 제안 | 이유 |
| --- | --- | --- |
| SP-1 | `GET /api/health`: 서버와 DB 연결 상태를 확인하는 엔드포인트 | n8n이 단계를 부르기 전에 서버가 살아 있는지 확인할 방법이 없다. 사용자 기능이 아니라 운영용이다 |
| P-5 (prd.md 9절, 승인, FR-1.11) | 외부 VOC를 두 모집단으로 나눈다. (1) 제목이나 본문이 있고 판정에 성공한 글: 가중/비가중 토글 적용. (2) 제목·본문이 모두 없거나 판정에 실패한 글: 토글과 무관하게 "판정 불가"로 건수와 평점 분포만 따로 표시한다 | SQ-2의 세 선택지(가중치 1로 포함 / 둘 다 제외 / 비가중에만 포함)는 모두 문제가 있다. 가중치 1은 근거 없이 "광고 아님"으로 간주하는 셈이고, 둘 다 제외는 제목·본문이 모두 없는 리뷰 992건의 평점 정보를 버리며, 비가중에만 포함은 토글이 가중치뿐 아니라 포함되는 글도 바꿔 FR-1.8(토글은 가중치에만 적용)과 어긋난다. 분리하면 토글은 가중치만 바꾸고 평점 정보도 남는다. **승인 시 영향:** A-3 응답에 판정 불가 영역이 늘고 S-2 화면에 "판정 불가" 영역이 하나 늘며, prd.md에 요구사항이 추가된다. 제목·본문이 모두 없는 리뷰는 1,302건 중 992건(약 76%, 실측)이라 판정 대상은 310건(약 24%)이다. **상태: 승인.** A-3의 `voc.undetermined`와 S-2의 "판정 불가" 섹션으로 반영함. 이 표에는 기록으로만 남긴다 |
| SP-3 | 근거 ID를 코드가 붙인다. 호출 B는 `row_ids`만 출력하고, 각 문장의 근거 ID 목록은 코드가 선택한 행의 `allowed_evidence_json`(집계에 들어간 모든 응답·리뷰)에서 그대로 붙인다 | 근거 개수와 선택 기준이 문서에 없다. 이 안은 "계산은 코드가" 원칙을 지키고, LLM이 근거를 고르거나 지어 붙일 여지가 없으며, 대표 사례를 고르는 규칙을 따로 만들 필요가 없다. 근거는 응답·리뷰 단위라 DR-4, FR-2.2와도 맞는다. **승인 시 영향:** (1) 호출 B 출력에서 `evidence_ids`를 빼고 검증 4번이 사라진다. (2) 문장 하나에 근거가 수백~천 건 붙을 수 있다. 전체 리뷰 1,302건 중 5점이 1,164건(약 89%, 실측)이라 "5점 비율" 같은 문장이 그렇다. (3) 근거 뷰어에 목록 조회와 페이지 나누기·필터가 필요하다. 즉 A-6 응답에는 근거 건수만 담고 목록을 보는 조회 API를 하나 더 둬야 한다. (4) `suggestion_evidence`를 저장할지, 행에서 계산할지 정해야 한다. **상태: 승인.** 호출 B 출력과 검증, A-6 응답, A-10, S-4로 반영함. 이 표에는 기록으로만 남긴다 |

## 12. 확인 필요 목록

| 번호 | 항목 | 관련 |
| --- | --- | --- |
| SQ-1 | 대시보드의 외부 VOC 집계에 담을 지표. 정해지지 않음. 후보는 리뷰 수·평균 평점·평점 분포이고, 가중 지표는 광고성 판정 파일럿 결과와 함께 정함. 평점 분포는 표본이 적은 칸의 표시·묶음 규칙이 필요. 단 "미판정"과 "제목·본문 없음" 섹션은 P-5에 따라 건수와 평점 분포를 쓴다. **결정(G4, 결정 2026-11-03, 사용자 승인):** (1) 지표는 건수, 평균 평점, 평점 분포(1~5점별 건수)다. 가중 쪽은 건수 = 가중치의 합, 평균 평점 = 가중 평균(Σ가중치×평점 ÷ Σ가중치), 분포 = 점수별 가중치의 합이며 계산은 코드가 한다(FR-0.1). (2) 표본이 적은 칸은 숨기거나 묶지 않고 건수 n을 항상 같이 보인다. 판정 묶음의 n이 30건 미만이면(임계값 30, n이 29건까지는 배지가 있고 30건부터는 없다) "표본 적음" 글자 배지를 붙인다. 임계값은 코드 상수(`VOC_SMALL_SAMPLE_THRESHOLD`)이고 기본 30이다. **이 값은 이 데이터로 검증한 것이 아닌 임시 가정이며 Q-7처럼 근거가 약하다.** (3) 화면은 "판정 N건 / 판정 대상 M건 / 전체 T건"을 항상 같이 보인다. | A-3 |
| SQ-2 | **해결됨(P-5 승인).** 판정 대상 범위는 정리됨: 제목이나 본문이 있는 310건(실측)을 판정하고, 제목만 있는 13건(310 − 297, 실측)도 포함한다(6.2 호출 A). 제목·본문이 모두 없는 992건(실측)과 판정 실패 글은 토글과 무관하게 "판정 불가"로 따로 표시하므로 가중치 기본값은 필요 없다. 문서에는 "글은 삭제하지 않고 가중만 낮춘다"(DR-3, FR-1.6)뿐이다. 분리 모집단 안은 prd.md 9절 P-5로 승인됨 | 호출 A, A-3 |
| SQ-3 | 광고성 확률을 규칙과 LLM으로 어떻게 하나로 만드는지. 정해지지 않음. 후보는 (a) 규칙이 확실한 광고의 확률을 직접 정하고 나머지만 LLM이 냄, (b) LLM이 규칙 신호를 입력으로 받아 하나의 확률을 냄, (c) 규칙 점수와 LLM 확률을 코드가 합침이며 모두 추론이고 문서에 없음. 기본안(설계 제안, 사용자 추천): (b). 호출 A의 `rule_signals`로 규칙 신호를 LLM에 넘기고 LLM이 하나의 확률을 낸다. 가중치 하한(prd.md Q-7)은 파일럿에서 정함. **결정(2026-11-02): A. 파일럿은 LLM 단독으로 하고, 규칙 신호는 골든셋 결과를 본 뒤에 정한다.** | 호출 A, ad_judgement |
| SQ-4 | (a) **해결됨(SP-3 승인).** 제안 문장 하나의 근거는 그 문장이 참조한 집계 행에 들어간 모든 응답·리뷰이며 코드가 붙인다. 승인 전 검토 내용: 제안 문장 하나가 근거를 몇 건 가리키는지와 선택 기준은 문서에 정해지지 않았었다. FR-2.1, FR-2.3은 "연결된다"고만 적었고, 이 명세는 행마다 허용 목록을 두고 문장이 그 안에서 고르는 구조까지만 정했다. 허용 목록에 집계 대상 전체를 넣을지 일부만 넣을지, 문장당 상한은 정해지지 않았다. 후보는 집계 대상 전체 연결(제안 SP-3, 승인 대기) / 대표 사례만 연결(건수·고정 기준 필요) / 표의 행 단위 연결(DR-4, FR-2.2의 "근거 ID는 응답·리뷰" 정의와 충돌)이다. (b) 설문 근거의 단위(응답 전체인지 문항별 응답인지): 정해지지 않음. 이 명세의 구조(A-4가 응답 한 건에 모든 문항 답을 담음, `survey_response`의 기본 키가 `response_id`)와 prd.md DR-4("모든 응답과 리뷰는 근거 ID로 식별")는 응답 전체 단위로 읽히지만 구조에서 읽은 것일 뿐이다. 문항별로 가리키는 방식은 어디에도 정해지지 않았고, 택하면 근거가 응답자 수 × 문항 수로 늘어난다. (c) "불확실·모순 가설"을 가려내는 방식(prd.md Q-5): 정해지지 않음. **결정(2026-11-03, 사용자 승인): 3.2절 hypothesis 아래 "구현에서 정함 (Phase 6, 가설)"의 코드 규칙 R1~R4.** | 근거, hypothesis |
| SQ-5 | 변수 단위의 열 정의와 문항 유형 목록(개요는 확인됨: 15683은 177개 변수·1,500행, 14488은 80개 변수·417행, 가중치 변수 없음, 한국 응답자 필터는 `CONTURY` 500명 / `nationality` 234명). 14488의 7점 척도 설문지와 1~5뿐인 데이터 값의 불일치를 어떻게 다룰지. 합성 응답을 제품군·회차에 연결하는 방식: 정해지지 않음. 기본안(설계 제안): 제품군과 무관한 공통 설문으로 만들어 `family_id`를 NULL로 두고, 화면에 "설문은 제품군과 무관"을 표시한다. KOSSDA에는 후지필름 제품에 대한 답이 없어 제품군별 결과를 만들면 없는 결과를 지어내게 되기 때문이다. 대신 제품군을 바꿔도 설문 쪽은 변하지 않으므로 prd.md FR-1.2의 "제품군을 고르면 설문 집계와 VOC가 한 화면에 나온다"는 기준은 "같은 설문 집계와 해당 제품군의 VOC가 나온다"로 읽는다. 회차 연결은 SQ-6. **결정(2026-11-02): 기본안 채택(공통 설문, `family_id`=NULL). 합성만 적재하고 KOSSDA는 구조 참고만 한다(PQ-4). 문항 유형·열 정의·7점 척도 불일치는 KOSSDA 변수 구조를 본 뒤에 정한다.** (2026-11-03) 메타데이터 확인 결과(변수·행 수, 값 라벨 코드 구성별 개수)는 plan.md Phase 0c에 기록했다. 14488의 척도 길이(7점인지 5점인지)와 결측 코드는 **확인 못 함**이다. **(2026-11-03 닫음) 합성 척도는 자체 설계한 5점이라 14488 척도 길이 확인이 불필요하다. .sav는 파기했다.** (결정 2026-11-03, 사용자 승인) | survey 테이블, 호출 C |
| SQ-6 | 리뷰를 회차에 대응시키는 방식(날짜 구간 등). 정해지지 않음. `round`에는 `period_start`, `period_end`를 NULL 허용으로 두었다. 리뷰 날짜(2017-06-24 ~ 2026-10-27, 실측)와 합성 설문의 회차가 맞지 않을 수 있다. 분기별 건수는 기준에 따라 다르다(2025Q1~2026Q3, 실측): 전체 리뷰는 분기당 55~139건, 본문이 있는 리뷰는 14~28건. **결정(2026-11-02): 회차는 달력 분기 기준이고 2026-Q1(2026-01-01~03-31)과 2026-Q2(2026-04-01~06-30) 2개로 한다.** 판정 대상 파일럿 표본 100건 중 각각 11건이다(실측). **리뷰의 회차 소속(Phase 4, 결정 2026-11-03, 사용자 승인):** 리뷰 날짜가 `round`의 `period_start`~`period_end` 안(양 끝 포함)이면 그 회차 소속이다. 제품군은 `product.family_id`로 거른다. 회차에 속하지 않는 리뷰는 집계에 넣지 않고 "포함되지 않은 N건"으로 건수만 보인다. | round, A-3 |
| SQ-7 | `author`를 DB에 적재할지. **해결됨(결정): `author`는 DB에 적재하지 않는다.** 작성자 규칙이 필요해지면 그때 따로 정한다. 표시(FR-2.5)와 LLM 입력(NFR-S2)에서는 P-4로 이미 제외했고 이 명세의 DB 테이블에도 `author` 열이 없다. 단, NFR-S2와 P-4는 화면과 LLM 입력만 막으므로 코드 안의 규칙이 `author`를 쓰는 것은 금지되어 있지 않다. 적재하지 않으면 값이 DB에 없어 자연히 쓸 수 없고, 필요해지면 원본 CSV에서 다시 읽어야 한다. 작성자 반복(가장 많은 값이 53행, 실측)을 광고성 규칙에 쓸 수 있는지는 문서에 없다. 가려진 이름은 서로 다른 사람이 같은 값이 될 수 있어(같은 마스킹 값이 17행인 경우가 있음, 실측) 반복 신호로 믿기 어렵다 | 3.1 |
| SQ-8 | n8n의 역할과 호출 방식(prd.md Q-4), 단계 이름·개수, 재실행 시 이전 결과 처리(정해지지 않음. 기본안은 쌓기: 결과 테이블이 `run_id`를 갖고 `ad_judgement`가 `model_name`·`prompt_version`을 두는 구조가 쌓기에 맞고 반복 실행 일치율 NFR-R1 측정에 필요하다. 덮어쓰면 이 측정이 어렵다), 실패 알림, 워크플로 파일 위치(정해지지 않음. 기본안은 `backend/n8n/`, 설계 제안). 실패 알림은 PRD에 없는 기능이라 두지 않고(기본안), n8n은 자체 재시도를 하지 않고 단계 안의 재시도만 쓴다(기본안, 6.3절) | 4.3, 7.5, 2절 |
| SQ-9 | LLM 세부: 모델(광고성 판정은 `gpt-5.6-luna`로 기록함(prd.md Q-12, 2026-11-02). 문항·제안 호출은 정해지지 않음. 기본안은 호출 종류별 환경 값으로 빼서 키 점검 후 채움; 광고성 판정이 가장 많이 불리므로 비용 기준을 먼저 정한다. 판정 대상은 실행당 최대 310건, 실측), 구조화 출력 사용, 무작위성 값, 한 호출의 항목 수, 문장 길이 상한, 숫자 비교 규칙, 재시도 횟수·대기 시간, 가설당 문항 수. **결정(2026-11-02): 파일럿 규모의 가정값(묶음 10건, 일시 오류 재시도 3회, 검증 실패 재시도 2회, 대기 1·2·4초, 시간 제한 60초)을 유지하고 무작위성 값은 지정하지 않는다. 문장 길이·숫자 비교·가설당 문항 수는 Phase 5·6에서 정한다.** (2026-11-03) Phase 5 결정: 문장 길이 120자, 한 호출 최대 5문장, 숫자 일치 규칙은 6.2절 "구현에서 정함"(호출 B)에 적었다. 가설당 문항 수는 Phase 6에서 정한다. (결정 2026-11-03, 사용자 승인) **Phase 6 결정(2026-11-03, 사용자 승인): 가설당 문항 1개(문항 대상 가설에만 적용, R1 표본 적음 가설은 문항 없이 저장만, 4.2절·6.2절). 문항은 100자 이내(가정). `single`·`multi` 선택지는 2~6개. 호출 C의 `previous_questions`는 입력하지 않는다(미정으로 남긴다).** | 6절 |
| SQ-10 | **대부분 해결됨(결정):** Python 3.13, pip + `requirements.txt`, pytest, Vite, React Router, JavaScript, SQLAlchemy + Alembic, psycopg 3, `backend/.venv`. 남은 항목: 차트 라이브러리(SQ-1이 먼저), 상태 관리, ORM은 SQLAlchemy + Alembic으로 확정(두 DB를 모두 지원하고 메타데이터로 SQLite 테스트와 PostgreSQL 운영이 같은 정의를 쓰며 이력이 남는다. SQLModel은 이미 A-1~A-10 응답 형식을 따로 정의해 이점이 작다) | 1절, 9절 |
| SQ-11 | `database/` 폴더의 역할, 원본 CSV 보관 위치와 추적 여부, Supabase 풀 크기·보안 설정. 정해지지 않음. 스키마는 ORM 메타데이터에서 만들기로 해서(1절) `database/`에 SQL 파일을 둘 이유는 약하다. 합성 응답 파일의 위치·저장 방식은 문서에 없다. **해결됨(결정):** 원본 CSV와 합성 응답 생성 결과는 `database/data/`에 두고 `.gitignore`로 추적에서 뺀다. `database/`에 SQL 파일은 두지 않는다(스키마는 ORM이 만든다). 지금 `.gitignore`에는 CSV·데이터 폴더 항목이 없어서 저장소를 만들기 전에 추가해야 한다 | 2절, 1절 |
| SQ-12 | 네이버 블로그·카페 글의 열 구성과 테이블(취소됨, 결정 2026-11-03) | 3.2 |
| SQ-13 | 회차 리포트가 회차 전체 단위인지 제품군 단위인지. 정해지지 않음. prd.md FR-3.1은 단위 없이 "액션플랜과 다음 회차 설문지가 함께 담긴다"고만 적었고, `report.family_id`를 NULL 허용으로 둔 것과 A-5가 `round_id`·`family_id`를 모두 선택 조건으로 받는 것은 두 단위를 모두 허용하는 모양일 뿐 결정이 아니다. 제품군 목록 자체가 미정(prd.md Q-3)이라 제품군별 리포트의 범위도 아직 정할 수 없다. 기본안(설계 제안): 회차 전체 리포트 한 부 안에 제품군별 절을 둔다. 이 경우 `report.family_id`는 NULL이고, 절 구분은 각 제안의 `snapshot_id`가 가진 `family_id`로 한다. **Phase 5 결정(2026-11-03, 사용자 승인): `action-suggestions` 실행마다 `report` 1행(`family_id` 포함)을 만들고 쌓는다. 화면은 가장 최근 성공한 실행을 보여준다. 회차 리포트로 합치는 방식은 Phase 6에서 정한다.** **Phase 6 결정(2026-11-03, 사용자 승인): `report-assembly`는 얇은 확인 단계다(액션 제안 1개 이상, 초안 문항 1개 이상인지 검사하고 실행 기록만 남긴다). 시간이 모자라면 가장 먼저 컷하고 A-6이 읽을 때 조립한다.** | report |
| SQ-14 | 내보내기 형식(prd.md Q-8). 정해지지 않음. 기본안(설계 제안): HTML. 의사결정자는 시스템을 쓰지 않고 파일만 받으므로(prd.md 가정) 한 파일로 열리고 인쇄해 PDF로 저장할 수 있으면 충분하고, 추가 라이브러리 없이 만들 수 있으며 한글 글꼴은 브라우저가 처리한다. 조건: 스타일을 모두 담은 독립형 HTML 한 파일이고, 의사결정자 컴퓨터에서는 시스템에 접속할 수 없으므로 근거 ID는 링크가 아니라 텍스트로만 적는다. 파일에 적는 근거: 정해지지 않음. 문장 하나에 근거가 수백~천 건 붙을 수 있어(SP-3) 전체 ID를 적으면 읽기 어려운 파일이 된다. 기본안(설계 제안): 문장 끝에 근거 건수만 적는다(예: "근거 리뷰 187건"). 개별 근거 확인은 담당자가 시스템에서 하고(prd.md 기능 2), 근거 ID 검사(FR-2.4)는 리포트를 만들 때 시스템 안에서 끝난다. 일부 ID를 적는 안은 고르는 기준을 따로 정해야 해서 쓰지 않는다. **Phase 6 결정(2026-11-03, 사용자 승인): `format=html`만 허용하고 그 밖은 400 `UNSUPPORTED_FORMAT`. 파일에는 제품군·회차·생성 시각, 액션플랜 문장과 근거 건수(링크 없음), 다음 회차 설문지("초안" 표시), "합성/실측" 출처 표기만 담는다. 리뷰 본문·작성자는 담지 않는다. 외부 리소스는 0건(`src`/`href`/`url()` 검사)이고 LLM이 낸 글은 모두 HTML 이스케이프한다. 파일 이름은 `report-{id}.html`.** | A-7 |
| SQ-15 | 근거 뷰어에 리뷰 제목(title)을 보여줄지. 정해지지 않음. 기본안(설계 제안): 본문이 없을 때만 제목을 대신 보여준다. 확정하면 prd.md FR-2.5를 "본문(본문이 없으면 제목)"으로 고친다. 제목을 보여주면 prd.md NFR-S4·Q-10의 개인정보 점검을 제목 기준으로도 다시 본다. 제목만 있는 리뷰를 근거 허용 목록에서 빼는 안은 근거 개수 결정(SP-3)과 얽혀 있어 따로 정한다. prd.md FR-2.5는 "본문"이라고만 적었고 이 명세도 title을 뺀 채로 읽어 두 문서의 해석은 같다. 다만 제목만 있는 리뷰 13건(실측)이 근거가 되면 뷰어에 보여줄 본문이 비어 있다 | A-4 |
| SQ-16 | 로그 보존 기간과 회전 방식. 정해지지 않음. 로그 위치와 남기지 않는 항목(7.4)은 이미 정했다. 기본안(설계 제안): 일 단위 파일 나누기 + 7일(가정) 보관. 7일은 근거가 없는 값이라 시연·파일럿 기간에 맞춰 조정한다. 크기 기준 회전은 로그 양이 적어 지금은 쓰지 않는다 | 7.3 |
| SQ-17 | A-10 근거 목록의 `page_size` 기본값과 상한, `suggestion_evidence`를 저장할지 계산할지, 목록의 필터 범위. 모두 정해지지 않음. 기본안(설계 제안): `page_size` 기본 50, 상한 200(가정, 근거 없음). `suggestion_evidence`는 저장하지 않고 스냅샷의 허용 목록에서 계산한다. 필터는 `kind`(리뷰·설문)만 둔다. **결정(2026-11-03, 사용자 승인): 기본안을 채택했다. `page_size` 기본 50·상한 200, `suggestion_evidence`는 저장하지 않고 계산, 필터는 `kind`만, 정렬은 종류 다음 `evidence_id`.** | A-10, 3.2 |
