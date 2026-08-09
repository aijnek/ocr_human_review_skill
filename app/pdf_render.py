"""PDF をレビュー画面用のページ PNG に変換する (PyMuPDF)。"""

from pathlib import Path

import pymupdf

from . import db

MAX_PAGES = 10
DPI = 150


def render_previews(document_id: int, source: Path, mime: str) -> int:
    """プレビュー画像を data/previews/{doc_id}/page_{n}.png に生成し、ページ数を返す。"""
    out_dir = db.PREVIEWS_DIR / str(document_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    if mime == "application/pdf":
        with pymupdf.open(source) as doc:
            n_pages = min(doc.page_count, MAX_PAGES)
            for i in range(n_pages):
                pix = doc[i].get_pixmap(dpi=DPI)
                pix.save(out_dir / f"page_{i + 1}.png")
        return n_pages

    # 画像はそのまま 1 ページのプレビューとして扱う
    ext = source.suffix.lower().lstrip(".") or "png"
    (out_dir / f"page_1.{ext}").write_bytes(source.read_bytes())
    return 1


def preview_page_path(document_id: int, page: int) -> Path | None:
    out_dir = db.PREVIEWS_DIR / str(document_id)
    if not out_dir.is_dir():
        return None
    matches = list(out_dir.glob(f"page_{page}.*"))
    return matches[0] if matches else None
