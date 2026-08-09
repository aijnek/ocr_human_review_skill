"""テンプレートの smoke。Jinja の構文エラーや変数リネームは現状ノーガードで壊れる。"""

import pytest


@pytest.mark.parametrize("path", ["/", "/admin"])
def test_static_pages_render(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert len(res.text) > 500


def test_review_page_embeds_the_whole_schema(client, reviewable):
    """フィールドは SCHEMA_FIELDS (tojson) から JS が描画するので、
    テンプレートがスキーマ全体を渡せているかを見る。"""
    doc_id, _ = reviewable
    res = client.get(f"/review/{doc_id}")
    assert res.status_code == 200
    from app import schemas

    schema = schemas.load_schema("employment_certificate")
    assert schema["title"] in res.text
    for f in schema["fields"]:
        assert f["key"] in res.text, f"{f['key']} がページに含まれていない"


def test_review_page_unknown_document(client):
    assert client.get("/review/99999").status_code == 404
