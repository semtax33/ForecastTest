#!/usr/bin/env python3
"""Assemble manually authored Korean page translations into one HTML book.

This program does not translate text. It only validates the page JSON files,
extracts the corresponding source text for reference, and renders the HTML.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader


BOOK_TITLE_KO = "세계 거시경제학의 이해"
BOOK_TITLE_EN = "Demystifying Global Macroeconomics"
AUTHOR = "John E. Marthinsen"
METHOD = "Codex가 원문을 페이지별로 읽고 직접 번역"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--no-embed-pdf", action="store_true")
    return parser.parse_args()


def load_pages(directory: Path) -> tuple[dict[int, dict[str, Any]], list[Path]]:
    files = sorted(directory.glob("pages_*.json"))
    if not files:
        raise FileNotFoundError(f"No page translation files in {directory}")
    pages: dict[int, dict[str, Any]] = {}
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("translation_method") != METHOD:
            raise ValueError(f"Unexpected translation method in {path}")
        for page in payload.get("pages", []):
            number = int(page["pdf_page"])
            if number in pages:
                raise ValueError(f"Duplicate PDF page {number}: {path}")
            if not isinstance(page.get("blocks"), list):
                raise ValueError(f"Page {number} has no blocks list: {path}")
            pages[number] = page
    return pages, files


def flatten_outline(reader: PdfReader) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def visit(nodes: Iterable[Any], level: int = 0) -> None:
        for node in nodes:
            if isinstance(node, list):
                visit(node, level + 1)
                continue
            title = getattr(node, "title", None)
            if not title and isinstance(node, dict):
                title = node.get("/Title")
            if not title:
                continue
            try:
                page_number = reader.get_destination_page_number(node) + 1
            except Exception:
                continue
            result.append({"title": str(title), "pdf_page": page_number, "level": level})

    try:
        visit(reader.outline)
    except Exception:
        pass
    return result


CHAPTER_TITLES = {
    "Acknowledgments": "감사의 말",
    "About the Author": "저자 소개",
    "Preface": "머리말",
    "Contents": "목차",
    "Introduction to Global Macroeconomics": "세계 거시경제학 입문",
    "Taking an Economic Pulse": "경제의 맥박 짚기",
    "Labor Market Conditions": "노동시장 여건",
    "Inflation and Real GDP": "인플레이션과 실질 GDP",
    "Inflation: Who Wins, and Who Loses?": "인플레이션: 누가 이익을 보고 누가 손해를 보는가?",
    "Monetary Aggregates": "통화지표",
    "Financial Intermediation": "금융중개",
    "Money Creation": "통화 창출",
    "Central Banks": "중앙은행",
    "Real Credit Markets": "실질 신용시장",
    "The Economics of Cryptocurrencies": "암호화폐의 경제학",
    "Real Goods and Services Markets": "실물 재화·서비스 시장",
    "Fiscal Policy": "재정정책",
    "Business Cycles": "경기순환",
    "Foreign Exchange Basics": "외환의 기초",
    "Foreign Exchange Markets": "외환시장",
    "Balance of Payments": "국제수지",
    "Putting It All Together": "종합: 모든 요소 연결하기",
    "Shocks to Nations with Flexible Exchange Rates": "변동환율제 국가에 대한 충격",
    "Shocks to Nations with Fixed Exchange Rates": "고정환율제 국가에 대한 충격",
    "Causes, Cures, and Consequences of the Great Recession": "대침체의 원인·해법·결과",
    "Long-Term Growth and Development": "장기 성장과 발전",
    "Long-Term Inflation, Exchange Rates, and Unemployment": "장기 인플레이션·환율·실업",
    "Appendix A. List of Abbreviations": "부록 A. 약어 목록",
    "Appendix B. Important Terms and Concepts": "부록 B. 중요 용어와 개념",
    "Index": "색인",
}


def translate_outline_title(title: str) -> str:
    if title in CHAPTER_TITLES:
        return CHAPTER_TITLES[title]
    match = re.fullmatch(r"Chapter (\d+)\. (.+)", title)
    if match:
        number, name = match.groups()
        return f"제{number}장. {CHAPTER_TITLES.get(name, name)}"
    return title


def render_block(block: dict[str, Any]) -> str:
    kind = block.get("type", "p")
    if kind == "table":
        # Manual translations use both structured tables and faithful,
        # line-oriented table text. Preserve the latter instead of rendering
        # an empty table when headers/rows are intentionally absent.
        if "text" in block and not block.get("headers") and not block.get("rows"):
            table_text = html.escape(str(block.get("text", "")))
            return f'<div class="text-table">{table_text}</div>'
        headers = "".join(f"<th>{html.escape(str(value))}</th>" for value in block.get("headers", []))
        rows = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
            for row in block.get("rows", [])
        )
        return f'<div class="table-wrap"><table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>'

    text = html.escape(str(block.get("text", ""))).replace("\n", "<br>")
    if kind == "title":
        return f"<h1>{text}</h1>"
    if kind == "chapter":
        return f'<p class="chapter-number">{text}</p>'
    if kind == "heading":
        return f"<h2>{text}</h2>"
    if kind == "subheading":
        return f"<h3>{text}</h3>"
    if kind == "subtitle":
        return f'<p class="subtitle">{text}</p>'
    if kind == "bullet":
        return f'<p class="bullet">• {text}</p>'
    if kind == "footnote":
        return f'<p class="footnote">{text}</p>'
    if kind == "caption":
        return f'<p class="caption">{text}</p>'
    if kind == "doi":
        return f'<p class="doi"><a href="{text}">{text}</a></p>'
    if kind == "running":
        return f'<p class="running">{text}</p>'
    if kind == "toc":
        ref_page = html.escape(str(block.get("ref_page", "")))
        return f'<p class="toc-entry"><span>{text}</span><b>{ref_page}</b></p>'
    if kind == "question":
        return f'<p class="question">{text}</p>'
    return f"<p>{text}</p>"


def page_text(page: dict[str, Any]) -> str:
    pieces: list[str] = []
    for block in page.get("blocks", []):
        pieces.append(str(block.get("text", "")))
        pieces.extend(str(value) for row in block.get("rows", []) for value in row)
    return " ".join(pieces)


def number_warnings(source: str, translation: str) -> list[str]:
    source_numbers = re.findall(r"\d+(?:[,.]\d+)*", source)
    compact_target = translation.replace(",", "")
    missing = [number for number in source_numbers if number.replace(",", "") not in compact_target]
    return list(dict.fromkeys(missing))


def build_document(
    reader: PdfReader,
    pdf_path: Path,
    pages: dict[int, dict[str, Any]],
    files: list[Path],
    embed_pdf: bool,
) -> str:
    total_pages = len(reader.pages)
    translated_count = len(pages)
    percent = translated_count / total_pages * 100
    outline = flatten_outline(reader)
    pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    nav = []
    for item in outline:
        title = html.escape(translate_outline_title(item["title"]))
        page_number = item["pdf_page"]
        nav.append(f'<a href="#page-{page_number}"><span>{title}</span><small>{page_number}</small></a>')

    sections: list[str] = []
    warning_count = 0
    for number in range(1, total_pages + 1):
        translation_page = pages.get(number)
        source = reader.pages[number - 1].extract_text() or ""
        original_button = (
            f'<button onclick="showOriginal({number})">원본 면 보기</button>'
            if embed_pdf
            else ""
        )
        if translation_page is None:
            body = '<p class="pending">직접 번역 대기 중</p>'
            state = "대기"
            warnings: list[str] = []
        else:
            body = "\n".join(render_block(block) for block in translation_page["blocks"])
            if not translation_page["blocks"]:
                body = '<p class="blank">원본의 빈 면</p>'
            state = "완료"
            warnings = number_warnings(source, page_text(translation_page))
            warning_count += len(warnings)
        warning_markup = ""
        if warnings:
            warning_markup = (
                '<details class="qa"><summary>숫자 대조 메모</summary><p>'
                + html.escape(", ".join(warnings))
                + "</p></details>"
            )
        sections.append(
            f'''<section class="book-page" id="page-{number}" data-page="{number}">
<header><span>PDF {number}쪽</span><i class="state state-{state}">{state}</i>{original_button}</header>
<article lang="ko">{body}</article>
{warning_markup}
<details class="source"><summary>추출 원문 텍스트</summary><pre>{html.escape(source)}</pre></details>
</section>'''
        )

    encoded_pdf = ""
    if embed_pdf:
        encoded_pdf = (
            '<script id="source-pdf-data" type="application/octet-stream">'
            + base64.b64encode(pdf_path.read_bytes()).decode("ascii")
            + "</script>"
        )
    built_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    source_files = ", ".join(path.name for path in files)

    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{BOOK_TITLE_KO} - 전체 한국어 번역</title>
<style>
:root{{--ink:#19231d;--muted:#69736c;--paper:#fffef9;--ground:#e9e7de;--line:#d8d5c9;--green:#0b6b4f;--amber:#995513}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--ground);color:var(--ink);font-family:Pretendard,"Noto Sans KR","Malgun Gothic",sans-serif;line-height:1.75}}
button,input{{font:inherit}}.toolbar{{position:sticky;top:0;z-index:20;display:flex;gap:.55rem;align-items:center;padding:.65rem 1rem;background:#19231df5;color:white;box-shadow:0 2px 12px #0003}}
.toolbar strong{{margin-right:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.toolbar input,.toolbar button,.book-page header button{{border:1px solid #ffffff55;border-radius:.4rem;padding:.3rem .55rem;background:#ffffff12;color:inherit}}
.toolbar input{{width:9rem}}.layout{{display:grid;grid-template-columns:19rem minmax(0,54rem);gap:1.2rem;justify-content:center;padding:1.2rem}}aside{{position:sticky;top:4.2rem;align-self:start;max-height:calc(100vh - 5.4rem);overflow:auto;padding:1rem;background:var(--paper);border:1px solid var(--line);border-radius:.7rem}}
aside h2{{margin:0 0 .6rem;font-size:1.05rem}}.bar{{height:.55rem;border-radius:9rem;background:#ddd9cc;overflow:hidden}}.bar span{{display:block;height:100%;width:{percent:.5f}%;background:var(--green)}}.meta{{font-size:.78rem;color:var(--muted)}}nav{{display:flex;flex-direction:column}}nav a{{display:flex;justify-content:space-between;gap:.5rem;padding:.27rem;color:inherit;text-decoration:none;font-size:.82rem;border-radius:.3rem}}nav a:hover{{background:#eeece3;color:var(--green)}}nav small{{color:var(--muted)}}
.cover,.book-page{{background:var(--paper);border:1px solid var(--line);border-radius:.75rem;box-shadow:0 8px 24px #3d463d14}}.cover{{min-height:78vh;display:grid;place-content:center;text-align:center;padding:3rem;margin-bottom:1.2rem}}.cover .tag{{color:var(--green);font-weight:700;letter-spacing:.12em}}.cover h1{{font:700 clamp(2.2rem,6vw,4.2rem)/1.2 "Noto Serif KR","Batang",serif;margin:.5rem 0}}.cover h2{{font-weight:400;color:var(--muted);margin:0 0 2rem}}
.book-page{{min-height:64vh;margin-bottom:1.2rem;padding:clamp(1.2rem,4vw,3.2rem);scroll-margin-top:4.3rem}}.book-page>header{{display:flex;align-items:center;gap:.7rem;border-bottom:1px solid var(--line);padding-bottom:.7rem;margin-bottom:1.3rem;font-size:.82rem;color:var(--muted)}}.book-page>header button{{margin-left:auto;color:var(--ink);border-color:var(--line);background:white;cursor:pointer}}.state{{font-style:normal;border-radius:9rem;padding:.05rem .45rem}}.state-완료{{background:#dcefe7;color:var(--green)}}.state-대기{{background:#f7e9d5;color:var(--amber)}}
article{{font-family:"Noto Serif KR","Batang",serif;font-size:1.03rem}}article p{{margin:0 0 1em;text-align:justify;word-break:keep-all}}article h1{{font-size:2.2rem;text-align:center}}article h2{{font-size:1.6rem;color:#114e3b}}article h3{{font-size:1.2rem;color:#1d604c;margin-top:1.5em}}.chapter-number{{font:700 .9rem/1 Pretendard,"Noto Sans KR",sans-serif;color:var(--green);letter-spacing:.08em;margin-bottom:.5rem}}.subtitle{{font-size:1.25rem;text-align:center}}.bullet{{padding-left:1.25rem;text-indent:-1.25rem}}.question{{padding-left:1.4rem;text-indent:-1.4rem}}.footnote{{font-size:.82rem;border-top:1px solid var(--line);padding-top:.7rem}}.caption{{font-weight:700}}.running{{font-size:.75rem;color:var(--muted);text-align:right}}.doi{{font-size:.78rem;overflow-wrap:anywhere}}.toc-entry{{display:flex;justify-content:space-between;gap:1rem;margin:.1em 0}}.toc-entry b{{font-family:inherit}}.blank,.pending{{color:var(--muted);font-style:italic}}
.table-wrap{{overflow-x:auto;margin:1rem 0}}table{{width:100%;border-collapse:collapse;font-family:Pretendard,"Noto Sans KR",sans-serif;font-size:.82rem;line-height:1.45}}th,td{{padding:.45rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{border-top:2px solid var(--ink);border-bottom:2px solid var(--ink)}}.text-table{{margin:1.15rem 0;padding:1rem;border:1px solid var(--line);border-radius:.45rem;background:#f7f6ef;white-space:pre-wrap;overflow-wrap:anywhere;font-family:Pretendard,"Noto Sans KR",sans-serif;font-size:.88rem;line-height:1.65}}.source,.qa{{margin-top:1rem;font-size:.78rem;color:var(--muted)}}.source pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0eee6;padding:1rem;border-radius:.4rem;line-height:1.45}}.qa{{color:var(--amber)}}
.viewer{{display:none;position:fixed;inset:0;z-index:40;background:#111d;padding:3vh 3vw;grid-template-rows:auto 1fr}}.viewer.open{{display:grid}}.viewer header{{display:flex;color:white;padding:.3rem;align-items:center}}.viewer button{{margin-left:auto}}.viewer iframe{{width:100%;height:100%;border:0;background:white}}
@media(max-width:900px){{.layout{{grid-template-columns:1fr;padding:.65rem}}aside{{position:static;max-height:15rem}}.toolbar strong{{display:none}}}}@media print{{body{{background:white}}.toolbar,aside,.book-page>header button,.viewer,.source,.qa{{display:none!important}}.layout{{display:block;padding:0}}.cover,.book-page{{border:0;box-shadow:none;break-after:page;margin:0;min-height:0}}}}
</style></head><body>
<div class="toolbar"><strong>{BOOK_TITLE_KO}</strong><input id="jump" inputmode="numeric" placeholder="PDF 쪽번호"><button onclick="jumpPage()">이동</button><input id="query" type="search" placeholder="번역문 검색"><button onclick="searchText()">검색</button></div>
<div class="layout"><aside><h2>책 전체 목차</h2><div class="bar"><span></span></div><p class="meta">직접 번역 {translated_count:,}/{total_pages:,}쪽 ({percent:.1f}%)<br>숫자 대조 메모 {warning_count:,}건</p><nav>{''.join(nav)}</nav></aside><main>
<section class="cover"><div class="tag">페이지별 직접 번역 · 제3판</div><h1>{BOOK_TITLE_KO}</h1><h2>{BOOK_TITLE_EN}</h2><p>{AUTHOR}</p><p class="meta">PDF {total_pages}쪽 1:1 대응 · {built_at}<br>번역 데이터: {html.escape(source_files)}<br>원본 SHA-256: {pdf_hash}</p></section>
{''.join(sections)}</main></div>
<div id="viewer" class="viewer"><header><span id="viewer-label">원본 PDF</span><button onclick="closeViewer()">닫기</button></header><iframe id="pdf-frame" title="원본 PDF"></iframe></div>
{encoded_pdf}
<script>
let pdfUrl=null;function ensurePdf(){{if(pdfUrl)return pdfUrl;const n=document.getElementById('source-pdf-data');if(!n)return null;const s=atob(n.textContent.trim()),b=new Uint8Array(s.length);for(let i=0;i<s.length;i++)b[i]=s.charCodeAt(i);pdfUrl=URL.createObjectURL(new Blob([b],{{type:'application/pdf'}}));return pdfUrl}}
function showOriginal(p){{const u=ensurePdf();if(!u){{alert('원본 PDF가 포함되지 않았습니다.');return}}document.getElementById('viewer-label').textContent=`원본 PDF ${{p}}쪽`;document.getElementById('pdf-frame').src=`${{u}}#page=${{p}}&view=FitH`;document.getElementById('viewer').classList.add('open')}}function closeViewer(){{document.getElementById('viewer').classList.remove('open')}}
function jumpPage(){{const p=Number(document.getElementById('jump').value),n=document.getElementById(`page-${{p}}`);if(n)n.scrollIntoView()}}function searchText(){{const q=document.getElementById('query').value.trim().toLocaleLowerCase('ko');if(!q)return;for(const n of document.querySelectorAll('.book-page')){{if(n.querySelector('article').innerText.toLocaleLowerCase('ko').includes(q)){{n.scrollIntoView();return}}}}alert('검색 결과가 없습니다.')}}
document.getElementById('jump').addEventListener('keydown',e=>{{if(e.key==='Enter')jumpPage()}});document.getElementById('query').addEventListener('keydown',e=>{{if(e.key==='Enter')searchText()}});document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeViewer()}});
</script></body></html>'''


def main() -> int:
    args = parse_args()
    pdf_path = args.pdf.resolve()
    translation_dir = args.translations.resolve()
    output_path = args.output.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    if not translation_dir.is_dir():
        raise FileNotFoundError(translation_dir)
    pages, files = load_pages(translation_dir)
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    out_of_range = sorted(number for number in pages if not 1 <= number <= total_pages)
    if out_of_range:
        raise ValueError(f"Page numbers outside PDF: {out_of_range}")
    missing = [number for number in range(1, total_pages + 1) if number not in pages]
    if args.require_complete and missing:
        raise ValueError(f"Translation is incomplete: {len(missing)} pages missing; first={missing[:10]}")
    document = build_document(reader, pdf_path, pages, files, not args.no_embed_pdf)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(document, encoding="utf-8")
    os.replace(temporary, output_path)
    print(
        json.dumps(
            {
                "output": str(output_path),
                "translated_pages": len(pages),
                "total_pages": total_pages,
                "missing_pages": len(missing),
                "bytes": output_path.stat().st_size,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
