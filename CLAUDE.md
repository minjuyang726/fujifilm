# CLAUDE.md

한국후지필름형 정기 설문 폐루프 에이전트. CX 담당자가 제품군별 대시보드로 설문과 외부 VOC를 보고, 제안의 근거를 추적하고, 액션플랜과 다음 회차 설문지가 담긴 회차 리포트를 내보내는 웹 서비스다. 문서와 대화는 한국어로 한다.

## 문서 위치

| 문서 | 내용 |
| --- | --- |
| `docs/service-definition.md` | 사용자, 불편, 핵심 행동 (배경) |
| `docs/mvp.md` | MVP 범위, 제외 범위, 성공 기준 |
| `docs/prd.md` | 기능·데이터·비기능 요구사항 (FR, DR, NFR 번호) |
| `docs/spec.md` | 기술 스택, 폴더 구조, 데이터 모델, API, LLM 호출, 로그 |
| `docs/plan.md` | Phase별 계획, 완료 확인 기준, 일정, 컷 후보 |

폴더: `backend/`(FastAPI), `frontend/`(React), `database/`(`database/data/`는 원본 CSV·합성 결과, 미추적), `docs/`. 루트의 `쿠팡 크롤러/`는 이 프로젝트 범위 밖이므로 건드리지 않는다.

## 작업 규칙

- 작업 전에 관련 문서를 먼저 읽는다. 기능은 prd.md, 구현 계약은 spec.md, 순서와 확인 기준은 plan.md가 기준이다.
- 문서에 없는 기능을 임의로 추가하지 않는다. 필요해 보이면 구현하지 말고 "제안"으로 따로 알려 승인을 받는다.
- 모르는 것은 추측하지 말고 질문한다. 질문은 한 번에 하나씩 한다.
- 한 번에 한 Phase만 작업한다. plan.md의 선행 Phase와 결정 게이트(G1~G5)가 끝나지 않았으면 먼저 알린다.
- 문서의 "확인 필요", "정해지지 않음", "기본안(설계 제안)"은 확정이 아니다. 확정된 것처럼 구현하지 않고, 기본안을 쓸 때는 쓴다고 말한다.
- 커밋과 Git 태그(저장점)는 사용자가 요청할 때만 만든다. 저장점 이름은 plan.md의 Phase 표를 따른다.
- 문서와 구현이 어긋나면 한쪽을 조용히 고치지 말고 알린다.

## 핵심 원칙 (prd.md에서)

- 계산(집계, 비율, 가중치)은 코드가 하고, LLM은 코드가 계산한 표를 서술만 한다. LLM이 수치를 만들거나 바꾸지 않는다 (FR-0.1~0.4).
- 광고성 판정은 글을 삭제하지 않고 가중치(1 − 광고성 확률)만 낮춘다. 가중 집계와 비가중 집계를 모두 보여 준다.
- 제안 문장의 근거는 코드가 붙이고, 근거가 없는 문장은 리포트에 담지 않는다 (FR-2.4, FR-2.6).
- `author`(작성자) 열은 DB에 적재하지 않고 화면과 LLM 입력에도 쓰지 않는다 (NFR-S2).

## 보안 규칙

- 키와 비밀번호(`DATABASE_URL`, `OPENAI_API_KEY` 등)는 `backend/.env`에만 둔다. 채팅, 문서, 커밋, 로그에 쓰지 않는다.
- `backend/.env`는 읽지도, 만들지도, 수정하지도 않는다. 값이 필요하면 사용자에게 직접 넣어 달라고 요청한다. (`.env.example`은 만들 수 있고, 값 없이 항목 이름만 둔다.)
- 저장소에는 `.env.example`만 올린다. n8n의 자격 증명은 내보낸 JSON에 넣지 않는다.
- 로그와 오류 응답에 리뷰 본문(`title`, `review_text`), 작성자, 키, 접속 문자열을 남기지 않는다 (spec.md 7.4).

## 데이터 규칙

