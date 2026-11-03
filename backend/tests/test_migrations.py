"""Alembic: 임시 SQLite 파일에서 upgrade head와 check가 통과한다. 실제 DB에는 접속하지 않는다."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

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
    assert "b3defd1eaa82" in heads.stdout and "c50aa015e072" not in heads.stdout


def test_downgrade_one_step_and_upgrade_again(tmp_path):
    db = tmp_path / "mig.db"
    assert run_alembic(db, "upgrade", "head").returncode == 0
    assert run_alembic(db, "downgrade", "-1").returncode == 0
    assert run_alembic(db, "upgrade", "head").returncode == 0


# ---------- b3defd1eaa82: next_survey_question type 제약과 hypothesis_id NULL 허용 ----------
def insert_question(db: Path, question_type: str, hypothesis_id):
    import sqlite3

    connection = sqlite3.connect(db)
    try:
        connection.execute(
            "INSERT INTO next_survey_question (report_id, hypothesis_id, run_id, order_no, text, type, options_json, status) "
            "VALUES (1, ?, 1, 1, 'q', ?, '{}', 'draft')",
            (hypothesis_id, question_type),
        )
        connection.commit()
    finally:
        connection.close()


def count_questions(db: Path) -> int:
    import sqlite3

    connection = sqlite3.connect(db)
    try:
        return connection.execute("SELECT COUNT(*) FROM next_survey_question").fetchone()[0]
    finally:
        connection.close()


def test_new_question_types_and_null_hypothesis_are_allowed_after_upgrade(tmp_path):
    import sqlite3

    db = tmp_path / "mig.db"
    assert run_alembic(db, "upgrade", "head").returncode == 0
    insert_question(db, "scale10", 1)
    insert_question(db, "scale10_matrix", None)  # 영역 확인 문항은 가설이 없다
    insert_question(db, "scale5", 1)
    assert count_questions(db) == 3
    with pytest.raises(sqlite3.IntegrityError):
        insert_question(db, "rating", 1)  # 허용 목록 밖의 형식은 여전히 막힌다


def test_downgrade_is_blocked_when_new_form_rows_exist_and_data_is_untouched(tmp_path):
    db = tmp_path / "mig.db"
    assert run_alembic(db, "upgrade", "head").returncode == 0
    insert_question(db, "scale10", 1)
    insert_question(db, "single", 1)
    blocked = run_alembic(db, "downgrade", "-1")
    assert blocked.returncode != 0 and "downgrade를 중단합니다" in blocked.stderr
    assert count_questions(db) == 2  # 지우거나 바꾸지 않았다
    assert "b3defd1eaa82" in run_alembic(db, "current").stdout  # 버전도 그대로다


def test_downgrade_is_blocked_when_a_row_has_no_hypothesis(tmp_path):
    db = tmp_path / "mig.db"
    assert run_alembic(db, "upgrade", "head").returncode == 0
    insert_question(db, "single", None)
    blocked = run_alembic(db, "downgrade", "-1")
    assert blocked.returncode != 0 and "downgrade를 중단합니다" in blocked.stderr and count_questions(db) == 1


def test_downgrade_restores_the_old_constraint_when_only_old_rows_exist(tmp_path):
    import sqlite3

    db = tmp_path / "mig.db"
    assert run_alembic(db, "upgrade", "head").returncode == 0
    insert_question(db, "multi", 1)
    assert run_alembic(db, "downgrade", "-1").returncode == 0
    assert count_questions(db) == 1
    with pytest.raises(sqlite3.IntegrityError):
        insert_question(db, "scale10", 1)  # 이전 제약으로 돌아왔다
    with pytest.raises(sqlite3.IntegrityError):
        insert_question(db, "single", None)  # NOT NULL도 돌아왔다
