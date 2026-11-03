"""next survey question scale10 types

next_survey_question의 type CHECK 제약(ck_next_survey_question_type)에 scale10, scale10_matrix를 허용한다(question-v4).
영역 확인 문항은 가설이 없는 코드 템플릿이라 hypothesis_id를 NULL로 둘 수 있게 한다(NOT NULL 해제).
컬럼은 추가하지 않는다. 새 형식의 양끝 라벨·항목·종류는 기존 options_json 컬럼에 객체로 담는다.

downgrade는 새 형식(scale10, scale10_matrix) 행이나 hypothesis_id가 NULL인 행이 하나라도 있으면
데이터를 지우거나 바꾸지 않고 명시적 오류로 중단한다.

Revision ID: b3defd1eaa82
Revises: c50aa015e072
Create Date: 2026-11-03 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3defd1eaa82'
down_revision: Union[str, Sequence[str], None] = 'c50aa015e072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "next_survey_question"
CONSTRAINT = "ck_next_survey_question_type"
OLD_VALUES = "type IN ('scale5', 'single', 'multi')"
NEW_VALUES = "type IN ('scale5', 'single', 'multi', 'scale10', 'scale10_matrix')"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_="check")
        batch_op.create_check_constraint(CONSTRAINT, NEW_VALUES)
        batch_op.alter_column("hypothesis_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    new_form_rows = bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE type IN ('scale10', 'scale10_matrix')")).scalar()
    no_hypothesis_rows = bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE hypothesis_id IS NULL")).scalar()
    if new_form_rows or no_hypothesis_rows:
        raise RuntimeError(
            f"downgrade를 중단합니다: 새 형식(scale10, scale10_matrix) 행 {new_form_rows}건, hypothesis_id가 NULL인 행 {no_hypothesis_rows}건이 있습니다. "
            "데이터를 지우거나 바꾸지 않았습니다. 해당 행을 직접 정리한 뒤 다시 실행하세요."
        )
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.alter_column("hypothesis_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint(CONSTRAINT, type_="check")
        batch_op.create_check_constraint(CONSTRAINT, OLD_VALUES)
