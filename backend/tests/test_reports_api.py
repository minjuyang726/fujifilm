"""A-5, A-6, A-7(HTML 내보내기). 임시 SQLite만 쓰고 모든 값은 가짜다."""

import html
import json
import re

import pytest
from sqlalchemy import select

from app.llm.client import LLMResult
from app.models import ActionSuggestion, Hypothesis, NextSurveyQuestion, Report
from app.services import report_export
from app.services.report_export import ExportError, find_external_references, render_report_html
from tests.test_question_step import QuestionClient, make_report, run_draft, use_client, world  # noqa: F401

SCRIPT_TEXT = '<script>alert("x")</script><img src="http://evil.example/a.png" onerror="boom()">'


def full_report(world, client=None):
    report = make_report(world)
    use_client(client or QuestionClient())
    assert run_draft(world).json()["status"] == "succeeded"
    return report


# ---------- A-5 ----------
def test_report_list_filters_and_counts(world):
    report = full_report(world)
    listing = world.get("/api/reports").json()["reports"]
    assert [r["report_id"] for r in listing] == [report.report_id]
    item = listing[0]
    assert set(item) == {"report_id", "round_id", "family_id", "generated_at", "suggestion_count", "question_count"}
    assert item["suggestion_count"] == 4 and item["question_count"] >= 1 and item["family_id"] == 1
    assert world.get(f"/api/reports?round_id={world.q1.round_id}&family_id=1").json()["reports"] == listing
    assert world.get("/api/reports?family_id=2").json()["reports"] == []
    assert world.get("/api/reports?round_id=abc").status_code == 422


def test_report_list_counts_questions_of_the_latest_draft_only(world):
    report = full_report(world)
    first_count = world.get("/api/reports").json()["reports"][0]["question_count"]
    run_draft(world)  # 초안을 한 번 더 쌓는다
    total = len(world.session.scalars(select(NextSurveyQuestion).where(NextSurveyQuestion.report_id == report.report_id)).all())
    assert total == 2 * first_count
    assert world.get("/api/reports").json()["reports"][0]["question_count"] == first_count


# ---------- A-6 ----------
def test_report_has_action_plan_and_next_survey_together(world):
    report = full_report(world)
    body = world.get(f"/api/reports/{report.report_id}").json()
    assert set(body) == {"report_id", "round", "family", "generated_at", "action_plan", "rank_notice", "next_survey"}
    assert body["round"]["label"] == "2026-Q1" and body["family"] == {"family_id": 1, "name": "일회용 카메라"}
    plan = body["action_plan"]
    assert [p["order_no"] for p in plan] == [1, 2, 3, 4]
    assert set(plan[0]) == {"suggestion_id", "order_no", "sentence", "evidence_count", "has_synthetic", "sources", "card_kind", "area_label", "rank_label",
                            "priority_text", "deliverable_kind", "deliverable_text", "check_question_no"}
    assert plan[0]["has_synthetic"] is True and plan[0]["sources"] == ["합성"] and plan[3]["sources"] == ["실측"]  # 영역 카드 3개(설문) + 쿠팡 리뷰 카드
    assert plan[0]["evidence_count"]["survey"] > 0 and plan[3]["evidence_count"]["review"] > 0
    survey = body["next_survey"]
    assert survey["status"] == "draft" and survey["run_id"] and survey["questions"]
    opportunity, question = survey["questions"][0], survey["questions"][1]
    fields = {"order_no", "text", "type", "options", "form", "items", "low_label", "high_label", "kind", "hypothesis_id", "hypothesis_kind", "hypothesis_statement"}
    assert set(opportunity) == fields and set(question) == fields
    # 영역 확인 문항(코드 템플릿)은 맨 앞이고 가설이 없다
    assert opportunity["order_no"] == 1 and opportunity["kind"] == "opportunity_matrix" and opportunity["hypothesis_id"] is None
    assert opportunity["form"] == "scale10_matrix" and [i["label"] for i in opportunity["items"]] == ["필름·소모품 비용", "현상·인화 대기", "사용법 안내", "결과물 품질"]
    assert (opportunity["low_label"], opportunity["high_label"]) == ("전혀 필요 없음", "매우 필요함") and opportunity["options"] == opportunity["items"]
    hypothesis = world.session.get(Hypothesis, question["hypothesis_id"])
    assert hypothesis.kind == question["hypothesis_kind"] and hypothesis.statement == question["hypothesis_statement"]
    assert question["kind"] == "hypothesis" and (question["low_label"], question["high_label"]) == ("전혀 그렇지 않음", "매우 그러함")
    assert {q["type"] for q in survey["questions"]} <= {"scale10", "scale10_matrix"} and all(q["form"] == q["type"] for q in survey["questions"])
    # R1(표본 적음)은 문항이 없고 별도 목록에 표시 문구와 함께 나온다
    assert [(n["kind"], n["note"]) for n in survey["no_question_hypotheses"]] == [("uncertain", "표본 적음 — 데이터 보강 필요(문항 없음)")]
    assert "표본이 적어" in survey["no_question_hypotheses"][0]["statement"]
    assert survey["no_question_hypotheses"][0]["hypothesis_id"] not in {q["hypothesis_id"] for q in survey["questions"]}


