"""A-7 내보내기: 독립형 HTML 한 파일(SQ-14, 결정 2026-11-03).

- 담는 것: 제품군·회차·생성 시각, 액션플랜(영역 카드: 영역 라벨·순위 배지·우선순위 문장·"AI가 작성한 초안" 상자·확인 문항 번호, 쿠팡 리뷰 카드,
  이전 형식 문장)과 근거 건수(링크 없음), 순위 안내, 다음 회차 설문지("초안" 표시, scale10·scale10_matrix 문항은 0~10 눈금 막대 미리보기), "합성/실측" 출처 표기.
  눈금 막대는 CSS(그라데이션)로 그린 정적 미리보기라 외부 참조가 없고 숫자와 양끝 라벨을 함께 적는다. 인쇄할 때 카드와 막대가 잘리지 않게 break-inside: avoid를 준다.
- 담지 않는 것: 리뷰 본문, 작성자, 근거 ID, 링크, 외부 리소스. 근거는 문장마다 건수로만 적는다.
- 모든 동적 값(LLM이 쓴 문장·문항·선택지, 이름, 가설 진술문)은 html.escape로 이스케이프한다.
- 만든 HTML에 외부 참조(src/href 등 URL 속성, on* 속성, url()/@import/http를 담은 CSS·속성, script/link/iframe/img 등 태그)가 하나라도 있으면 내보내지 않는다(find_external_references).
"""

import html
import re
from html.parser import HTMLParser

NOTICE = (
    "이 리포트의 설문 수치는 합성 응답에서 나온 시연용 수치이며 성과가 아닙니다. "
    "설문은 제품군 구분 없이 회차 공통 합성 응답(회차당 100건)입니다. "
    "외부 VOC 수치는 수집된 쿠팡 리뷰의 실측 집계입니다. 근거는 건수로만 적었고, 개별 근거는 시스템에서 확인합니다."
)
TYPE_LABEL = {"scale5": "5점 척도", "single": "하나 고르기", "multi": "여러 개 고르기", "scale10": "0~10 눈금", "scale10_matrix": "항목별 0~10 눈금"}
SCALE_FORMS = ("scale10", "scale10_matrix")
SCALE_PREVIEW_NOTE = "응답용 화면이 아닌 문항 미리보기입니다."
OPPORTUNITY_MARK = "액션 카드의 확인 문항"
KIND_LABEL = {"uncertain": "불확실 가설", "contradictory": "불일치 가설"}

# 외부 참조 검사는 표준 라이브러리 HTML 파서로 태그와 속성, <style> 내용만 본다. 본문 글(이스케이프된 LLM 출력 포함)은 검사하지 않으므로
# 글 속에 "http://"나 "src=" 같은 문자열이 있어도 내보내기가 막히지 않는다(이스케이프되어 마크업이 아니다).
FORBIDDEN_TAGS = {"script", "link", "iframe", "img", "object", "embed", "form", "video", "audio", "source", "base", "meta_refresh"}
URL_ATTRIBUTES = {"src", "href", "srcset", "action", "data", "poster", "formaction", "xlink:href"}
_URL_IN_CSS = re.compile(r"url\s*\(|@import|https?://", re.IGNORECASE)
_URL_IN_VALUE = re.compile(r"https?://|url\s*\(", re.IGNORECASE)


class _ReferenceFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        if tag in FORBIDDEN_TAGS:
            self.found.append(f"<{tag}>")
        if tag == "style":
            self._in_style = True
        for name, value in attrs:
            if name in URL_ATTRIBUTES or name.startswith("on"):
                self.found.append(f"{tag} {name}=")
            elif value and _URL_IN_VALUE.search(value):
                self.found.append(f"{tag} {name}=...url")

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False

    def handle_data(self, data):
        if self._in_style and _URL_IN_CSS.search(data):
            self.found.append("style url/@import/http")


