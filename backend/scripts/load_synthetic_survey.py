"""합성 설문 파일을 survey_question, survey_response, survey_answer에 적재한다.

backend 폴더에서 실행한다.
  python scripts/load_synthetic_survey.py --check-only   # 파일만 검사한다(DB에 접속하지 않음)
  python scripts/load_synthetic_survey.py                # DATABASE_URL이 가리키는 DB에 적재한다

- 입력 기본값: database/data/synthetic_survey.json (scripts/generate_synthetic_survey.py가 만든다)
- 여러 번 실행해도 행이 늘지 않는다: 회차는 label로 upsert하고, 합성 응답은 지우고 다시 넣는다.
- is_synthetic이 거짓인 행과 label이 '[파일럿-임시]'로 시작하는 회차는 건드리지 않는다.
- 출력에는 건수만 있다.
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import make_engine  # noqa: E402
from app.models import Round, SurveyAnswer, SurveyQuestion, SurveyResponse  # noqa: E402
from app.services.survey_load import load_synthetic_survey  # noqa: E402
from app.services.synthetic_survey import validate_dataset  # noqa: E402

DEFAULT_IN = BACKEND_DIR.parent / "database" / "data" / "synthetic_survey.json"


def table_counts(session: Session) -> dict:
    return {
        "round": session.scalar(select(func.count()).select_from(Round)),
        "survey_question": session.scalar(select(func.count()).select_from(SurveyQuestion)),
        "survey_response": session.scalar(select(func.count()).select_from(SurveyResponse)),
        "survey_answer": session.scalar(select(func.count()).select_from(SurveyAnswer)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--in", dest="path", type=Path, default=DEFAULT_IN)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.path.read_text(encoding="utf-8"))
    validate_dataset(data)
    print(f"파일 검사 통과: 회차 {len(data['rounds'])}개, 응답 {sum(len(r['responses']) for r in data['rounds'])}건")
    if args.check_only:
        return 0

    engine = make_engine()
    print(f"대상 DB: {engine.dialect.name}")
    with Session(engine) as session:
        with session.begin():
            loaded = load_synthetic_survey(session, data)
        print("적재한 건수:", loaded)
        print("테이블 전체 건수:", table_counts(session))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