def test_report_shows_only_the_latest_draft_run(world):
    report = full_report(world)
    first = world.get(f"/api/reports/{report.report_id}").json()["next_survey"]
    use_client(QuestionClient(mutate=lambda qs: [{**q, "text": "두 번째 초안의 문항인가요?"} for q in qs]))
    second_run = run_draft(world).json()["run_id"]
    latest = world.get(f"/api/reports/{report.report_id}").json()["next_survey"]
    assert latest["run_id"] == second_run != first["run_id"]
    assert all(q["text"] == "두 번째 초안의 문항인가요?" for q in latest["questions"] if q["kind"] == "hypothesis")
    assert latest["questions"][0]["kind"] == "opportunity_matrix"  # 영역 확인 문항은 실행마다 맨 앞에 다시 들어간다


def test_report_reads_question_v3_list_rows_and_question_v4_object_rows_together(world):
    report = make_report(world)
    hypothesis = Hypothesis(snapshot_id=1, round_id=world.q1.round_id, family_id=1, run_id=None, kind="uncertain", statement="진술문", related_row_ids=["survey:q06:2"])
    world.session.add(hypothesis)
    world.session.flush()
    legacy_options = [{"code": "1", "label": "여행"}, {"code": "2", "label": "모임"}]
    world.session.add_all([
        NextSurveyQuestion(report_id=report.report_id, hypothesis_id=hypothesis.hypothesis_id, run_id=77, order_no=1, text="예전 문항인가요?",
                           type="single", options_json=legacy_options, status="draft"),  # question-v3: 목록
        NextSurveyQuestion(report_id=report.report_id, hypothesis_id=hypothesis.hypothesis_id, run_id=77, order_no=2, text="예전 척도 문항인가요?",
                           type="scale5", options_json=[{"code": str(i), "label": f"{i}점"} for i in range(1, 6)], status="draft"),
        NextSurveyQuestion(report_id=report.report_id, hypothesis_id=hypothesis.hypothesis_id, run_id=77, order_no=3, text="새 문항인가요?", type="scale10_matrix",
                           options_json={"kind": "hypothesis", "low_label": "낮음", "high_label": "높음", "items": legacy_options}, status="draft"),  # question-v4: 객체
        NextSurveyQuestion(report_id=report.report_id, hypothesis_id=None, run_id=77, order_no=4, text="눈금 하나인가요?", type="scale10",
                           options_json={"kind": "hypothesis", "low_label": "낮음", "high_label": "높음", "items": []}, status="draft"),
    ])
    world.session.commit()
    questions = world.get(f"/api/reports/{report.report_id}").json()["next_survey"]["questions"]
    legacy, scale5, matrix, bar = questions
    assert (legacy["form"], legacy["items"], legacy["low_label"], legacy["high_label"], legacy["kind"]) == ("single", legacy_options, None, None, "hypothesis")
    assert legacy["options"] == legacy_options and legacy["type"] == "single"  # 기존 필드는 그대로다
    assert scale5["form"] == "scale5" and len(scale5["items"]) == 5 and scale5["low_label"] is None
    assert (matrix["form"], matrix["items"], matrix["low_label"], matrix["high_label"]) == ("scale10_matrix", legacy_options, "낮음", "높음")
    assert matrix["options"] == legacy_options
    assert bar["form"] == "scale10" and bar["items"] == [] and bar["hypothesis_id"] is None and bar["hypothesis_kind"] == "opportunity"
    document = world.get(f"/api/reports/{report.report_id}/export?format=html")
    assert document.status_code == 200 and "눈금 하나인가요?" in document.text and "예전 문항인가요?" in document.text  # 내보내기 입력도 두 형식을 읽는다


