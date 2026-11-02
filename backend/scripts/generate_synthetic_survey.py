"""합성 설문 데이터를 만들어 파일로 쓴다. DB와 네트워크를 쓰지 않는다.

backend 폴더에서 실행한다.
  python scripts/generate_synthetic_survey.py [--out 경로]

- 기본 출력: database/data/synthetic_survey.json (database/data/는 추적하지 않는다, spec.md SQ-11)
- 임의 설정, 시연용, 성과로 쓰지 않음. 같은 seed면 같은 바이트가 나온다.
- 출력에는 건수와 sha256만 있다.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.synthetic_survey import SEED, generate, validate_dataset  # noqa: E402

DEFAULT_OUT = BACKEND_DIR.parent / "database" / "data" / "synthetic_survey.json"


def render(data: dict) -> bytes:
    """같은 데이터는 항상 같은 바이트가 되도록 키를 정렬하고 줄바꿈은 LF로 고정한다."""
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    data = generate(SEED)
    validate_dataset(data)
    payload = render(data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(payload)
    print(f"seed {SEED}, 회차 {len(data['rounds'])}개, 응답 {sum(len(r['responses']) for r in data['rounds'])}건")
    print(f"sha256 {hashlib.sha256(payload).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
