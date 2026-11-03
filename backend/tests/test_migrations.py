"""Alembic: 임시 SQLite 파일에서 upgrade head와 check가 통과한다. 실제 DB에는 접속하지 않는다."""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def run_alembic(db_file: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}"}  # 환경 값이 .env보다 우선한다
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120
    )


def test_upgrade_head_and_check_pass_on_temp_sqlite(tmp_path):
    db = tmp_path / "mig.db"
    upgrade = run_alembic(db, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr[-500:]
    check = run_alembic(db, "check")
    assert check.returncode == 0, check.stderr[-500:] + check.stdout[-500:]
    heads = run_alembic(db, "heads")
    assert "fd2af39e3e2a" in heads.stdout


def test_downgrade_one_step_and_upgrade_again(tmp_path):
    db = tmp_path / "mig.db"
    assert run_alembic(db, "upgrade", "head").returncode == 0
    assert run_alembic(db, "downgrade", "-1").returncode == 0
    assert run_alembic(db, "upgrade", "head").returncode == 0