def test_report_without_a_draft_has_an_empty_question_list(world):
    report = make_report(world)
    body = world.get(f"/api/reports/{report.report_id}").json()
    assert body["next_survey"] == {"status": "draft", "run_id": None, "questions": [], "no_question_hypotheses": []} and len(body["action_plan"]) == 4


def test_report_errors(world):
    assert world.get("/api/reports/9999").json()["error"]["code"] == "NOT_FOUND"
    assert world.get("/api/reports/abc").status_code == 422


# ---------- A-7 ----------
def test_export_returns_a_standalone_html_attachment(world):
    report = full_report(world)
    response = world.get(f"/api/reports/{report.report_id}/export?format=html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-disposition"] == f'attachment; filename="report-{report.report_id}.html"'
    document = response.text
    assert document.startswith("<!doctype html>") and "<style>" in document
    body = world.get(f"/api/reports/{report.report_id}").json()
    for item in body["action_plan"]:
        if item["card_kind"] == "area":  # 영역 카드는 라벨·우선순위 문장·산출물 본문으로 나뉘어 나온다
            for field in ("area_label", "priority_text", "deliverable_text", "rank_label"):
                assert html.escape(item[field]) in document
        else:
            assert html.escape(item["sentence"]) in document  # 쿠팡 리뷰 카드와 이전 형식 문장은 그대로 나온다
    assert "합성" in document and "실측" in document and "초안" in document
    assert "회차 공통 합성 응답(회차당 100건)" in document
    assert "표본 적음 — 데이터 보강 필요(문항 없음)" in document and "문항이 없는 가설" in document
    assert re.search(r"근거 리뷰 \d+건", document) and re.search(r"근거 설문 \d+건\(합성\)", document)
    assert "일회용 카메라" in document and "2026-Q1" in document and "다음 회차 설문지" in document
    for question in body["next_survey"]["questions"]:
        assert question["text"] in document


def test_export_has_no_external_references_no_ids_and_no_review_text(world):
    report = full_report(world)
    document = world.get(f"/api/reports/{report.report_id}/export?format=html").text
    assert find_external_references(document) == []
    for forbidden in ("src=", "href=", "url(", "http://", "https://", "<script", "<link", "<img", "@import"):
        assert forbidden not in document
    for forbidden in ("author", "review_text", "variant", "evidence_id", "review_id", "response_id", "row_id", "survey:q", "voc:"):
        assert forbidden not in document  # 근거 ID와 행 ID는 파일에 없다
    # 근거는 건수뿐이다: 1,000 이하의 숫자만 있고 ID 목록 같은 긴 숫자열이 없다
    assert not re.search(r"\d+\s*,\s*\d+\s*,\s*\d+", document)


def test_export_escapes_everything_that_the_llm_wrote(world):
    report = make_report(world)
    world.session.add(Hypothesis(snapshot_id=1, round_id=world.q1.round_id, family_id=1, run_id=None, kind="uncertain",
                                 statement=SCRIPT_TEXT, related_row_ids=["voc:judged:count"]))
    world.session.flush()
    hid = world.session.scalar(select(Hypothesis.hypothesis_id).where(Hypothesis.statement == SCRIPT_TEXT))
    world.session.add(NextSurveyQuestion(report_id=report.report_id, hypothesis_id=hid, run_id=1, order_no=1, text=SCRIPT_TEXT,
                                         type="single", options_json=[{"code": "1", "label": SCRIPT_TEXT}, {"code": "2", "label": "<b>굵게</b>"}], status="draft"))
    world.session.commit()
    document = world.get(f"/api/reports/{report.report_id}/export?format=html").text
    assert "<script" not in document and "<img" not in document and "<b>" not in document
    assert "&lt;script&gt;" in document and "&lt;b&gt;" in document
    # 이스케이프된 글 속의 "http://", "src=", "onerror="는 마크업이 아니므로 외부 참조로 세지 않는다
    assert find_external_references(document) == []
    assert "&lt;img src=&quot;http://evil.example/a.png&quot;" in document