STYLE = """
body{font-family:system-ui,'Malgun Gothic','Apple SD Gothic Neo',sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#222;line-height:1.55}
h1{font-size:26px;margin:0 0 8px} h2{font-size:20px;margin:28px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px}
.meta{color:#555;font-size:14px} .notice{background:#f5f4ee;border:1px solid #ddd;border-radius:6px;padding:8px 12px;font-size:14px}
.badge{display:inline-block;font-size:12px;font-weight:600;border:1px solid #999;border-radius:999px;padding:1px 8px;margin-left:6px;vertical-align:middle}
.evidence{display:block;color:#555;font-size:13px} li{margin:10px 0} .hyp{display:block;color:#555;font-size:13px}
ul.options{margin:4px 0 0 0;padding-left:20px;color:#333;font-size:14px}
.card{list-style:none;border:1px solid #ccc;border-radius:8px;padding:10px 14px;margin:12px 0}
ol.plan{padding-left:0} .card-head{font-weight:600} .card-head .no{margin-right:6px}
.draft{background:#f3f6fd;border:1px dashed #6b86c9;border-radius:6px;padding:8px 12px;margin:8px 0}
.draft-title{font-weight:600;font-size:14px;margin:0} .draft-note{color:#555;font-size:12px;margin:0 0 4px} .draft-text{margin:0}
.check{color:#333;font-size:13px;margin:6px 0 0}
.scale{margin:8px 0 12px;max-width:560px}
.scale-track{height:14px;border:1px solid #6b86c9;border-radius:4px;background:linear-gradient(to right,#e6eefc,#1d3f91);-webkit-print-color-adjust:exact;print-color-adjust:exact}
.scale-ticks{display:flex;justify-content:space-between;font-size:12px;color:#333;margin-top:2px}
.scale-ticks span{display:inline-flex;flex-direction:column;align-items:center;min-width:10px}
.scale-ticks i{display:block;width:0;height:6px;border-left:1px solid #333}
.scale-ends{display:flex;justify-content:space-between;gap:12px;font-size:13px;font-weight:600;margin-top:2px}
ul.matrix{list-style:none;padding-left:0;margin:6px 0 0} ul.matrix li{margin:8px 0} .item-name{font-weight:600;font-size:14px}
.preview-note{color:#555;font-size:13px;margin:0 0 6px}
@media print{.card,.scale,li{break-inside:avoid;page-break-inside:avoid} h2{break-after:avoid}}
""".strip()


class ExportError(RuntimeError):
    """내보내기 규칙을 어길 때. 메시지에는 사유 코드만 쓴다."""


def find_external_references(document: str) -> list[str]:
    """HTML 안의 외부 참조(태그, 속성, <style> 내용 기준). 비어 있어야 내보낼 수 있다."""
    finder = _ReferenceFinder()
    finder.feed(document)
    finder.close()
    return finder.found


def _e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _evidence_text(count: dict) -> str:
    parts = []
    if count["review"]:
        parts.append(f"근거 리뷰 {count['review']}건")
    if count["survey"]:
        parts.append(f"근거 설문 {count['survey']}건(합성)")
    return " · ".join(parts) if parts else "근거 0건"


def _scale_bar(low_label, high_label, subject: str) -> str:
    """0~10 눈금 막대(정적 미리보기). 연속 막대 아래에 0부터 10까지 11개 눈금 숫자를, 양끝에 '0 낮은 라벨', '10 높은 라벨'을 적는다(색만으로 뜻을 전하지 않는다)."""
    ticks = "".join(f"<span><i></i>{number}</span>" for number in range(11))
    label = f"{subject}: 0부터 10까지의 눈금. 0은 {low_label or ''}, 10은 {high_label or ''}. {SCALE_PREVIEW_NOTE}"
    return (
        f'<div class="scale" role="img" aria-label="{_e(label)}"><div class="scale-track"></div>'
        f'<div class="scale-ticks">{ticks}</div>'
        f'<div class="scale-ends"><span>0 {_e(low_label)}</span><span>10 {_e(high_label)}</span></div></div>'
    )


def _question_scales(question: dict) -> str:
    """scale10은 막대 하나, scale10_matrix는 항목마다 막대 하나. 그 밖의 형식에는 막대가 없다."""
    form = question.get("form") or question["type"]
    low, high = question.get("low_label"), question.get("high_label")
    if form == "scale10":
        return _scale_bar(low, high, question["text"])
    if form == "scale10_matrix":
        rows = "".join(
            f'<li><span class="item-name">{_e(item["label"])}</span>{_scale_bar(low, high, item["label"])}</li>' for item in question.get("items") or []
        )
        return f'<ul class="matrix">{rows}</ul>'
    return ""


