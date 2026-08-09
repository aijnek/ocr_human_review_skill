"""実サンプルに対する描画。PyMuPDF の実挙動が対象なのでモックは使わない。"""

import pymupdf

from app import db, pdf_render
from tests.conftest import SAMPLE_PDF, SAMPLE_PNG

PNG_MAGIC = b"\x89PNG"


def test_renders_pdf_to_real_png():
    assert pdf_render.render_previews(1, SAMPLE_PDF, "application/pdf") == 1
    out = db.PREVIEWS_DIR / "1" / "page_1.png"
    data = out.read_bytes()
    assert data.startswith(PNG_MAGIC)
    # 描画に失敗した空画像は極端に小さくなるので、下限を置いて中身があることを担保する
    assert len(data) > 10_000


def test_image_upload_is_passed_through_byte_identical():
    assert pdf_render.render_previews(2, SAMPLE_PNG, "image/png") == 1
    assert (db.PREVIEWS_DIR / "2" / "page_1.png").read_bytes() == SAMPLE_PNG.read_bytes()


def test_page_count_is_clamped_to_max_pages(tmp_path):
    src = tmp_path / "many.pdf"
    doc = pymupdf.open()
    for _ in range(pdf_render.MAX_PAGES + 2):
        doc.new_page()
    doc.save(src)
    doc.close()

    assert pdf_render.render_previews(3, src, "application/pdf") == pdf_render.MAX_PAGES
    assert len(list((db.PREVIEWS_DIR / "3").glob("page_*.png"))) == pdf_render.MAX_PAGES


def test_preview_page_path():
    assert pdf_render.preview_page_path(4, 1) is None, "未描画なら None"

    pdf_render.render_previews(4, SAMPLE_PDF, "application/pdf")
    assert pdf_render.preview_page_path(4, 1).name == "page_1.png"
    assert pdf_render.preview_page_path(4, 2) is None, "存在しないページ"