def test_export_format_errors_and_missing_report(world):
    report = full_report(world)
    base = f"/api/reports/{report.report_id}/export"
    assert world.get(base).status_code == 422 and world.get(base).json()["error"]["code"] == "VALIDATION_ERROR"
    for bad in ("pdf", "HTML", "", "docx"):
        response = world.get(f"{base}?format={bad}")
        assert response.status_code == 400 and response.json()["error"]["code"] == "UNSUPPORTED_FORMAT"
    assert world.get("/api/reports/9999/export?format=html").json()["error"]["code"] == "NOT_FOUND"


# ---------- 외부 참조 검사기 ----------
@pytest.mark.parametrize(
    "snippet",
    ['<img src="a.png">', '<a href="x">링크</a>', '<div style="background:url(a.png)">x</div>', "<style>@import 'a.css';</style>",
     "<style>body{background:url(a.png)}</style>", "<style>a{background:url( http://e/x.png )}</style>",
     "<script>1</script>", '<link rel="stylesheet" href="a">', '<div onclick="x()">x</div>', "<iframe></iframe>",
     '<p title="http://example.com">x</p>', "<video src='a.mp4'></video>"],
)
def test_external_reference_detector_catches_each_markup_pattern(snippet):
    assert find_external_references(f"<html><body>{snippet}</body></html>")


@pytest.mark.parametrize("text", ["http://example.com 은 글일 뿐", "src=abc 와 href=abc", "url(abc) onclick=1", "&lt;img src=&quot;x&quot;&gt;"])
def test_plain_text_mentions_are_not_references(text):
    assert find_external_references(f"<html><body><p>{text}</p></body></html>") == []


def test_plain_document_has_no_external_reference():
    assert find_external_references("<!doctype html><html><head><style>body{margin:0}</style></head><body><p>안녕</p></body></html>") == []


def test_export_is_refused_when_the_document_would_contain_an_external_reference(world, monkeypatch):
    report = full_report(world)
    monkeypatch.setattr(report_export, "STYLE", "body{background:url(http://evil.example/x.png)}")
    response = world.get(f"/api/reports/{report.report_id}/export?format=html")
    assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "evil" not in response.text


# ---------- 카드 구조화(API) ----------
AREA_SENTENCE = "합성 설문 기준 '{label}' 영역 — 이 영역을 개선 희망으로 고른 응답자는 33.0%이며 {rank}입니다. ▸ 산출물(FAQ 초안): 답변 초안입니다. 기간은 [확인 필요]입니다."
VOC_SENTENCE = "쿠팡 리뷰 기준(실측) — 선택한 회차의 리뷰는 63건이고, 그중 제목·본문 없음이 50건, 판정이 끝난 글이 7건이다. 판정 표본이 적어 영역 우선순위는 설문 기준으로만 정했다."
LEGACY_SENTENCE = "합성 설문에서 추천 응답이 49건이다."


def set_sentences(world, report, sentences):
    rows = world.session.scalars(select(ActionSuggestion).where(ActionSuggestion.report_id == report.report_id).order_by(ActionSuggestion.order_no)).all()
    for row, sentence in zip(rows, sentences):
        row.sentence = sentence
    world.session.commit()


def area(label, rank):
    return AREA_SENTENCE.format(label=label, rank=rank)


def test_report_api_splits_area_voc_and_legacy_sentences_and_keeps_the_sentence_field(world):
    report = make_report(world)
    set_sentences(world, report, [area("필름·소모품 비용", "1순위"), LEGACY_SENTENCE, VOC_SENTENCE, "합성 설문 기준 '라벨' 영역 — 깨진 형식"])
    plan = world.get(f"/api/reports/{report.report_id}").json()["action_plan"]
    first, legacy, voc, broken = plan
    assert (first["card_kind"], first["area_label"], first["rank_label"], first["deliverable_kind"]) == ("area", "필름·소모품 비용", "1순위", "FAQ 초안")
    assert first["priority_text"] == "이 영역을 개선 희망으로 고른 응답자는 33.0%이며 1순위입니다."
    assert first["deliverable_text"] == "답변 초안입니다. 기간은 [확인 필요]입니다." and first["sentence"] == area("필름·소모품 비용", "1순위")
    assert (legacy["card_kind"], legacy["priority_text"], legacy["area_label"], legacy["deliverable_text"]) == ("legacy", LEGACY_SENTENCE, None, None)
    assert (voc["card_kind"], voc["priority_text"], voc["check_question_no"]) == ("voc", VOC_SENTENCE, None)
    assert broken["card_kind"] == "legacy" and broken["priority_text"] == "합성 설문 기준 '라벨' 영역 — 깨진 형식"
    # 액션플랜 API도 같은 필드를 준다
    sentences = world.get(f"/api/families/1/action-plan?round_id={world.q1.round_id}").json()["action_plan"]
    assert [(s["card_kind"], s["rank_label"]) for s in sentences] == [("area", "1순위"), ("legacy", None), ("voc", None), ("legacy", None)]
    assert sentences[0]["area_label"] == "필름·소모품 비용" and sentences[0]["sentence"] == plan[0]["sentence"]


