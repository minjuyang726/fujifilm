> 위치 안내: CLAUDE.md와 docs/spec.md는 n8n 워크플로 파일 위치를 `backend/n8n/`으로 적고 있으나, 이 워크플로우는 `docs/n8n/`에 있다.

# n8n 워크플로우: 파이프라인 호출

n8n은 기존 FastAPI 파이프라인을 순서대로 호출하는 조정자다. 계산과 OpenAI 호출, 비용 가드는 모두 FastAPI 안에 있고, n8n에서 OpenAI를 직접 부르지 않는다. 이 폴더의 파일은 새로 만든 것이며 `backend/app`, `frontend`, DB, 테스트, 설정값은 바꾸지 않았다.

상태: 파일 작성과 코드 대조까지만 했다. n8n에 가져와 실행해 본 적은 없다(미확인).

## 파일

| 파일 | 내용 |
| --- | --- |
| `workflow.json` | n8n 워크플로우(내보내기 형식). 키, 토큰, 웹훅 주소, 자격 증명을 넣지 않았다 |
| `README.md` | 이 문서 |

## 실행 전 지켜야 할 것

- n8n과 FastAPI는 이 컴퓨터(localhost)에서만 쓴다. 인증이 없다(spec.md 7절, NFR-S1). 터널, 외부 공개, 공개 웹훅 설정은 하지 않는다.
- OpenAI를 부르는 단계는 `action-suggestions`와 `next-survey-draft`다. 실제 실행은 사용자가 승인한 뒤에만 한다. `Config` 노드의 `approveOpenAI`는 기본이 `false`이고, 이 값이 `true`가 아니면 `Gate OpenAI` 노드가 오류로 멈춘다. 승인한 뒤에만 `true`로 바꾼다.
- 하루 OpenAI 비용 합계 $5 이내를 지킨다. 실행 전에 `llm_call_log`로 오늘 누적을 합산하고, 이번 실행의 예상 비용(`python scripts/estimate_suggestion_cost.py`, `python scripts/estimate_question_cost.py`의 "상한 합")을 더해 $5를 넘을 것 같으면 실행하지 않는다. `llm_call_log`에는 비용 열이 없어 토큰 수에 단가(`backend/.env`)를 곱해 구한다.
  ```sql
  select call_type, count(*) as calls, sum(input_tokens) as input_tokens, sum(output_tokens) as output_tokens
  from llm_call_log
  where created_at >= date_trunc('day', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'
  group by call_type;
  ```
- 비용 한도 환경 값(`AD_JUDGEMENT_COST_LIMIT_USD`, `SUGGESTION_COST_LIMIT_USD`, `QUESTION_COST_LIMIT_USD`)은 바꾸지 않는다. 기본 $0.5이며 단계마다 FastAPI가 호출 전에 확인한다.

## 로컬 실행

1. FastAPI를 켠다(backend 폴더에서): `uvicorn app.main:app --port 8000`
2. n8n을 켠다. 둘 중 하나를 쓴다.
   - Node.js가 있으면: `npx n8n` (기본 화면 `http://localhost:5678`)
   - Docker가 있으면: `docker run -it --rm -p 127.0.0.1:5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n` (포트를 127.0.0.1에만 연다)
   - Docker에서 FastAPI에 닿으려면 `Config`의 `baseUrl`을 `http://host.docker.internal:8000`으로 바꿔야 할 수 있다(미확인).
3. n8n 화면에서 새 워크플로우를 만들고 메뉴의 "Import from File"로 `workflow.json`을 가져온다.
4. `Config` 노드의 `baseUrl`(기본 `http://localhost:8000`)을 확인한다.

## 노드별 설명

