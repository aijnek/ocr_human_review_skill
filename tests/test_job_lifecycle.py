"""ジョブキュー越しの状態遷移プロトコル。本スイートの中核。"""

import json

from tests.conftest import SAMPLE_PDF, count, document_status, job_status, upload

OCR_RESULT = {
    "fields": {
        "person_name": {"value": "田中太郎", "confidence": 0.95, "evidence": "氏名 田中太郎"},
        "facility_name": {"value": "ひまわり保育園", "confidence": 0.9, "evidence": "施設名欄"},
        "employment_start": {
            "value": "2019-04-01",
            "confidence": 0.8,
            "evidence": "平成31年4月1日",
        },
    }
}


def test_full_arc_upload_to_confirmed(client):
    """アップロード → 取得 → OCR 結果投入 → 確定までの一周。"""
    doc_id = upload(client, SAMPLE_PDF).json()["created"][0]
    assert document_status(doc_id) == "uploaded"
    assert count("jobs") == 1

    res = client.get("/api/agent/jobs/next?wait=0").json()
    assert res["status"] == "job"
    job = res["job"]
    assert job["type"] == "ocr"
    # SKILL.md がエージェントに約束している payload の形
    payload = job["payload"]
    assert payload["document_id"] == doc_id
    assert payload["file_path"].endswith(".pdf")
    assert [f["key"] for f in payload["schema"]["fields"]][:1] == ["person_name"]
    assert job_status(job["id"]) == "running"
    assert document_status(doc_id) == "ocr_running"

    assert client.post(f"/api/agent/jobs/{job['id']}/complete", json=OCR_RESULT).status_code == 200
    assert job_status(job["id"]) == "done"
    assert document_status(doc_id) == "awaiting_review"

    detail = client.get(f"/api/documents/{doc_id}").json()
    assert detail["page_count"] == 1
    by_key = {e["field_key"]: e for e in detail["extractions"]}
    assert by_key["person_name"]["value_extracted"] == "田中太郎"
    assert by_key["person_name"]["confidence"] == 0.95
    assert by_key["person_name"]["evidence"] == "氏名 田中太郎"

    fields = {k: v["value"] for k, v in OCR_RESULT["fields"].items()}
    res = client.post(f"/api/documents/{doc_id}/confirm", json={"fields": fields})
    assert res.status_code == 200
    assert document_status(doc_id) == "confirmed"

    records = client.get("/api/records").json()["records"]
    assert len(records) == 1
    assert records[0]["data"] == fields


def test_double_complete_is_rejected(client, claimed):
    _, job_id = claimed
    assert client.post(f"/api/agent/jobs/{job_id}/complete", json=OCR_RESULT).status_code == 200
    res = client.post(f"/api/agent/jobs/{job_id}/complete", json=OCR_RESULT)
    assert res.status_code == 409


def test_fail_after_done_is_rejected(client, claimed):
    """完了済みジョブを後から fail できると、確定済み文書が error に戻ってしまう。"""
    doc_id, job_id = claimed
    client.post(f"/api/agent/jobs/{job_id}/complete", json=OCR_RESULT)
    client.post(f"/api/documents/{doc_id}/confirm", json={"fields": {"person_name": "田中太郎"}})
    assert document_status(doc_id) == "confirmed"

    res = client.post(f"/api/agent/jobs/{job_id}/fail", json={"error": "後出しの失敗報告"})
    assert res.status_code == 409
    assert document_status(doc_id) == "confirmed", "確定済み文書が巻き戻ってはいけない"


def test_complete_rejects_malformed_body(client, claimed):
    _, job_id = claimed
    assert client.post(f"/api/agent/jobs/{job_id}/complete", json={}).status_code == 400
    res = client.post(f"/api/agent/jobs/{job_id}/complete", json={"fields": "not a dict"})
    assert res.status_code == 400
    assert job_status(job_id) == "running", "不正なボディでジョブを消費してはいけない"


def test_fail_marks_document_with_error(client, claimed):
    doc_id, job_id = claimed
    res = client.post(f"/api/agent/jobs/{job_id}/fail", json={"error": "読み取り不能"})
    assert res.status_code == 200
    assert job_status(job_id) == "error"
    assert document_status(doc_id) == "error"
    assert client.get(f"/api/documents/{doc_id}").json()["document"]["error"] == "読み取り不能"
    with_result = client.get("/api/status").json()
    assert with_result["active_jobs"] == 0


def test_empty_queue_times_out(client):
    assert client.get("/api/agent/jobs/next?wait=0").json() == {"status": "timeout"}


def test_shutdown_is_consumed_exactly_once(client):
    assert client.get("/api/status").json()["shutdown_requested"] is False
    client.post("/api/shutdown")
    # status は覗くだけで消費しない
    assert client.get("/api/status").json()["shutdown_requested"] is True
    assert client.get("/api/status").json()["shutdown_requested"] is True

    assert client.get("/api/agent/jobs/next?wait=0").json() == {"status": "shutdown"}
    # 受け取った時点でリセットされ、次のセッションを妨げない
    assert client.get("/api/agent/jobs/next?wait=0").json() == {"status": "timeout"}


def test_jobs_are_claimed_in_fifo_order(client):
    for path, name in ((SAMPLE_PDF, "a.pdf"), (SAMPLE_PDF, "b.pdf")):
        upload(client, path, filename=name)
    # 2 通目は内容が同じで重複排除されるため、別内容のジョブを直接積む
    from app import db

    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (type, payload_json) VALUES ('ocr', ?)",
            (json.dumps({"document_id": 1}),),
        )
    first = client.get("/api/agent/jobs/next?wait=0").json()["job"]["id"]
    second = client.get("/api/agent/jobs/next?wait=0").json()["job"]["id"]
    assert first < second
