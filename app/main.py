"""OCR Human-Review ローカル Web アプリ。

LLM は一切呼ばない。OCR はジョブキュー (jobs テーブル) に積み、
Claude Code エージェントが scripts/poll.py 経由で処理して結果を POST してくる。
"""

import asyncio
import hashlib
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, pdf_render, schemas

app = FastAPI(title="OCR Human Review")

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

ALLOWED_MIMES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}

DEFAULT_SCHEMA = "employment_certificate"

# UI の「セッション終了」ボタンで立ち、poll 中のエージェントに shutdown を返す
shutdown_requested = False


@app.on_event("startup")
def startup() -> None:
    db.init_db()


# ---------------------------------------------------------------- pages


@app.get("/")
def page_index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"page": "index"})


@app.get("/review/{document_id}")
def page_review(request: Request, document_id: int):
    with db.get_conn() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if doc is None:
        raise HTTPException(404)
    schema = schemas.load_schema(doc["schema_name"])
    return templates.TemplateResponse(
        request,
        "review.html",
        {"page": "review", "doc": dict(doc), "schema": schema},
    )


@app.get("/admin")
def page_admin(request: Request):
    return templates.TemplateResponse(request, "admin.html", {"page": "admin"})


# ---------------------------------------------------------------- upload & documents


@app.post("/api/upload")
async def api_upload(files: list[UploadFile]):
    # 1 件でも未対応形式があれば何も保存しない。ループ内で 400 を投げると
    # 先行ファイルだけ登録済みなのにクライアントはエラーを見る、という状態になる
    for f in files:
        if (f.content_type or "") not in ALLOWED_MIMES:
            raise HTTPException(400, f"未対応のファイル形式です: {f.filename} ({f.content_type})")

    created = []
    duplicates = []
    for f in files:
        mime = f.content_type or ""
        data = await f.read()
        digest = hashlib.sha256(data).hexdigest()
        with db.get_conn() as conn:
            # 同一内容が登録済みなら保存も OCR ジョブ投入もしない
            dup = conn.execute(
                "SELECT id FROM documents WHERE content_hash = ?", (digest,)
            ).fetchone()
            if dup is not None:
                duplicates.append({"filename": f.filename, "document_id": dup["id"]})
                continue
            stored = db.UPLOADS_DIR / f"{uuid.uuid4().hex}{ALLOWED_MIMES[mime]}"
            stored.write_bytes(data)
            cur = conn.execute(
                "INSERT INTO documents (filename, stored_path, content_hash, mime, schema_name, status)"
                " VALUES (?, ?, ?, ?, ?, 'uploaded')",
                (f.filename, str(stored), digest, mime, DEFAULT_SCHEMA),
            )
            doc_id = cur.lastrowid
            assert doc_id is not None  # INSERT 成功後は必ず入る
            payload = {
                "document_id": doc_id,
                "file_path": str(stored),
                "original_filename": f.filename,
                "mime": mime,
                "schema_name": DEFAULT_SCHEMA,
                "schema": schemas.load_schema(DEFAULT_SCHEMA),
            }
            conn.execute(
                "INSERT INTO jobs (type, payload_json) VALUES ('ocr', ?)",
                (json.dumps(payload, ensure_ascii=False),),
            )
        try:
            pdf_render.render_previews(doc_id, stored, mime)
        except Exception as e:  # プレビュー失敗はレビュー継続を妨げない
            print(f"preview rendering failed for doc {doc_id}: {e}")
        created.append(doc_id)
    return {"created": created, "duplicates": duplicates}


@app.get("/api/documents")
def api_documents():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY id DESC").fetchall()
    return {"documents": [dict(r) for r in rows]}


@app.get("/api/documents/{document_id}")
def api_document(document_id: int):
    with db.get_conn() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if doc is None:
            raise HTTPException(404)
        ext = conn.execute(
            "SELECT * FROM extractions WHERE document_id = ? ORDER BY id", (document_id,)
        ).fetchall()
    pages = sorted(
        (db.PREVIEWS_DIR / str(document_id)).glob("page_*.*")
        if (db.PREVIEWS_DIR / str(document_id)).is_dir()
        else []
    )
    return {
        "document": dict(doc),
        "extractions": [dict(r) for r in ext],
        "page_count": len(pages),
    }