def test_check_question_number_points_at_the_opportunity_question_of_the_same_report(world):
    report = make_report(world)
    set_sentences(world, report, [area("필름·소모품 비용", "1순위"), area("결과물 품질", "2순위"), VOC_SENTENCE, LEGACY_SENTENCE])
    before = world.get(f"/api/reports/{report.report_id}").json()["action_plan"]
    assert all(item["check_question_no"] is None for item in before)  # 아직 문항 초안이 없다
    use_client(QuestionClient())
    assert run_draft(world).json()["status"] == "succeeded"
    after = world.get(f"/api/reports/{report.report_id}").json()
    assert [item["check_question_no"] for item in after["action_plan"]] == [1, 1, None, None]  # 영역 카드에만 붙는다
    assert after["next_survey"]["questions"][0]["kind"] == "opportunity_matrix"
    plan = world.get(f"/api/families/1/action-plan?round_id={world.q1.round_id}").json()["action_plan"]
    assert [item["check_question_no"] for item in plan] == [1, 1, None, None]


def test_check_question_number_follows_the_position_of_the_opportunity_question(world):
    report = make_report(world)
    set_sentences(world, report, [area("필름·소모품 비용", "1순위"), VOC_SENTENCE, LEGACY_SENTENCE, LEGACY_SENTENCE])
    for order_no, (kind, form) in enumerate((("hypothesis", "scale10"), ("hypothesis", "scale10"), ("opportunity_matrix", "scale10_matrix")), start=1):
        world.session.add(NextSurveyQuestion(
            report_id=report.report_id, hypothesis_id=None, run_id=5, order_no=order_no, text=f"문항 {order_no}", type=form, status="draft",
            options_json={"kind": kind, "low_label": "낮음", "high_label": "높음", "items": []}))
    world.session.commit()
    assert world.get(f"/api/reports/{report.report_id}").json()["action_plan"][0]["check_question_no"] == 3


def test_rank_notice_when_every_area_is_joint_first(world):
    report = make_report(world)
    set_sentences(world, report, [area("필름·소모품 비용", "공동 1순위"), area("결과물 품질", "공동 1순위"), area("현상·인화 대기", "공동 1순위"), VOC_SENTENCE])
    use_client(QuestionClient())
    run_draft(world)
    notice = world.get(f"/api/reports/{report.report_id}").json()["rank_notice"]
    assert notice == ("합성 설문(응답 100건)에서는 상위 영역의 선택 비율 차이가 우연 범위라 순위를 가리지 못했습니다. "
                      "다음 회차 문항 1번(영역별 눈금)으로 순위를 가립니다.")
    assert world.get(f"/api/families/1/action-plan?round_id={world.q1.round_id}").json()["rank_notice"] == notice


def test_rank_notice_without_a_check_question_omits_the_question_number(world):
    report = make_report(world)
    set_sentences(world, report, [area("필름·소모품 비용", "공동 1순위"), area("결과물 품질", "공동 1순위"), area("현상·인화 대기", "공동 1순위"), VOC_SENTENCE])
    assert world.get(f"/api/reports/{report.report_id}").json()["rank_notice"] == (
        "합성 설문(응답 100건)에서는 상위 영역의 선택 비율 차이가 우연 범위라 순위를 가리지 못했습니다.")


def test_rank_notice_when_only_some_areas_are_joint(world):
    report = make_report(world)
    set_sentences(world, report, [area("필름·소모품 비용", "공동 1순위"), area("결과물 품질", "공동 1순위"), area("현상·인화 대기", "3순위"), VOC_SENTENCE])
    assert world.get(f"/api/reports/{report.report_id}").json()["rank_notice"] == "일부 영역은 차이가 우연 범위라 공동 순위로 표시했습니다."
    set_sentences(world, report, [area("필름·소모품 비용", "1순위"), area("결과물 품질", "공동 2순위"), area("현상·인화 대기", "공동 2순위"), VOC_SENTENCE])
    assert world.get(f"/api/reports/{report.report_id}").json()["rank_notice"] == "일부 영역은 차이가 우연 범위라 공동 순위로 표시했습니다."