- 모든 수치에 **실측 / 가정 / 합성** 중 하나를 표기한다. 출처 없는 수치는 쓰지 않는다.
- 합성 응답에서 나온 수치는 성과로 쓰지 않는다.
- 합성 데이터는 화면 어디에서든 **"합성" 라벨을 고정**으로 붙인다 (FR-1.10, NFR-S3).
- 원본 CSV와 합성 응답 결과는 `database/data/`에 두고 추적하지 않는다. `.gitignore`가 `database/data/`와 `*.csv`를 제외하므로, 데이터 파일을 `git add -f`로 강제로 올리지 않는다.
- 개인정보가 들어 있을 수 있는 데이터(리뷰 본문, 작성자)는 저장소, 채팅, 문서, 로그에 옮겨 쓰지 않는다. 외부 서비스(OpenAI, Supabase)로 보내는 항목은 필요한 열만 허용 목록으로 고른다.
- 법적 적합성(개인정보 보호법, 국외 이전, 크롤링 약관 등)은 코드나 이 문서로 보증할 수 없다. 판단이 필요한 항목은 prd.md Q-17에 두고 전문가 확인을 요청한다.
- **쿠팡 리뷰 수집**: 이미 수집된 CSV만 쓴다. 쿠팡 이용약관을 확인하기 전까지 추가 수집을 하지 않는다.
- **네이버 수집(Phase 0d)**: 네이버 API 약관을 확인하기 전까지 시작하지 않는다.
- **리뷰 본문을 OpenAI로 보내는 일**: 310건 전체 판정은 prd.md Q-17-3이 해결된 뒤에만 한다. 그 전에는 파일럿 100건으로 제한하고 이름이 든 본문은 보내지 않는다. OpenAI의 데이터 사용·보관 조건(학습 사용 여부 등)은 사용자가 직접 확인한다.
- **공모전 제출물**: 리뷰 원문을 넣지 않는다. 집계 수치와 가공한 예시만 쓴다.

## 검증 규칙

- 각 작업은 시작하기 전에 **무엇을, 어디에, 어떻게 확인하는지**를 먼저 말한다. 확인 방법은 plan.md의 해당 Phase "완료 확인 기준"에서 가져오고, 사용자가 직접 확인할 수 있는 방법(브라우저, Supabase Table Editor, 터미널)으로 적는다.
- 작업이 끝나면 확인 결과를 사실대로 보고한다. 실패했거나 건너뛴 것은 그렇게 말한다.
- 테스트는 SQLite로 돌고 Supabase에 접속하지 않는다. LLM 호출은 테스트에서 가짜 응답으로 대체한다.

## 실행 명령

Phase 0a에서 아래 명령을 실제로 실행해 확인했다. "확인 필요"는 아직 확인하지 못한 것이다. 명령은 Windows 기준이고, 가상환경을 켜지 않아도 `backend/.venv/Scripts/python.exe -m …` 형태로 실행할 수 있다.

