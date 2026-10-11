#!/usr/bin/env python3
"""把 PDF / Word / 图片转成干净的 markdown，供 Skill 蒸馏使用。

用法:
    python convert_to_markdown.py <输入...> [--out .distill] [--force]

每份文档产出两个文件:
    <out>/<slug>.md    抽取出的 markdown（含需视觉阅读的提示）
    <out>/<slug>.json  元数据: 源路径 / 大小 / mtime / sha256 / 需视觉阅读的页

重复运行是增量的: 源文件 sha256 未变则报告 cached 并跳过。
成功返回 0，任一输入失败返回 1。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx"}
LEGACY_DOC_SUFFIXES = {".doc"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}

MIN_PAGE_CHARS = 25        # 非空白字符少于此值视为该页无文字层
RENDER_DPI = 200           # 渲染页面时的分辨率
GARBLED_THRESHOLD = 0.10   # 可疑字符占比超过此值判定为字体映射损坏
GARBLED_RANGES = ((0x0080, 0x02FF), (0xE000, 0xF8FF))


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #

def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def garbled_ratio(text: str) -> float:
    """估算「字体映射损坏」造成的乱码比例。

    正常文本里 Latin-1 补充区、Latin 扩展区、私用区的字符占比很低（通常 <2%）；
    PDF 嵌入字体缺少 ToUnicode 映射时，抽出来的文字会大量落进这些区段
    —— 看起来是字，其实全是错码。这类文字层必须丢弃，改走视觉阅读。
    """
    visible = [ch for ch in text if not ch.isspace()]
    if not visible:
        return 0.0
    suspect = sum(
        1 for ch in visible
        if any(low <= ord(ch) <= high for low, high in GARBLED_RANGES)
    )
    return suspect / len(visible)


def slugify(path: Path) -> str:
    """文件名 + 源路径哈希，保证同名不同目录不撞车、改名后仍可对应。"""
    stem = re.sub("[^0-9A-Za-z\\u4e00-\\u9fff]+", "-", path.stem).strip("-") or "doc"
    key = hashlib.sha256(str(path.resolve()).lower().encode("utf-8")).hexdigest()[:8]
    return f"{stem[:48]}-{key}"


# --------------------------------------------------------------------------- #
# 各格式转换
# --------------------------------------------------------------------------- #

def convert_pdf(path: Path, pages_dir: Path, render_all: bool = False):
    """返回 (markdown, 需视觉阅读的条目, 渲染出的图片路径, 总页数)。

    条目形如 {"page": 3, "reason": "no_text_layer" | "garbled_text" | "render_all"}。
    """
    try:
        import pymupdf
    except ImportError:  # pymupdf < 1.24.4 只暴露 fitz 这个名字
        import fitz as pymupdf

    document = pymupdf.open(path)
    try:
        total = len(document)
        chunks, vision = [], []
        for index, page in enumerate(document):
            page_no = index + 1
            text = (page.get_text("text") or "").strip()
            if render_all:
                vision.append({"page": page_no, "reason": "render_all"})
            elif len(re.sub(r"\s+", "", text)) < MIN_PAGE_CHARS:
                vision.append({"page": page_no, "reason": "no_text_layer"})
            elif garbled_ratio(text) > GARBLED_THRESHOLD:
                vision.append({"page": page_no, "reason": "garbled_text"})
            else:
                chunks.append(f"<!-- page {page_no} -->\n\n{text}")

        rendered = []
        for entry in vision:
            out_path = pages_dir / f"{path.stem}-p{entry['page']}.png"
            document[entry["page"] - 1].get_pixmap(dpi=RENDER_DPI).save(str(out_path))
            rendered.append(out_path)
    finally:
        document.close()

    return "\n\n".join(chunks), vision, rendered, total


def _heading_level(paragraph) -> int:
    style = ""
    try:
        style = paragraph.style.name or ""
    except (AttributeError, KeyError):
        return 0
    lowered = style.lower()
    if lowered.startswith("heading") or "标题" in style:
        digits = re.findall(r"\d+", style)
        return min(int(digits[0]), 6) if digits else 1
    return 0


def _table_to_markdown(table) -> str:
    rows = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            text = re.sub(r"\s+", " ", cell.text).strip().replace("|", "\\|")
            cells.append(text)
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    header, *body = rows
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join([" --- "] * width) + "|",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def convert_docx(path: Path) -> str:
    """按文档原始顺序遍历段落与表格。"""
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(str(path))
    blocks = []
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            level = _heading_level(paragraph)
            blocks.append(f"{'#' * level} {text}" if level else text)
        elif child.tag == qn("w:tbl"):
            markdown = _table_to_markdown(Table(child, document))
            if markdown:
                blocks.append(markdown)
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

def process(path: Path, out_dir: Path, pages_dir: Path, force: bool,
            render_all: bool = False) -> dict:
    slug = slugify(path)
    md_path = out_dir / f"{slug}.md"
    meta_path = out_dir / f"{slug}.json"
    digest = sha256_of(path)

    if not force and md_path.exists() and meta_path.exists():
        try:
            previous = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        if previous.get("sha256") == digest:
            return {**previous, "status": "cached", "md": str(md_path), "meta": str(meta_path)}

    suffix = path.suffix.lower()
    needs_vision: list = []
    rendered: list = []
    pages = None

    try:
        if suffix in PDF_SUFFIXES:
            markdown, needs_vision, rendered, pages = convert_pdf(path, pages_dir, render_all)
        elif suffix in DOCX_SUFFIXES:
            markdown = convert_docx(path)
        elif suffix in LEGACY_DOC_SUFFIXES:
            return {
                "source": str(path.resolve()), "slug": slug, "status": "unsupported",
                "reason": "旧版 .doc 无法直接解析，请另存为 .docx 或 PDF 后重试",
            }
        elif suffix in IMAGE_SUFFIXES:
            markdown = ""
            needs_vision = [{"page": 1, "reason": "image_input"}]
            rendered = [path]
        else:
            return {
                "source": str(path.resolve()), "slug": slug, "status": "unsupported",
                "reason": f"不支持的格式 {suffix or '(无扩展名)'}",
            }
    except Exception as exc:  # noqa: BLE001 - 逐文件隔离失败，不影响批处理
        return {
            "source": str(path.resolve()), "slug": slug, "status": "error",
            "reason": f"{type(exc).__name__}: {exc}",
        }

    vision_note = ""
    if needs_vision:
        reason_text = {
            "no_text_layer": "无文字层（扫描件）",
            "garbled_text": "文字层乱码（字体映射损坏，文字不可信）",
            "render_all": "按要求整篇渲染",
            "image_input": "本身就是图片",
        }
        listing = "\n".join(
            f"- 第 {entry['page']} 页 — {reason_text.get(entry['reason'], entry['reason'])}: {image}"
            for entry, image in zip(needs_vision, rendered)
        )
        vision_note = (
            "\n\n## 需要视觉阅读\n\n"
            "以下页面必须用 Read 工具直接读图片，抽取出的文字层不可信：\n\n" + listing
        )

    header = f"<!-- source: {path.resolve()} -->\n<!-- sha256: {digest} -->\n"
    md_text = header + ("\n" + markdown if markdown else "") + vision_note
    md_path.write_text(md_text, encoding="utf-8")

    stat = path.stat()
    meta = {
        "source": str(path.resolve()),
        "slug": slug,
        "suffix": suffix,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "sha256": digest,
        "pages": pages,
        "needs_vision": needs_vision,
        "vision_files": [str(item) for item in rendered],
        "status": "ok",
        "md": str(md_path),
        "meta": str(meta_path),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description="把文档转成干净 markdown 供蒸馏使用")
    parser.add_argument("inputs", nargs="+", help="输入文件（PDF / docx / 图片）")
    parser.add_argument("--out", default=".distill", help="中间产物目录，默认 .distill")
    parser.add_argument("--force", action="store_true", help="忽略缓存，强制重新解析")
    parser.add_argument("--render-all", action="store_true",
                        help="PDF 整篇渲染成图片走视觉阅读（课件、PPT 导出、文字层不可信时用）")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    pages_dir = out_dir / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for raw in args.inputs:
        path = Path(raw)
        if not path.is_file():
            results.append({"source": raw, "status": "error", "reason": "文件不存在"})
            continue
        results.append(process(path, out_dir, pages_dir, args.force, args.render_all))

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item.get("status") in {"ok", "cached"} for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