def _plan_item(item: dict) -> str:
    badges = "".join(f'<span class="badge">{_e(source)}</span>' for source in item["sources"])
    evidence = f'<span class="evidence">{_e(_evidence_text(item["evidence_count"]))}</span>'
    if item.get("card_kind") != "area":  # 쿠팡 리뷰 카드와 이전 형식(suggest-v3) 문장은 기존 모양 그대로
        return f'<li>{_e(item["sentence"])}{badges}{evidence}</li>'
    rank = f'<span class="badge">{_e(item["rank_label"])}</span>' if item.get("rank_label") else ""
    check = f'<p class="check">확인 문항: 다음 회차 문항 {_e(item["check_question_no"])}번</p>' if item.get("check_question_no") is not None else ""
    return (
        f'<li class="card"><div class="card-head"><span class="no">{_e(item["order_no"])}.</span>{_e(item["area_label"])} 영역{rank}{badges}</div>'
        f'<p>{_e(item["priority_text"])}</p>'
        f'<div class="draft"><p class="draft-title">AI가 작성한 초안 · {_e(item["deliverable_kind"])}</p>'
        f'<p class="draft-note">검토·수정이 필요한 초안입니다</p><p class="draft-text">{_e(item["deliverable_text"])}</p></div>'
        f"{evidence}{check}</li>"
    )


def render_report_html(report: dict) -> str:
    family = report["family"]["name"] if report.get("family") else "전체"
    parts = [
        "<!doctype html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>회차 리포트 - {_e(family)} {_e(report['round']['label'])}</title>",
        f"<style>{STYLE}</style></head><body>",
        "<h1>회차 리포트</h1>",
        f'<p class="meta">제품군 {_e(family)} · 회차 {_e(report["round"]["label"])} · 생성 {_e(report["generated_at"])} · 리포트 번호 {_e(report["report_id"])}</p>',
        f'<p class="notice">{_e(NOTICE)}</p>',
        "<h2>액션플랜</h2>",
    ]
    plan = report["action_plan"]
    if plan:
        if report.get("rank_notice"):
            parts.append(f'<p class="notice rank-notice">{_e(report["rank_notice"])}</p>')
        parts.append('<ol class="plan">')
        for item in plan:
            parts.append(_plan_item(item))
        parts.append("</ol>")
    else:
        parts.append("<p>액션플랜 문장이 없습니다.</p>")
    parts.append('<h2>다음 회차 설문지<span class="badge">초안</span></h2>')
    questions = report["next_survey"]["questions"]
    if questions:
        if any((q.get("form") or q["type"]) in SCALE_FORMS for q in questions):
            parts.append(f'<p class="preview-note">눈금 막대는 {_e(SCALE_PREVIEW_NOTE)}</p>')
        parts.append("<ol>")
        for question in questions:
            is_scale = (question.get("form") or question["type"]) in SCALE_FORMS
            options = ""
            if is_scale:
                options = _question_scales(question)
            elif question["type"] != "scale5" and question["options"]:
                options = '<ul class="options">' + "".join(f"<li>{_e(o['label'])}</li>" for o in question["options"]) + "</ul>"
            elif question["type"] == "scale5":
                options = '<ul class="options"><li>1점부터 5점까지 고르기</li></ul>'
            if question.get("kind") == "opportunity_matrix":
                hyp = f'<span class="hyp">{_e(OPPORTUNITY_MARK)}: {_e(question["hypothesis_statement"])}</span>'
                mark = f'<span class="badge">{_e(OPPORTUNITY_MARK)}</span>'
            else:
                hyp = f'<span class="hyp">{_e(KIND_LABEL.get(question["hypothesis_kind"], question["hypothesis_kind"]))}: {_e(question["hypothesis_statement"])}</span>'
                mark = ""
            parts.append(
                f'<li>{_e(question["text"])}<span class="badge">{_e(TYPE_LABEL.get(question["type"], question["type"]))}</span>'
                f'<span class="badge">초안</span>{mark}{options}{hyp}</li>'
            )
        parts.append("</ol>")
    else:
        parts.append("<p>문항 초안이 없습니다.</p>")
    notes = report["next_survey"].get("no_question_hypotheses") or []
    if notes:
        parts.append("<h2>문항이 없는 가설</h2><ul>")
        for note in notes:
            parts.append(
                f'<li>{_e(note["note"])}<span class="hyp">{_e(KIND_LABEL.get(note["kind"], note["kind"]))}: {_e(note["statement"])}</span></li>'
            )
        parts.append("</ul>")
    parts.append("</body></html>")
    document = "\n".join(parts)
    if find_external_references(document):
        raise ExportError("external_reference")
    return document
