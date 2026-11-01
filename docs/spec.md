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
| LLM | OpenAI API | 키는 `backend/.env`에만 둔다 (결정). 모델 이름은 정해지지 않음 (확인 필요 SQ-9) |

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
- prd.md는 "텍스트가 있는 리뷰 297건", "제목이나 본문이 있는 리뷰 310건, 둘 다 빈 리뷰 992건"이라고 했고, 이 대조로 같은 수를 확인했습니다. 광고성 판정 대상은 제목이나 본문이 있는 310건입니다(6.2 호출 A). 제목·본문이 모두 없는 992건은 집계에서 "판정 불가" 섹션으로 따로 표시합니다(P-5 승인, FR-1.11).
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
| family_id | FK → product_family, NULL 허용 | 제품군이 정해지기 전에는 NULL |

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
- 네이버 블로그·카페 글은 열 구성이 정해지지 않아 테이블을 정의하지 않았다(확인 필요 SQ-12).

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
| survey_question | question_id(PK), round_id(FK), code, text, type, options_json | type의 값은 확인 필요 SQ-5 |
| survey_response | response_id(PK), round_id(FK), family_id(FK, NULL 허용), is_synthetic(불리언, NOT NULL) | 합성 응답에는 "합성" 표시를 데이터에 고정(DR-2). 합성 응답을 제품군에 연결하는 방식은 확인 필요 SQ-5. 기본안(설계 제안)은 제품군과 무관한 공통 설문이라 `family_id`는 NULL |
| survey_answer | answer_id(PK), response_id(FK), question_id(FK), value | |

**ad_judgement (광고성 판정)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| judgement_id | 정수, 기본 키 | |
| review_id | FK → review | |
| run_id | FK → pipeline_run | |
| ad_probability | 실수, NULL 허용 | 0~1 CHECK |
| ad_weight | 실수, NULL 허용 | 1 − ad_probability(FR-1.5, 1.7). 구현(Phase 3)은 하한 없이 `1 − 확률`을 저장한다. 하한은 확인 필요 SQ-3, prd.md Q-7 |
| model_name, prompt_version | 텍스트, NULL 허용 | 반복 실행 일치율(NFR-R1) 측정용. `skipped`는 LLM을 부르지 않아 NULL |
| status | 텍스트 | `ok`, `failed`, `skipped` CHECK. 제목·본문이 모두 없는 글은 LLM에 보내지 않고 `skipped`로 기록한다 |
| error_code | 텍스트, NULL 허용 | |
| judged_at | 시각 | |

- 구현에서 추가한 제약: `(review_id, run_id)` 유일, `status = 'ok'`일 때만 `ad_probability`가 NULL이 아님(CHECK), `run_id` 색인.
- `weight_floor_used`(하한 값 기록)와 `rule_signals`(규칙 신호)는 구현하지 않았다. SQ-3(규칙과 LLM 결합)과 Q-7(하한)이 정해질 때 추가한다.

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

**hypothesis (불확실·모순 가설)**

| 열 | 형식 | 비고 |
| --- | --- | --- |
| hypothesis_id | 정수, 기본 키 | |
| snapshot_id, round_id, family_id | FK | |
| kind | 텍스트 | `uncertain`, `contradictory` CHECK |
| statement | 텍스트 | |
| related_row_ids | JSON | 스냅샷 표의 행 ID |

- 가설을 어떻게 가려내는지는 정해지지 않았습니다(prd.md Q-5, 확인 필요 SQ-4). 이 테이블은 가려낸 결과를 담는 자리일 뿐입니다.

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
| A-1 | GET | `/api/families` | 없음 | `families`: 제품군 목록 `{family_id, name}` | 200, 500 | FR-1.1 |
| A-2 | GET | `/api/rounds` | 없음 | `rounds`: 회차 목록 `{round_id, label, period_start, period_end}` | 200, 500 | FR-1.3 |
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
| `voc.unweighted` | 외부 VOC의 비가중 집계. 광고성 판정에 성공한 글만 대상이다(P-5, FR-1.11) |
| `voc.weighted` | 외부 VOC의 가중 집계 (가중치 = 1 − 광고성 확률, 하한 적용). `unweighted`와 같은 글이 대상이다 |
| `voc.weight_floor` | 계산에 쓴 하한 값 |
| `voc.counts` | `{total, judged, unjudged}`. 광고성 판정이 된 글과 안 된 글의 수 |
| `voc.undetermined` | `{count, no_text_count, failed_count, rating_distribution: [{rating, count}]}`. 제목·본문이 모두 없는 글과 판정에 실패한 글. 토글과 무관하게 항상 같은 값이다(P-5, FR-1.11). `count`는 `no_text_count + failed_count`이고 `voc.counts.unjudged`와 같다 |