| 노드 | 라우트 / 하는 일 | OpenAI |
| --- | --- | --- |
| Manual Trigger | 수동 시작 | 없음 |
| Config | `baseUrl`, `approveOpenAI` 값을 둔다 | 없음 |
| GET families | `GET /api/families` | 없음 |
| GET rounds | `GET /api/rounds` | 없음 |
| Build combos | 제품군 × 회차 조합을 만든다 | 없음 |
| Loop combos | 조합을 하나씩 처리한다(Split In Batches, 크기 1) | 없음 |
| POST analysis-snapshot | `POST /api/rounds/{round_id}/pipeline/analysis-snapshot`, 본문 `{"family_id": 정수}` | 없음 |
| Gate OpenAI | `approveOpenAI`가 `true`가 아니면 멈춘다 | 없음 |
| POST action-suggestions | `POST .../pipeline/action-suggestions`, 같은 본문 | 호출함(비용 가드는 FastAPI) |
| Wait for review | 담당자가 검토한 뒤 재개해야 다음으로 간다(Wait, 웹훅 재개) | 없음 |
| POST next-survey-draft | `POST .../pipeline/next-survey-draft`, 같은 본문 | 호출함(비용 가드는 FastAPI) |
| POST report-assembly | `POST .../pipeline/report-assembly`, 같은 본문. 제안과 문항이 있는지 확인하는 기록만 남긴다 | 없음 |
| GET reports | `GET /api/reports`. 모든 조합이 끝난 뒤 결과 목록을 확인한다 | 없음 |
| Check … (7개) | 각 HTTP 노드 바로 뒤. 200번대가 아니면 응답 본문을 오류 메시지에 담아 멈춘다 | 없음 |

오류 처리: 모든 HTTP 노드는 재시도를 끄고(`retryOnFail: false`), 오류 상태(예: 422 `COST_LIMIT_EXCEEDED`, 500 `PRICE_NOT_CONFIGURED`)도 일단 응답으로 받은 뒤 바로 뒤의 `Check` 노드가 `HTTP 상태 코드`와 응답 본문(`code`, `message`)을 오류로 내며 워크플로우를 멈춘다. 오류 메시지에서 본문을 볼 수 있다.

Wait 노드: 조합마다 한 번씩 멈춘다. 재개 방법(재개 주소가 n8n 화면 어디에 나오는지)은 확인하지 못했다. n8n의 Wait 노드 안내를 따른다. 재개 주소는 localhost 주소이므로 공개하지 않는다.

## 설계 근거 (한 줄씩)

- 조합은 `GET /api/families`와 `GET /api/rounds`로 얻는다. 임시 회차(`[파일럿-임시]`)는 `/api/rounds`가 이미 뺀다.
- `analysis-snapshot`은 제품군 × 회차 단위라 본문에 `family_id`가 필수다(`StepRequest`는 다른 필드를 받지 않는다).
- `action-suggestions`는 스냅샷이 먼저 있어야 하고, `next-survey-draft`는 성공한 액션 제안 리포트가 먼저 있어야 한다. 선행이 없으면 FastAPI가 400 `STEP_NOT_READY`를 낸다.
- `report-assembly`는 새 데이터를 만들지 않고 제안과 문항이 1개 이상인지 확인해 실행 기록만 남긴다.
- Wait 노드를 `action-suggestions`와 `next-survey-draft` 사이에 둔 이유: 담당자가 제안을 본 뒤에 다음 OpenAI 호출을 하게 하려는 것이다.
- 비용 가드는 FastAPI 안에 있어 n8n에 두지 않는다(호출 전 예상 상한 검사, 실행 중 누적 검사).

## 이 흐름에 넣지 않은 것

| 제외 | 이유 |
| --- | --- |
| 광고성 판정(`ad-judgement`) | 본문의 `review_ids`가 필수인데 그 목록을 주는 라우트가 없다. 이를 위해 코드를 추가하지 않는다 |
| 주제 신호(검색 추이) | 구현된 코드가 없다 |
| 응답 취합 | 응답을 받는 라우트가 없고 합성 응답 적재는 CLI(`scripts/load_synthetic_survey.py`)로만 한다 |

## 알려진 한계

- 합성 설문 응답에서 나온 수치는 성과로 쓰지 않고, 화면에서는 "합성" 라벨이 붙는다. 이 워크플로우는 라벨을 바꾸지 않는다.
- `docs/spec.md`와 `CLAUDE.md`는 n8n 워크플로 파일 위치를 `backend/n8n/`으로 적고 있다. 이 파일들은 요청에 따라 `docs/n8n/`에 두었고 두 문서는 바꾸지 않았다.
