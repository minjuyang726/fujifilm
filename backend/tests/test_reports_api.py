"""A-5, A-6, A-7(HTML 내보내기). 임시 SQLite만 쓰고 모든 값은 가짜다."""

import json
import re

import pytest
from sqlalchemy import select

from app.llm.client import LLMResult
from app.models import Hypothesis, NextSurveyQuestion, Report
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
    assert item["suggestion_count"] == 2 and item["question_count"] >= 1 and item["family_id"] == 1
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
    assert set(body) == {"report_id", "round", "family", "generated_at", "action_plan", "next_survey"}
    assert body["round"]["label"] == "2026-Q1" and body["family"] == {"family_id": 1, "name": "일회용 카메라"}
    plan = body["action_plan"]
    assert [p["order_no"] for p in plan] == [1, 2]
    assert set(plan[0]) == {"suggestion_id", "order_no", "sentence", "evidence_count", "has_synthetic", "sources"}
    assert plan[0]["has_synthetic"] is True and plan[0]["sources"] == ["합성"] and plan[1]["sources"] == ["실측"]
    assert plan[0]["evidence_count"]["survey"] > 0 and plan[1]["evidence_count"]["review"] > 0
    survey = body["next_survey"]
    assert survey["status"] == "draft" and survey["run_id"] and survey["questions"]
    question = survey["questions"][0]
    assert set(question) == {"order_no", "text", "type", "options", "hypothesis_id", "hypothesis_kind", "hypothesis_statement"}
    hypothesis = world.session.get(Hypothesis, question["hypothesis_id"])
    assert hypothesis.kind == question["hypothesis_kind"] and hypothesis.statement == question["hypothesis_statement"]
    assert {q["type"] for q in survey["questions"]} <= {"scale5", "single", "multi"}
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
    assert all(q["text"] == "두 번째 초안의 문항인가요?" for q in latest["questions"])


def test_report_without_a_draft_has_an_empty_question_list(world):
    report = make_report(world)
    body = world.get(f"/api/reports/{report.report_id}").json()
    assert body["next_survey"] == {"status": "draft", "run_id": None, "questions": [], "no_question_hypotheses": []} and len(body["action_plan"]) == 2


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
        assert item["sentence"] in document  # 한글이라 이스케이프되지 않는다
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