- 가중 집계와 비가중 집계를 **항상 둘 다** 돌려줍니다(FR-1.8). 토글은 화면에서 어느 쪽을 보여줄지만 고르고, 서버에 토글 값을 보내지 않습니다.
- VOC 집계에 어떤 지표를 담을지는 정해지지 않았습니다(확인 필요 SQ-1). 문서에 있는 것은 "가중/비가중 토글로 VOC 집계 결과가 바뀐다"는 확인 기준뿐입니다.
  - 후보는 리뷰 수, 평균 평점, 평점 분포입니다. 가중 쪽은 리뷰 수를 가중치의 합으로, 평균 평점을 가중 평균으로 바꾸는 방식이 자연스럽지만 문서에 적힌 것은 아니고 추론입니다.
  - 가중 집계를 어떤 지표로 보일지는 광고성 판정 파일럿(Phase 3) 결과와 함께 정합니다.
  - 평점 분포를 쓰면 표본이 적은 칸이 생깁니다. 1~2점은 전체 1,302건 중 22건, 본문이 있는 리뷰 297건 중 10건입니다(실측). 건수를 함께 표시하거나 칸을 묶는 규칙이 필요하며, 이 규칙도 정해지지 않았습니다.
- 가중 평균은 가중치와 평점의 곱을 합해 가중치의 합으로 나눈 값이고, 계산은 코드가 합니다(FR-0.1).
- 400은 `round_id`가 요청한 제품군과 맞지 않는 경우(데이터가 없는 조합)에 씁니다. 회차가 아예 없으면 404입니다.

**A-4 응답 (근거)**

| kind | 필드 | 비고 |
| --- | --- | --- |
| `review` | `kind`, `review_id`, `rating`, `date`, `review_text`, `text_source` | FR-2.5. `review_text`가 비어 있으면 `title` 값을 `review_text` 자리에 넣고 `text_source`를 `title`로 한다(`text_source`는 `review_text` 또는 `title`). 기본안이며 설계 제안이다(확인 필요 SQ-15). 그 밖의 `title`과 `author`, `variant`는 담지 않는다 |
| `survey` | `kind`, `response_id`, `synthetic_label`, `round`, `answers: [{question_text, value}]` | 합성 응답이면 `synthetic_label`이 `"합성"`. 필드는 설문 구조를 확인한 뒤 확정(확인 필요 SQ-5) |

**A-6 응답 (리포트)**

| 필드 | 설명 |
| --- | --- |
| `report_id`, `round`, `family`, `generated_at` | 기본 정보. `family`는 NULL일 수 있음(확인 필요 SQ-13) |
| `action_plan` | `{suggestion_id, order_no, sentence, evidence_count: {review, survey}}` 목록. 모든 문장이 근거를 하나 이상 가진다(FR-2.3, 2.4). 근거 목록은 문장당 수백~천 건이 될 수 있어 응답에 담지 않고 A-10으로 조회한다(SP-3) |
| `next_survey` | `{status: "draft", questions: [{order_no, text, type, options}]}`. `status`는 항상 `draft`(FR-3.3) |

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
- 같은 단계를 다시 실행할 때 이전 결과를 어떻게 처리할지는 정해지지 않았습니다(확인 필요 SQ-8). 기본안(설계 제안)은 쌓는 것입니다: 실행마다 새 결과를 만들고 이전 결과를 지우지 않으며, 화면은 가장 최근에 성공한 실행의 결과를 보여줍니다. "가장 최근 성공한 실행을 보여준다"는 규칙은 이 명세에서 처음 적는 것입니다.

## 5. 화면별 구성과 사용하는 API

화면을 이렇게 나눌지는 정해지지 않았습니다(prd.md Q-9). 아래는 prd.md의 S-1~S-4를 따른 구성입니다.