| 용도 | 명령 | 상태 |
| --- | --- | --- |
| backend 가상환경 만들기 | `python -m venv .venv` (backend에서), Python 3.13 | 확인됨 |
| backend 가상환경 켜기 | PowerShell `.venv\Scripts\Activate.ps1`, Git Bash `source .venv/Scripts/activate` (backend에서) | 켜지 않고 `python.exe`를 직접 쓰는 방식만 확인. 켜는 명령은 확인 필요 |
| backend 패키지 설치 | `pip install -r requirements.txt` (backend에서) | `requirements.txt` 작성함. 이 파일로 새로 설치하는 것은 확인 필요 |
| backend 실행 | `uvicorn app.main:app --port 8000` (backend에서). 개발 중에는 `--reload` 추가 | `/docs`가 200으로 열리는 것을 확인함. `--reload`는 확인 필요 |
| API 문서 화면 | `http://localhost:8000/docs` | 확인됨 |
| backend 테스트 | `pytest` (backend에서). 설정은 `backend/pytest.ini` | 확인됨 (3개 통과, SQLite) |
| Supabase 연결 확인 | `python scripts/check_db.py` (backend에서) | `DATABASE_URL`이 없을 때의 실패 메시지만 확인. 성공 경로는 사용자가 `backend/.env`를 채운 뒤 확인 필요 |
| 마이그레이션 적용 | `alembic upgrade head` (backend에서). 설정은 `backend/alembic.ini`, `backend/migrations/` | 임시 SQLite에서 적용과 `alembic check`를 확인함(Phase 0b). Supabase 적용은 사용자가 실행한 뒤 확인 필요 |
| frontend 패키지 설치 | `npm install` (frontend에서) | 확인됨 |
| frontend 실행 | `npm run dev` (frontend에서), `http://localhost:5173` | 확인됨 (포트 5173 고정) |
| frontend 빌드·점검 | `npm run build`, `npm run lint` (frontend에서) | 확인됨 |
| 리뷰 적재 | `python scripts/load_reviews.py` (backend에서). CSV만 점검하려면 `--check-only` | 임시 SQLite에서 확인함(1,302행, 두 번 실행해도 그대로). Supabase 실행은 사용자가 한 뒤 확인 필요 |
| 파일럿 표본 뽑기 | `python scripts/pilot_sample.py` (backend에서). 층화는 `--stratify product` | 임시 SQLite에서 확인함(310건 중 100건, 같은 seed면 같은 id). DB에서 읽기만 함. 결과는 `database/data/pilot_sample_ids.json`(추적 안 됨) |
| 합성 설문 생성 | `python scripts/generate_synthetic_survey.py` (backend에서). `--out`으로 경로 변경 | 파일만 만든다(DB·네트워크 안 씀). 같은 seed로 두 번 만든 `database/data/synthetic_survey.json`의 sha256이 같음을 확인함(2026-11-03). 파일은 추적 안 됨 |
| 합성 설문 적재 | `python scripts/load_synthetic_survey.py` (backend에서). 파일만 점검하려면 `--check-only` | 임시 SQLite(pytest)와 Supabase에서 확인함(2026-11-03, 두 번 실행해도 행이 늘지 않음). 실행 전에 `alembic upgrade head`가 필요하고 사용자가 실행한다. `[파일럿-임시]` 회차와 `is_synthetic`이 거짓인 행은 건드리지 않는다 |
| 제품군 시드 | `python scripts/seed_families.py` (backend에서). 읽기만 하려면 `--dry-run` | 임시 SQLite(pytest)에서만 확인함. 실행 전에 `alembic upgrade head`(→ `4d7cdf97c911`)가 필요하고 Supabase 실행은 사용자가 한 뒤 확인 필요. 대응표에 없는 상품은 건드리지 않는다 |
| VOC 집계 검증 | `python scripts/verify_voc_dashboard.py` (backend에서) | 읽기 전용. 서비스 코드를 거치지 않은 SQL 집계와 A-3의 voc 응답을 제품군×회차 조합마다 비교하고 숫자만 출력한다. Supabase에서 확인함(2026-11-03, 4개 조합 모두 다른 칸 0) |
| 스냅샷 검증 | `python scripts/verify_snapshot.py` (backend에서). 한 조합만: `--family-id 2 --round-label 2026-Q1` | 읽기 전용(스냅샷을 저장하지 않음). 서비스 코드를 거치지 않은 SQL 집계와 비교한다. Supabase에서 확인함(2026-11-03, 4개 조합 모두 다른 칸 0) |
| 액션 제안 비용 추정 | `python scripts/estimate_suggestion_cost.py` (backend에서) | 읽기 전용, OpenAI 호출 없음. 계수는 가정이다. Supabase에서 실행함(2026-11-03) |
| 스냅샷·액션 제안 실행 | `POST /api/rounds/{round_id}/pipeline/analysis-snapshot`, `POST /api/rounds/{round_id}/pipeline/action-suggestions` (본문 `{"family_id": 정수}`, `/docs` 화면에서), 결과는 `GET /api/runs/{run_id}`, `GET /api/families/{family_id}/action-plan?round_id=` | 가짜 클라이언트로만 확인함. 실행 전에 `alembic upgrade head`(→ `fd2af39e3e2a`)가 필요하다. `action-suggestions`의 실제 호출에는 `backend/.env`의 `OPENAI_MODEL_SUGGEST`, `OPENAI_API_KEY`, 단가 항목이 필요하다. 실제 호출은 사용자 승인 후에 한다 |
| 광고성 판정 실행 | `POST /api/rounds/{round_id}/pipeline/ad-judgement`, `GET /api/runs/{run_id}` (`/docs` 화면에서) | 가짜 클라이언트로만 확인함. 본문의 `review_ids`는 필수이고 파일럿은 표본의 `review_ids`를 넣는다. 실제 실행에는 `backend/.env`의 `OPENAI_API_KEY`, `OPENAI_MODEL_AD`와 `round` 행 하나가 필요하다. 리뷰 데이터를 보내는 실제 호출은 prd.md Q-17-3과 G3 전에는 하지 않는다. 리뷰가 아닌 임의 문장의 시험 호출은 사용자가 허용한 횟수 안에서 예외다 |
| n8n | 워크플로 파일은 `backend/n8n/` | 기본안(설계 제안). 실행 방법은 확인 필요 |

환경 값은 `backend/.env`(비밀 값)와 `frontend/.env`(backend 주소만)에 넣는다. 항목 이름은 각 폴더의 `.env.example`에 있다.