@app.get("/api/documents/{document_id}/preview/{page}")
def api_preview(document_id: int, page: int):
    path = pdf_render.preview_page_path(document_id, page)
    if path is None:
        raise HTTPException(404)
    return FileResponse(path)


@app.post("/api/documents/{document_id}/confirm")
async def api_confirm(document_id: int, request: Request):
    body = await request.json()
    fields: dict[str, str] = body.get("fields", {})
    with db.get_conn() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if doc is None:
            raise HTTPException(404)
        if doc["status"] not in ("awaiting_review", "confirmed"):
            raise HTTPException(409, "この文書はまだレビューできる状態ではありません")
        # スキーマ外のキーは黙って捨てる (単一ユーザーのローカルアプリなので 400 にはしない)
        allowed = {f["key"] for f in schemas.load_schema(doc["schema_name"])["fields"]}
        fields = {k: v for k, v in fields.items() if k in allowed}
        for key, value in fields.items():
            row = conn.execute(
                "SELECT value_extracted FROM extractions WHERE document_id = ? AND field_key = ?",
                (document_id, key),
            ).fetchone()
            # 抽出行が無いのは「抽出値が空」と同じ扱い。ここで value をそのまま入れると
            # 未抽出フィールドを空欄で確定しただけで value_corrected = "" が残り、
            # 精度指標 (value_corrected IS NOT NULL) が幻の修正を数えてしまう
            extracted = (row["value_extracted"] or "") if row is not None else ""
            corrected = value if extracted != value else None
            conn.execute(
                """INSERT INTO extractions (document_id, field_key, value_corrected)
                   VALUES (?, ?, ?)
                   ON CONFLICT (document_id, field_key) DO UPDATE SET
                     value_corrected = excluded.value_corrected,
                     updated_at = datetime('now', 'localtime')""",
                (document_id, key, corrected),
            )
        data_json = json.dumps(fields, ensure_ascii=False)
        existing = conn.execute(
            "SELECT id FROM records WHERE document_id = ?", (document_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE records SET data_json = ?, updated_at = datetime('now', 'localtime')"
                " WHERE id = ?",
                (data_json, existing["id"]),
            )
            record_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO records (document_id, schema_name, data_json) VALUES (?, ?, ?)",
                (document_id, doc["schema_name"], data_json),
            )
            record_id = cur.lastrowid
        conn.execute("UPDATE documents SET status = 'confirmed' WHERE id = ?", (document_id,))
    return {"record_id": record_id}


# ---------------------------------------------------------------- admin (records CRUD)