| 화면 | 구성 | 사용하는 API |
| --- | --- | --- |
| S-1 제품군 선택 | 제품군 목록. 별도 화면 또는 대시보드 안의 영역은 확인 필요 Q-9 | A-1 |
| S-2 제품군 대시보드 | 상단: 제품군, 회차 선택. 설문 집계 영역(합성 라벨 포함, 설문이 제품군과 무관하다는 표시는 기본안). 외부 VOC 집계 영역. 가중/비가중 토글(판정에 성공한 VOC에만 적용). VOC 영역 안의 "판정 불가" 섹션: 건수와 평점 분포, 토글과 무관(P-5, FR-1.11) | A-2, A-3 |
| S-3 근거 뷰어 | 근거 하나를 보여준다. 리뷰는 review_id, 평점, 날짜, 본문만(본문이 없으면 제목, 기본안). 합성 응답은 "합성" 라벨 | A-4 |
| S-4 회차 리포트 | 액션플랜(문장마다 근거 건수와 근거 목록 링크, 목록은 페이지 단위), 다음 회차 설문지(초안 표시), 내보내기 버튼 | A-5, A-6, A-7, A-10, A-4 |

**화면 동작 규칙**
- 가중/비가중 토글은 화면 안에서만 바뀐다. 서버를 다시 부르지 않는다(A-3이 둘 다 준다).
- 설문 집계 영역은 토글의 영향을 받지 않고, 비가중이라는 표시를 둔다(FR-1.9).
- 문장의 근거 건수를 누르면 근거 목록이 열리고(A-10, 페이지 단위), 목록의 항목을 누르면 S-3이 A-4를 호출한다. 근거를 찾을 수 없으면(404) "근거를 찾을 수 없음"을 보여준다.
- 라우팅은 React Router를 쓴다(결정). 라우팅 주소, 상태 관리, 차트 라이브러리는 확인 필요 SQ-10.

## 6. LLM 호출 명세

### 6.1 공통

| 항목 | 내용 |
| --- | --- |
| 서비스 | OpenAI API. 호출은 backend의 `llm/client`만 한다. 프런트엔드와 n8n은 LLM을 직접 부르지 않는다 (설계 제안) |
| 키 | `backend/.env`에서만 읽는다. 로그와 응답에 넣지 않는다 |
| 모델 | 정해지지 않음 (확인 필요 SQ-9). 기본안(설계 제안): 모델 이름을 코드에 박지 않고 호출 종류별(광고성 판정, 액션 제안 서술, 문항 초안) 환경 값으로 둔다. 같은 모델을 쓸지 다르게 쓸지는 나중에 정하고, 호출마다 모델 이름을 `ad_judgement.model_name`과 `llm_call_log.model_name`에 남겨 모델별로 반복 실행 일치율(NFR-R1)을 비교할 수 있게 한다 |
| 입력 제한 | `author`와 `variant`는 어떤 호출에도 넣지 않는다(NFR-S2). 필요한 열만 허용 목록으로 골라 보낸다 |
| 출력 | JSON만 받는다. 출력 스키마를 호출에 지정하는 방식(구조화 출력)은 모델이 정해진 뒤 확인(확인 필요 SQ-9) |
| 무작위성 | 반복 실행 일치율(NFR-R1)을 위해 낮게 둔다. 값은 확인 필요 SQ-9 |
| 원칙 | LLM은 수치를 만들거나 바꾸지 않는다. 가중치 계산과 집계는 코드가 한다(FR-0.1, 0.2, 0.4) |
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
- 규칙 신호(`rule_signals`)를 LLM에 넘기는지는 확인 필요 SQ-3입니다. 지금 구현은 넘기지 않습니다.
- 한 호출에 몇 건을 넣을지는 확인 필요 SQ-9입니다.
- 한 실행에서 LLM에 보내는 글 수에는 상한을 둡니다. 기본 100건(파일럿, 가정)이며 환경 값으로 바꿉니다. 이름이 든 본문은 보내지 않습니다. 판정 대상 310건 전체 실행은 prd.md Q-17-3이 해결된 뒤에만 상한을 올려서 합니다 (설계 제안, plan.md Phase 3).
- 코드가 `ad_probability`로 가중치(1 − 확률, 하한 적용)를 계산합니다. 하한은 파일럿에서 정합니다(prd.md Q-7).
- 규칙과 LLM이 어떻게 하나의 확률이 되는지는 확인 필요 SQ-3입니다.

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
| 출력 검증 실패 | 실패한 항목만 오류 내용을 알려 주고 다시 요청한다 | 최대 2회 (가정) |
| 재시도 후에도 실패 | 그 항목은 `failed`로 기록하고 값을 지어내지 않는다. 실행 기록은 `partial`(일부 성공) 또는 `failed`(전부 실패) | |