def test_rank_notice_is_null_without_area_cards_or_without_joint_ranks(world):
    report = make_report(world)
    set_sentences(world, report, [LEGACY_SENTENCE, VOC_SENTENCE, LEGACY_SENTENCE, LEGACY_SENTENCE])
    assert world.get(f"/api/reports/{report.report_id}").json()["rank_notice"] is None  # 영역 카드가 없다
    set_sentences(world, report, [area("필름·소모품 비용", "1순위"), area("결과물 품질", "2순위"), area("현상·인화 대기", "3순위"), VOC_SENTENCE])
    assert world.get(f"/api/reports/{report.report_id}").json()["rank_notice"] is None  # 모두 구분된다
    assert world.get(f"/api/families/1/action-plan?round_id={world.q1.round_id}").json()["rank_notice"] is None


def test_a_report_mixing_both_formats_reads_without_error(world):
    """이전 형식 문장·문항(suggest-v3, question-v3)과 새 형식(카드, 눈금 문항)이 한 리포트에 섞여 있어도 정상 응답한다."""
    report = make_report(world)
    set_sentences(world, report, [area("필름·소모품 비용", "공동 1순위"), LEGACY_SENTENCE, VOC_SENTENCE, LEGACY_SENTENCE])
    hypothesis = Hypothesis(snapshot_id=1, round_id=world.q1.round_id, family_id=1, run_id=None, kind="uncertain", statement="진술문", related_row_ids=["survey:q06:2"])
    world.session.add(hypothesis)
    world.session.flush()
    world.session.add_all([
        NextSurveyQuestion(report_id=report.report_id, hypothesis_id=hypothesis.hypothesis_id, run_id=9, order_no=1, text="예전 문항인가요?", type="single",
                           options_json=[{"code": "1", "label": "여행"}], status="draft"),
        NextSurveyQuestion(report_id=report.report_id, hypothesis_id=None, run_id=9, order_no=2, text="확인 문항인가요?", type="scale10_matrix", status="draft",
                           options_json={"kind": "opportunity_matrix", "low_label": "전혀 필요 없음", "high_label": "매우 필요함", "items": [{"code": "1", "label": "여행"}]}),
    ])
    world.session.commit()
    response = world.get(f"/api/reports/{report.report_id}")
    assert response.status_code == 200
    body = response.json()
    assert [item["card_kind"] for item in body["action_plan"]] == ["area", "legacy", "voc", "legacy"]
    assert body["action_plan"][0]["check_question_no"] == 2
    assert [q["form"] for q in body["next_survey"]["questions"]] == ["single", "scale10_matrix"]
    assert world.get(f"/api/reports/{report.report_id}/export?format=html").status_code == 200
    assert world.get(f"/api/families/1/action-plan?round_id={world.q1.round_id}").status_code == 200


# ---------- 내보내기: 카드 구조와 눈금 막대 ----------
def export_of(world, report):
    response = world.get(f"/api/reports/{report.report_id}/export?format=html")
    assert response.status_code == 200
    return response.text


def test_export_renders_cards_notice_draft_box_and_check_question(world):
    report = full_report(world)
    set_sentences(world, report, [area("필름·소모품 비용", "공동 1순위"), area("결과물 품질", "공동 1순위"), area("현상·인화 대기", "공동 1순위"), VOC_SENTENCE])
    document = export_of(world, report)
    assert document.count('<li class="card">') == 3 and "필름·소모품 비용 영역" in document and "결과물 품질 영역" in document
    assert document.count("AI가 작성한 초안") == 3 and document.count("검토·수정이 필요한 초안입니다") == 3
    assert document.count("확인 문항: 다음 회차 문항 1번") == 3
    assert document.count("공동 1순위") >= 3 and 'class="badge">공동 1순위</span>' in document
    assert "합성 설문(응답 100건)에서는 상위 영역의 선택 비율 차이가 우연 범위라 순위를 가리지 못했습니다." in document and 'class="notice rank-notice"' in document
    assert "FAQ 초안" in document and "답변 초안입니다. 기간은 [확인 필요]입니다." in document
    assert VOC_SENTENCE in document  # 쿠팡 리뷰 카드는 기존 모양
    assert '<span class="badge">합성</span>' in document and re.search(r"근거 설문 \d+건\(합성\)", document)
    assert find_external_references(document) == []


