"""アップロードの重複排除と形式検証。"""

from app import db
from tests.conftest import SAMPLE_PDF, SAMPLE_PNG, count, upload


def test_same_content_is_deduplicated(client):
    first = upload(client, SAMPLE_PDF).json()
    assert first == {"created": [1], "duplicates": []}

    second = upload(client, SAMPLE_PDF).json()
    assert second["created"] == []
    assert second["duplicates"] == [{"filename": SAMPLE_PDF.name, "document_id": 1}]

    assert count("documents") == 1
    assert count("jobs") == 1, "重複には OCR ジョブを積まない"
    assert len(list(db.UPLOADS_DIR.iterdir())) == 1, "重複はファイルも保存しない"


def test_deduplication_is_by_content_not_filename(client):
    upload(client, SAMPLE_PDF, filename="original.pdf")
    res = upload(client, SAMPLE_PDF, filename="renamed_copy.pdf").json()
    assert res["created"] == []
    assert res["duplicates"][0]["document_id"] == 1


def test_different_content_creates_separate_documents(client):
    upload(client, SAMPLE_PDF)
    res = upload(client, SAMPLE_PNG, mime="image/png").json()
    assert res["created"] == [2]
    assert count("documents") == 2
    assert count("jobs") == 2


def test_unsupported_mime_is_rejected(client):
    res = client.post("/api/upload", files={"files": ("notes.txt", b"hello", "text/plain")})
    assert res.status_code == 400
    assert count("documents") == 0


def test_a_bad_file_rejects_the_whole_batch(client):
    """途中で 400 を返しつつ先行ファイルだけ登録済み、という状態を作らない。"""
    res = client.post(
        "/api/upload",
        files=[
            ("files", (SAMPLE_PDF.name, SAMPLE_PDF.read_bytes(), "application/pdf")),
            ("files", ("notes.txt", b"hello", "text/plain")),
        ],
    )
    assert res.status_code == 400
    assert count("documents") == 0
    assert count("jobs") == 0
    assert list(db.UPLOADS_DIR.iterdir()) == []