@app.get("/api/records")
def api_records():
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT r.*, d.filename FROM records r
               LEFT JOIN documents d ON d.id = r.document_id
               ORDER BY r.id DESC"""
        ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["data"] = json.loads(item.pop("data_json"))
        out.append(item)
    schema = schemas.load_schema(DEFAULT_SCHEMA)
    return {"records": out, "schema": schema}


@app.put("/api/records/{record_id}")
async def api_record_update(record_id: int, request: Request):
    body = await request.json()
    with db.get_conn() as conn:
        row = conn.execute("SELECT id FROM records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            raise HTTPException(404)
        conn.execute(
            "UPDATE records SET data_json = ?, updated_at = datetime('now', 'localtime')"
            " WHERE id = ?",
            (json.dumps(body.get("data", {}), ensure_ascii=False), record_id),
        )
    return {"ok": True}


@app.delete("/api/records/{record_id}")
def api_record_delete(record_id: int):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
    return {"ok": True}


# ---------------------------------------------------------------- session control


@app.post("/api/shutdown")
def api_shutdown():
    global shutdown_requested
    shutdown_requested = True
    return {"ok": True}


@app.get("/api/status")
def api_status():
    with db.get_conn() as conn:
        queued = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued', 'running')"
        ).fetchone()["n"]
    return {
        "shutdown_requested": shutdown_requested,
        "active_jobs": queued,
    }


# ---------------------------------------------------------------- agent API


def _finish_job(conn, job_id: int, status: str, result: dict) -> None:
    """running のジョブだけを終端状態に遷移させる。

    status = 'running' を条件に含めるのは jobs/next の claim と同じ理由。
    読んでから書くまでの間に他のワーカーが終端させていた場合に 409 を返す。
    これが無いと complete と fail が競合し、確定済み文書が error に戻る。
    """
    cur = conn.execute(
        "UPDATE jobs SET status = ?, result_json = ?,"
        " updated_at = datetime('now', 'localtime')"
        " WHERE id = ? AND status = 'running'",
        (status, json.dumps(result, ensure_ascii=False), job_id),
    )
    if cur.rowcount == 0:
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        raise HTTPException(409, f"job {job_id} is {row['status']}, not running")


@app.get("/api/agent/jobs/next")
async def api_agent_next_job(wait: int = 230):
    global shutdown_requested
    deadline = asyncio.get_event_loop().time() + min(wait, 590)
    while True:
        if shutdown_requested:
            # 一度返したらリセットする (サーバーが残っても次回セッションを妨げない)
            shutdown_requested = False
            return {"status": "shutdown"}
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is not None:
                # status = 'queued' を条件に含めることで、複数ワーカー構成でも
                # 同じジョブを二重に取得しない (単一ワーカーなら常に成功する)
                cur = conn.execute(
                    "UPDATE jobs SET status = 'running',"
                    " updated_at = datetime('now', 'localtime')"
                    " WHERE id = ? AND status = 'queued'",
                    (row["id"],),
                )
                # 負けた場合は下の deadline/sleep を通す。continue で先頭に
                # 戻すと wait を超えて回り続け、イベントループにも譲らない
                if cur.rowcount:
                    if row["type"] == "ocr":
                        doc_id = json.loads(row["payload_json"])["document_id"]
                        conn.execute(
                            "UPDATE documents SET status = 'ocr_running' WHERE id = ?",
                            (doc_id,),
                        )
                    return {
                        "status": "job",
                        "job": {
                            "id": row["id"],
                            "type": row["type"],
                            "payload": json.loads(row["payload_json"]),
                        },
                    }
        if asyncio.get_event_loop().time() >= deadline:
            return {"status": "timeout"}
        await asyncio.sleep(0.5)


@app.post("/api/agent/jobs/{job_id}/complete")
async def api_agent_complete(job_id: int, request: Request):
    result = await request.json()
    with db.get_conn() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(404)
        payload = json.loads(job["payload_json"])

        if job["type"] == "ocr":
            fields = result.get("fields")
            if not isinstance(fields, dict):
                raise HTTPException(400, "OCR 結果には fields (dict) が必要です")
            doc_id = payload["document_id"]
            for key, f in fields.items():
                conn.execute(
                    """INSERT INTO extractions
                         (document_id, field_key, value_extracted, confidence, evidence)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT (document_id, field_key) DO UPDATE SET
                         value_extracted = excluded.value_extracted,
                         confidence = excluded.confidence,
                         evidence = excluded.evidence,
                         updated_at = datetime('now', 'localtime')""",
                    (doc_id, key, f.get("value"), f.get("confidence"), f.get("evidence")),
                )
            conn.execute(
                "UPDATE documents SET status = 'awaiting_review', error = NULL WHERE id = ?",
                (doc_id,),
            )

        # 最後に置く。CAS に負けた場合は 409 で例外が飛び、上の書き込みごと
        # トランザクションが巻き戻る
        _finish_job(conn, job_id, "done", result)
    return {"ok": True}


@app.post("/api/agent/jobs/{job_id}/fail")
async def api_agent_fail(job_id: int, request: Request):
    body = await request.json()
    error = body.get("error", "unknown error")
    with db.get_conn() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(404)
        payload = json.loads(job["payload_json"])
        _finish_job(conn, job_id, "error", {"error": error})
        if job["type"] == "ocr":
            conn.execute(
                "UPDATE documents SET status = 'error', error = ? WHERE id = ?",
                (error, payload["document_id"]),
            )
    return {"ok": True}


@app.exception_handler(HTTPException)
def http_exc_handler(request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
