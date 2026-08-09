"""共通フィクスチャ。

OCR_DATA_DIR は app.db が DATA_DIR を import 時に評価するため、
app.* の import より前に設定する必要がある。
"""

import os
import shutil
import tempfile

_TMP = tempfile.TemporaryDirectory(prefix="ocr-test-")
os.environ["OCR_DATA_DIR"] = _TMP.name  # 以下の import より前であること

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, main  # noqa: E402

SAMPLES = db.PROJECT_ROOT / "samples"
SAMPLE_PDF = SAMPLES / "sample1_zaiseki_himawari.pdf"
SAMPLE_PDF2 = SAMPLES / "sample2_kinmu_sakura.pdf"
SAMPLE_PNG = SAMPLES / "sample4_zaiseki_himawari_scan.png"


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    db.init_db()
    yield
    _TMP.cleanup()


@pytest.fixture(autouse=True)
def _clean_state():
    """テーブルを空にし、プロセスグローバルとファイル出力をリセットする。"""
    main.shutdown_requested = False  # モジュールグローバルなので明示的に戻す
    with db.get_conn() as conn:
        for table in ("extractions", "records", "jobs", "documents"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence")  # id を予測可能にする
    for d in (db.PREVIEWS_DIR, db.UPLOADS_DIR):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture
def client():
    with TestClient(main.app) as c:  # context manager にすることで lifespan が走る
        yield c


def upload(client, path, mime="application/pdf", filename=None):
    return client.post(
        "/api/upload",
        files={"files": (filename or path.name, path.read_bytes(), mime)},
    )


@pytest.fixture
def uploaded(client):
    """サンプル PDF を 1 件アップロードし (document_id, job_id) を返す。"""
    doc_id = upload(client, SAMPLE_PDF).json()["created"][0]
    with db.get_conn() as conn:
        job_id = conn.execute("SELECT id FROM jobs ORDER BY id DESC LIMIT 1").fetchone()["id"]
    return doc_id, job_id


@pytest.fixture
def claimed(client, uploaded):
    """uploaded に加えてエージェントがジョブを取得済みの状態。"""
    client.get("/api/agent/jobs/next?wait=0")
    return uploaded


@pytest.fixture
def reviewable(client, claimed):
    """OCR 結果を投入し、レビュー可能 (awaiting_review) にした状態。"""
    doc_id, job_id = claimed
    client.post(
        f"/api/agent/jobs/{job_id}/complete",
        json={
            "fields": {
                "person_name": {"value": "田中太郎", "confidence": 0.9, "evidence": "氏名欄"},
                "facility_name": {
                    "value": "ひまわり保育園",
                    "confidence": 0.8,
                    "evidence": "施設名",
                },
            }
        },
    )
    return doc_id, job_id


def extraction(document_id, field_key):
    """extractions の 1 行を dict で返す (無ければ None)。"""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM extractions WHERE document_id = ? AND field_key = ?",
            (document_id, field_key),
        ).fetchone()
    return dict(row) if row is not None else None


def document_status(document_id):
    with db.get_conn() as conn:
        row = conn.execute("SELECT status FROM documents WHERE id = ?", (document_id,)).fetchone()
    return row["status"] if row is not None else None


def job_status(job_id):
    with db.get_conn() as conn:
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row["status"] if row is not None else None


def count(table):
    with db.get_conn() as conn:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