def test_export_draws_scale_bars_only_for_scale_questions(world):
    report = full_report(world)
    questions = world.get(f"/api/reports/{report.report_id}").json()["next_survey"]["questions"]
    expected = sum(1 if q["form"] == "scale10" else len(q["items"]) for q in questions if q["form"] in ("scale10", "scale10_matrix"))
    document = export_of(world, report)
    assert document.count('<div class="scale" role="img"') == expected and expected >= 5
    assert "응답용 화면이 아닌 문항 미리보기입니다." in document
    # 눈금은 숫자와 양끝 라벨을 함께 적는다: 0부터 10까지 11개 눈금, 양끝 '0 낮은 라벨', '10 높은 라벨'
    assert document.count("<i></i>") == 11 * expected
    assert document.count("<span>0 전혀 그렇지 않음</span>") + document.count("<span>0 전혀 필요 없음</span>") == expected
    assert "<span>10 매우 그러함</span>" in document and "<span>10 매우 필요함</span>" in document
    assert "linear-gradient" in document and "break-inside:avoid" in document and "print-color-adjust:exact" in document
    # 영역 확인 문항 표시와 항목 이름
    assert "액션 카드의 확인 문항" in document and "결과물 품질" in document
    assert find_external_references(document) == []


def test_export_has_no_scale_bar_for_older_question_formats(world):
    report = make_report(world)
    hypothesis = Hypothesis(snapshot_id=1, round_id=world.q1.round_id, family_id=1, run_id=None, kind="uncertain", statement="진술문", related_row_ids=["survey:q06:2"])
    world.session.add(hypothesis)
    world.session.flush()
    world.session.add_all([
        NextSurveyQuestion(report_id=report.report_id, hypothesis_id=hypothesis.hypothesis_id, run_id=3, order_no=1, text="예전 5점 문항인가요?", type="scale5",
                           options_json=[{"code": str(i), "label": f"{i}점"} for i in range(1, 6)], status="draft"),
        NextSurveyQuestion(report_id=report.report_id, hypothesis_id=hypothesis.hypothesis_id, run_id=3, order_no=2, text="예전 선택 문항인가요?", type="single",
                           options_json=[{"code": "1", "label": "여행"}, {"code": "2", "label": "모임"}], status="draft"),
    ])
    world.session.commit()
    document = export_of(world, report)
    assert 'class="scale"' not in document and "응답용 화면이 아닌" not in document and "<i></i>" not in document
    assert "1점부터 5점까지 고르기" in document and "<li>여행</li>" in document and "5점 척도" in document and "하나 고르기" in document


def test_export_of_an_older_report_keeps_the_old_look(world):
    report = make_report(world)
    set_sentences(world, report, [LEGACY_SENTENCE, VOC_SENTENCE, LEGACY_SENTENCE, LEGACY_SENTENCE])
    document = export_of(world, report)
    assert document.count("<li>합성 설문에서 추천 응답이 49건이다.") == 3 and f"<li>{VOC_SENTENCE}" in document
    for absent in ('class="card"', "AI가 작성한 초안", "확인 문항:", "rank-notice", 'class="scale"'):
        assert absent not in document
    assert "초안" in document and "합성" in document and "다음 회차 설문지" in document
    assert find_external_references(document) == []


def test_export_marks_drafts_and_synthetic_in_every_card_and_stays_free_of_external_references(world):
    report = full_report(world)
    set_sentences(world, report, [area("필름·소모품 비용", "1순위"), area("결과물 품질", "2순위"), area("현상·인화 대기", "3순위"), VOC_SENTENCE])
    document = export_of(world, report)
    assert "rank-notice" not in document  # 모두 구분되면 안내가 없다
    assert document.count("AI가 작성한 초안") == 3 and document.count('<span class="badge">합성</span>') >= 3
    assert "<h2>다음 회차 설문지<span class=\"badge\">초안</span></h2>" in document
    assert find_external_references(document) == []
    for forbidden in ("<script", "<img", "<link", "src=", "href=", "onclick", "@import", "url("):
        assert forbidden not in document
