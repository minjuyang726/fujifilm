"""A-8(단계 실행)과 A-9(실행 조회). 이 단계는 지금 서버가 요청 안에서 끝까지 실행하고 결과를 돌려준다.

백그라운드 실행(spec.md 4.3절)은 실제 LLM 호출을 붙일 때 정한다.
오류 응답의 통일된 형식(spec.md 7.1절)은 Phase 1에서 만든다. 지금은 detail에 code와 message를 담는다.
"""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.llm.client import LLMClient, LLMConfigError, ModelNotConfigured, build_default_client, get_ad_model_name
from app.llm.cost import CostGuard, Prices, estimate_ad_cost
from app.models import PipelineRun, Review, Round
from app.schemas.pipeline import AdJudgementRequest, RunCreated, RunDetail, as_utc
from app.services.ad_cost import char_counts_to_send
from app.services.ad_judgement import BATCH_SIZE
from app.services.ad_judgement_step import STEP_NAME, run_ad_judgement_step

router = APIRouter(prefix="/api", tags=["pipeline"])


def get_llm_client_factory() -> Callable[[], LLMClient]:
    """실제 클라이언트를 만드는 함수를 돌려준다. 테스트는 이 의존성을 가짜로 바꾼다."""
    return build_default_client


def get_ad_model_provider() -> Callable[[], str]:
    return get_ad_model_name


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.post("/rounds/{round_id}/pipeline/ad-judgement", status_code=201, response_model=RunCreated)
def run_ad_judgement(
    round_id: int,
    body: AdJudgementRequest,
    session: Session = Depends(get_session),
    client_factory: Callable[[], LLMClient] = Depends(get_llm_client_factory),
    model_provider: Callable[[], str] = Depends(get_ad_model_provider),
) -> RunCreated:
    if session.get(Round, round_id) is None:
        raise _error(404, "NOT_FOUND", "회차를 찾을 수 없습니다.")
    max_items = get_settings().ad_judgement_max_items
    review_ids = sorted(set(body.review_ids))
    if len(review_ids) > max_items:
        raise _error(422, "TOO_MANY_REVIEWS", f"한 번에 보낼 수 있는 리뷰는 {max_items}건까지입니다.")
    found = set(session.scalars(select(Review.review_id).where(Review.review_id.in_(review_ids))))
    if len(found) != len(review_ids):
        # 목록과 실제로 보내는 건이 어긋나지 않도록 일부만 처리하지 않고 거절한다. 번호는 응답에 담지 않는다.
        raise _error(422, "UNKNOWN_REVIEW_IDS", f"존재하지 않는 review_id가 {len(review_ids) - len(found)}건 있습니다.")
    try:
        model_name = model_provider()
        client = client_factory()
    except ModelNotConfigured:
        raise _error(500, "MODEL_NOT_CONFIGURED", "광고성 판정 모델이 설정되지 않았습니다.") from None
    except LLMConfigError:
        raise _error(500, "LLM_NOT_CONFIGURED", "OpenAI 키가 설정되지 않았습니다.") from None

    # 비용 가드: 호출 전에 예상 비용 상한을 계산한다. 본문은 가져오지 않고 글자 수만 읽는다.
    settings = get_settings()
    if settings.price_input_per_m is None or settings.price_output_per_m is None:
        raise _error(500, "PRICE_NOT_CONFIGURED", "비용 가드에 필요한 단가가 설정되지 않아 호출하지 않았습니다.")
    prices = Prices(settings.price_input_per_m, settings.price_output_per_m)
    char_counts = char_counts_to_send(session, review_ids)  # 제목 또는 본문이 있는 글의 글자 수만 읽는다
    estimate = estimate_ad_cost(char_counts, BATCH_SIZE, prices)
    limit = settings.ad_judgement_cost_limit_usd
    if estimate.upper_usd > limit:
        raise _error(
            422,
            "COST_LIMIT_EXCEEDED",
            f"예상 비용 상한 ${estimate.upper_usd:.4f}가 한도 ${limit:.2f}를 넘어 호출하지 않았습니다.",
        )
    fallback_call_usd = estimate.one_pass_usd / estimate.calls if estimate.calls else 0.0
    cost_guard = CostGuard(limit, prices, fallback_call_usd)

    run = run_ad_judgement_step(
        session,
        round_id=round_id,
        family_id=body.family_id,
        client=client,
        model_name=model_name,
        max_items=max_items,
        review_ids=review_ids,
        cost_guard=cost_guard,
    )
    return RunCreated(run_id=run.run_id, step=STEP_NAME, status=run.status, started_at=as_utc(run.started_at))


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: int, session: Session = Depends(get_session)) -> RunDetail:
    run = session.get(PipelineRun, run_id)
    if run is None:
        raise _error(404, "NOT_FOUND", "실행 기록을 찾을 수 없습니다.")
    return RunDetail(
        run_id=run.run_id,
        round_id=run.round_id,
        family_id=run.family_id,
        step=run.step,
        status=run.status,
        counters=run.counters or {},
        error_code=run.error_code,
        started_at=as_utc(run.started_at),
        finished_at=as_utc(run.finished_at),
    )
