"""A-7 내보내기: 독립형 HTML 한 파일(SQ-14, 결정 2026-11-03).

- 담는 것: 제품군·회차·생성 시각, 액션플랜 문장과 근거 건수(링크 없음), 다음 회차 설문지("초안" 표시), "합성/실측" 출처 표기.
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
TYPE_LABEL = {"scale5": "5점 척도", "single": "하나 고르기", "multi": "여러 개 고르기"}
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
        parts.append("<ol>")
        for item in plan:
            badges = "".join(f'<span class="badge">{_e(source)}</span>' for source in item["sources"])
            parts.append(f'<li>{_e(item["sentence"])}{badges}<span class="evidence">{_e(_evidence_text(item["evidence_count"]))}</span></li>')
        parts.append("</ol>")
    else:
        parts.append("<p>액션플랜 문장이 없습니다.</p>")
    parts.append('<h2>다음 회차 설문지<span class="badge">초안</span></h2>')
    questions = report["next_survey"]["questions"]
    if questions:
        parts.append("<ol>")
        for question in questions:
            options = ""
            if question["type"] != "scale5" and question["options"]:
                options = '<ul class="options">' + "".join(f"<li>{_e(o['label'])}</li>" for o in question["options"]) + "</ul>"
            elif question["type"] == "scale5":
                options = '<ul class="options"><li>1점부터 5점까지 고르기</li></ul>'
            hyp = f'<span class="hyp">{_e(KIND_LABEL.get(question["hypothesis_kind"], question["hypothesis_kind"]))}: {_e(question["hypothesis_statement"])}</span>'
            parts.append(
                f'<li>{_e(question["text"])}<span class="badge">{_e(TYPE_LABEL.get(question["type"], question["type"]))}</span>'
                f'<span class="badge">초안</span>{options}{hyp}</li>'
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
