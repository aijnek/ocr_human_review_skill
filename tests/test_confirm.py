"""確定時の修正差分。value_corrected は OCR 精度を測るための監査列なので、
誤って埋まると指標そのものが壊れる。
"""

from app import db
from tests.conftest import count, document_status, extraction


def seed_extraction(document_id, field_key, value_extracted):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO extractions (document_id, field_key, value_extracted, confidence)"
            " VALUES (?, ?, ?, 0.9)",
            (document_id, field_key, value_extracted),
        )


def confirm(client, document_id, fields):
    return client.post(f"/api/documents/{document_id}/confirm", json={"fields": fields})


def test_unchanged_value_is_not_recorded_as_a_correction(client, reviewable):
    doc_id, _ = reviewable
    assert confirm(client, doc_id, {"person_name": "田中太郎"}).status_code == 200
    assert extraction(doc_id, "person_name")["value_corrected"] is None


def test_changed_value_is_recorded(client, reviewable):
    doc_id, _ = reviewable
    confirm(client, doc_id, {"person_name": "田中花子"})
    row = extraction(doc_id, "person_name")
    assert row["value_corrected"] == "田中花子"
    assert row["value_extracted"] == "田中太郎", "抽出値は監査のため残る"


def test_reverting_a_correction_clears_it(client, reviewable):
    doc_id, _ = reviewable
    confirm(client, doc_id, {"person_name": "田中花子"})
    assert extraction(doc_id, "person_name")["value_corrected"] == "田中花子"

    confirm(client, doc_id, {"person_name": "田中太郎"})
    assert extraction(doc_id, "person_name")["value_corrected"] is None


def test_blank_value_for_null_extraction_is_not_a_correction(client, reviewable):
    doc_id, _ = reviewable
    seed_extraction(doc_id, "job_title", None)
    confirm(client, doc_id, {"job_title": ""})
    assert extraction(doc_id, "job_title")["value_corrected"] is None


def test_blank_value_for_missing_extraction_is_not_a_correction(client, reviewable):
    """エージェントが値を返さなかったフィールドを空欄のまま確定しただけで
    「人間が修正した」と記録されると、精度指標が幻の修正を数えてしまう。"""
    doc_id, _ = reviewable
    assert extraction(doc_id, "job_title") is None
    confirm(client, doc_id, {"job_title": ""})
    assert extraction(doc_id, "job_title")["value_corrected"] is None


def test_filling_a_missing_extraction_is_a_correction(client, reviewable):
    doc_id, _ = reviewable
    confirm(client, doc_id, {"job_title": "保育士"})
    assert extraction(doc_id, "job_title")["value_corrected"] == "保育士"


def test_keys_outside_the_schema_are_dropped(client, reviewable):
    doc_id, _ = reviewable
    confirm(client, doc_id, {"person_name": "田中太郎", "bogus_key": "x"})
    assert extraction(doc_id, "bogus_key") is None
    assert client.get("/api/records").json()["records"][0]["data"] == {"person_name": "田中太郎"}


def test_status_guard_and_reconfirm(client, claimed):
    doc_id, job_id = claimed
    assert document_status(doc_id) == "ocr_running"
    assert confirm(client, doc_id, {"person_name": "x"}).status_code == 409

    client.post(
        f"/api/agent/jobs/{job_id}/complete",
        json={"fields": {"person_name": {"value": "田中太郎", "confidence": 0.9}}},
    )
    assert confirm(client, doc_id, {"person_name": "田中太郎"}).status_code == 200
    # 確定済みからの再確定は許可され、records は増えず更新される
    assert confirm(client, doc_id, {"person_name": "田中花子"}).status_code == 200
    assert count("records") == 1
    assert client.get("/api/records").json()["records"][0]["data"] == {"person_name": "田中花子"}


def test_confirm_unknown_document(client):
    assert confirm(client, 99999, {"person_name": "x"}).status_code == 404


def test_records_crud_round_trip(client, reviewable):
    doc_id, _ = reviewable
    record_id = confirm(client, doc_id, {"person_name": "田中太郎"}).json()["record_id"]

    listing = client.get("/api/records").json()
    assert listing["records"][0]["filename"] == "sample1_zaiseki_himawari.pdf"
    assert listing["schema"]["name"] == "employment_certificate"

    update = client.put(f"/api/records/{record_id}", json={"data": {"person_name": "山田"}})
    assert update.status_code == 200
    assert client.get("/api/records").json()["records"][0]["data"] == {"person_name": "山田"}

    assert client.put("/api/records/99999", json={"data": {}}).status_code == 404

    assert client.delete(f"/api/records/{record_id}").status_code == 200
    assert count("records") == 0