- 재시도 횟수와 대기 시간은 가정이며 확인 필요 SQ-9입니다.
- 광고성 판정이 실패한 글은 가중치가 없습니다. 이런 글과 판정 대상이 아닌 992건을 집계에서는 토글과 무관하게 "판정 불가"로 건수와 평점 분포만 따로 표시합니다(prd.md 9절 P-5 승인, FR-1.11).
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
| FR-1.11 (P-5) | A-3 응답의 `voc.undetermined`, `ad_judgement.status`, S-2의 "판정 불가" 섹션 |
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
| SQ-1 | 대시보드의 외부 VOC 집계에 담을 지표. 정해지지 않음. 후보는 리뷰 수·평균 평점·평점 분포이고, 가중 지표는 광고성 판정 파일럿 결과와 함께 정함. 평점 분포는 표본이 적은 칸의 표시·묶음 규칙이 필요. 단 "판정 불가" 섹션은 P-5에 따라 건수와 평점 분포를 쓴다 | A-3 |
| SQ-2 | **해결됨(P-5 승인).** 판정 대상 범위는 정리됨: 제목이나 본문이 있는 310건(실측)을 판정하고, 제목만 있는 13건(310 − 297, 실측)도 포함한다(6.2 호출 A). 제목·본문이 모두 없는 992건(실측)과 판정 실패 글은 토글과 무관하게 "판정 불가"로 따로 표시하므로 가중치 기본값은 필요 없다. 문서에는 "글은 삭제하지 않고 가중만 낮춘다"(DR-3, FR-1.6)뿐이다. 분리 모집단 안은 prd.md 9절 P-5로 승인됨 | 호출 A, A-3 |
| SQ-3 | 광고성 확률을 규칙과 LLM으로 어떻게 하나로 만드는지. 정해지지 않음. 후보는 (a) 규칙이 확실한 광고의 확률을 직접 정하고 나머지만 LLM이 냄, (b) LLM이 규칙 신호를 입력으로 받아 하나의 확률을 냄, (c) 규칙 점수와 LLM 확률을 코드가 합침이며 모두 추론이고 문서에 없음. 기본안(설계 제안, 사용자 추천): (b). 호출 A의 `rule_signals`로 규칙 신호를 LLM에 넘기고 LLM이 하나의 확률을 낸다. 가중치 하한(prd.md Q-7)은 파일럿에서 정함 | 호출 A, ad_judgement |
| SQ-4 | (a) **해결됨(SP-3 승인).** 제안 문장 하나의 근거는 그 문장이 참조한 집계 행에 들어간 모든 응답·리뷰이며 코드가 붙인다. 승인 전 검토 내용: 제안 문장 하나가 근거를 몇 건 가리키는지와 선택 기준은 문서에 정해지지 않았었다. FR-2.1, FR-2.3은 "연결된다"고만 적었고, 이 명세는 행마다 허용 목록을 두고 문장이 그 안에서 고르는 구조까지만 정했다. 허용 목록에 집계 대상 전체를 넣을지 일부만 넣을지, 문장당 상한은 정해지지 않았다. 후보는 집계 대상 전체 연결(제안 SP-3, 승인 대기) / 대표 사례만 연결(건수·고정 기준 필요) / 표의 행 단위 연결(DR-4, FR-2.2의 "근거 ID는 응답·리뷰" 정의와 충돌)이다. (b) 설문 근거의 단위(응답 전체인지 문항별 응답인지): 정해지지 않음. 이 명세의 구조(A-4가 응답 한 건에 모든 문항 답을 담음, `survey_response`의 기본 키가 `response_id`)와 prd.md DR-4("모든 응답과 리뷰는 근거 ID로 식별")는 응답 전체 단위로 읽히지만 구조에서 읽은 것일 뿐이다. 문항별로 가리키는 방식은 어디에도 정해지지 않았고, 택하면 근거가 응답자 수 × 문항 수로 늘어난다. (c) "불확실·모순 가설"을 가려내는 방식(prd.md Q-5): 정해지지 않음 | 근거, hypothesis |
| SQ-5 | 변수 단위의 열 정의와 문항 유형 목록(개요는 확인됨: 15683은 177개 변수·1,500행, 14488은 80개 변수·417행, 가중치 변수 없음, 한국 응답자 필터는 `CONTURY` 500명 / `nationality` 234명). 14488의 7점 척도 설문지와 1~5뿐인 데이터 값의 불일치를 어떻게 다룰지. 합성 응답을 제품군·회차에 연결하는 방식: 정해지지 않음. 기본안(설계 제안): 제품군과 무관한 공통 설문으로 만들어 `family_id`를 NULL로 두고, 화면에 "설문은 제품군과 무관"을 표시한다. KOSSDA에는 후지필름 제품에 대한 답이 없어 제품군별 결과를 만들면 없는 결과를 지어내게 되기 때문이다. 대신 제품군을 바꿔도 설문 쪽은 변하지 않으므로 prd.md FR-1.2의 "제품군을 고르면 설문 집계와 VOC가 한 화면에 나온다"는 기준은 "같은 설문 집계와 해당 제품군의 VOC가 나온다"로 읽는다. 회차 연결은 SQ-6 | survey 테이블, 호출 C |
| SQ-6 | 리뷰를 회차에 대응시키는 방식(날짜 구간 등). 정해지지 않음. `round`에는 `period_start`, `period_end`를 NULL 허용으로 두었다. 리뷰 날짜(2017-06-24 ~ 2026-10-27, 실측)와 합성 설문의 회차가 맞지 않을 수 있다. 분기별 건수는 기준에 따라 다르다(2025Q1~2026Q3, 실측): 전체 리뷰는 분기당 55~139건, 본문이 있는 리뷰는 14~28건 | round, A-3 |
| SQ-7 | `author`를 DB에 적재할지. **해결됨(결정): `author`는 DB에 적재하지 않는다.** 작성자 규칙이 필요해지면 그때 따로 정한다. 표시(FR-2.5)와 LLM 입력(NFR-S2)에서는 P-4로 이미 제외했고 이 명세의 DB 테이블에도 `author` 열이 없다. 단, NFR-S2와 P-4는 화면과 LLM 입력만 막으므로 코드 안의 규칙이 `author`를 쓰는 것은 금지되어 있지 않다. 적재하지 않으면 값이 DB에 없어 자연히 쓸 수 없고, 필요해지면 원본 CSV에서 다시 읽어야 한다. 작성자 반복(가장 많은 값이 53행, 실측)을 광고성 규칙에 쓸 수 있는지는 문서에 없다. 가려진 이름은 서로 다른 사람이 같은 값이 될 수 있어(같은 마스킹 값이 17행인 경우가 있음, 실측) 반복 신호로 믿기 어렵다 | 3.1 |
| SQ-8 | n8n의 역할과 호출 방식(prd.md Q-4), 단계 이름·개수, 재실행 시 이전 결과 처리(정해지지 않음. 기본안은 쌓기: 결과 테이블이 `run_id`를 갖고 `ad_judgement`가 `model_name`·`prompt_version`을 두는 구조가 쌓기에 맞고 반복 실행 일치율 NFR-R1 측정에 필요하다. 덮어쓰면 이 측정이 어렵다), 실패 알림, 워크플로 파일 위치(정해지지 않음. 기본안은 `backend/n8n/`, 설계 제안). 실패 알림은 PRD에 없는 기능이라 두지 않고(기본안), n8n은 자체 재시도를 하지 않고 단계 안의 재시도만 쓴다(기본안, 6.3절) | 4.3, 7.5, 2절 |
| SQ-9 | LLM 세부: 모델(정해지지 않음. 기본안은 호출 종류별 환경 값으로 빼서 키 점검 후 채움; 광고성 판정이 가장 많이 불리므로 비용 기준을 먼저 정한다. 판정 대상은 실행당 최대 310건, 실측), 구조화 출력 사용, 무작위성 값, 한 호출의 항목 수, 문장 길이 상한, 숫자 비교 규칙, 재시도 횟수·대기 시간, 가설당 문항 수 | 6절 |
| SQ-10 | **대부분 해결됨(결정):** Python 3.13, pip + `requirements.txt`, pytest, Vite, React Router, JavaScript, SQLAlchemy + Alembic, psycopg 3, `backend/.venv`. 남은 항목: 차트 라이브러리(SQ-1이 먼저), 상태 관리, ORM은 SQLAlchemy + Alembic으로 확정(두 DB를 모두 지원하고 메타데이터로 SQLite 테스트와 PostgreSQL 운영이 같은 정의를 쓰며 이력이 남는다. SQLModel은 이미 A-1~A-10 응답 형식을 따로 정의해 이점이 작다) | 1절, 9절 |
| SQ-11 | `database/` 폴더의 역할, 원본 CSV 보관 위치와 추적 여부, Supabase 풀 크기·보안 설정. 정해지지 않음. 스키마는 ORM 메타데이터에서 만들기로 해서(1절) `database/`에 SQL 파일을 둘 이유는 약하다. 합성 응답 파일의 위치·저장 방식은 문서에 없다. **해결됨(결정):** 원본 CSV와 합성 응답 생성 결과는 `database/data/`에 두고 `.gitignore`로 추적에서 뺀다. `database/`에 SQL 파일은 두지 않는다(스키마는 ORM이 만든다). 지금 `.gitignore`에는 CSV·데이터 폴더 항목이 없어서 저장소를 만들기 전에 추가해야 한다 | 2절, 1절 |
| SQ-12 | 네이버 블로그·카페 글의 열 구성과 테이블 | 3.2 |
| SQ-13 | 회차 리포트가 회차 전체 단위인지 제품군 단위인지. 정해지지 않음. prd.md FR-3.1은 단위 없이 "액션플랜과 다음 회차 설문지가 함께 담긴다"고만 적었고, `report.family_id`를 NULL 허용으로 둔 것과 A-5가 `round_id`·`family_id`를 모두 선택 조건으로 받는 것은 두 단위를 모두 허용하는 모양일 뿐 결정이 아니다. 제품군 목록 자체가 미정(prd.md Q-3)이라 제품군별 리포트의 범위도 아직 정할 수 없다. 기본안(설계 제안): 회차 전체 리포트 한 부 안에 제품군별 절을 둔다. 이 경우 `report.family_id`는 NULL이고, 절 구분은 각 제안의 `snapshot_id`가 가진 `family_id`로 한다 | report |
| SQ-14 | 내보내기 형식(prd.md Q-8). 정해지지 않음. 기본안(설계 제안): HTML. 의사결정자는 시스템을 쓰지 않고 파일만 받으므로(prd.md 가정) 한 파일로 열리고 인쇄해 PDF로 저장할 수 있으면 충분하고, 추가 라이브러리 없이 만들 수 있으며 한글 글꼴은 브라우저가 처리한다. 조건: 스타일을 모두 담은 독립형 HTML 한 파일이고, 의사결정자 컴퓨터에서는 시스템에 접속할 수 없으므로 근거 ID는 링크가 아니라 텍스트로만 적는다. 파일에 적는 근거: 정해지지 않음. 문장 하나에 근거가 수백~천 건 붙을 수 있어(SP-3) 전체 ID를 적으면 읽기 어려운 파일이 된다. 기본안(설계 제안): 문장 끝에 근거 건수만 적는다(예: "근거 리뷰 187건"). 개별 근거 확인은 담당자가 시스템에서 하고(prd.md 기능 2), 근거 ID 검사(FR-2.4)는 리포트를 만들 때 시스템 안에서 끝난다. 일부 ID를 적는 안은 고르는 기준을 따로 정해야 해서 쓰지 않는다 | A-7 |
| SQ-15 | 근거 뷰어에 리뷰 제목(title)을 보여줄지. 정해지지 않음. 기본안(설계 제안): 본문이 없을 때만 제목을 대신 보여준다. 확정하면 prd.md FR-2.5를 "본문(본문이 없으면 제목)"으로 고친다. 제목을 보여주면 prd.md NFR-S4·Q-10의 개인정보 점검을 제목 기준으로도 다시 본다. 제목만 있는 리뷰를 근거 허용 목록에서 빼는 안은 근거 개수 결정(SP-3)과 얽혀 있어 따로 정한다. prd.md FR-2.5는 "본문"이라고만 적었고 이 명세도 title을 뺀 채로 읽어 두 문서의 해석은 같다. 다만 제목만 있는 리뷰 13건(실측)이 근거가 되면 뷰어에 보여줄 본문이 비어 있다 | A-4 |
| SQ-16 | 로그 보존 기간과 회전 방식. 정해지지 않음. 로그 위치와 남기지 않는 항목(7.4)은 이미 정했다. 기본안(설계 제안): 일 단위 파일 나누기 + 7일(가정) 보관. 7일은 근거가 없는 값이라 시연·파일럿 기간에 맞춰 조정한다. 크기 기준 회전은 로그 양이 적어 지금은 쓰지 않는다 | 7.3 |
| SQ-17 | A-10 근거 목록의 `page_size` 기본값과 상한, `suggestion_evidence`를 저장할지 계산할지, 목록의 필터 범위. 모두 정해지지 않음. 기본안(설계 제안): `page_size` 기본 50, 상한 200(가정, 근거 없음). `suggestion_evidence`는 저장하지 않고 스냅샷의 허용 목록에서 계산한다. 필터는 `kind`(리뷰·설문)만 둔다 | A-10, 3.2 |
