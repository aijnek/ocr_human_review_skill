"""スキーマ YAML はエージェントのプロンプト・DB・レビュー UI の三者間契約。"""

import re

import pytest
import yaml

from app import schemas

# SKILL.md がフィールドごとの正規化ルールを持つ型。ここに無い型は
# エージェント側に扱う手順が存在しないことを意味する。
KNOWN_TYPES = {"string", "date"}


@pytest.fixture
def schema():
    return schemas.load_schema("employment_certificate")


def test_fields_are_well_formed(schema):
    fields = schema["fields"]
    assert len(fields) == 10
    for f in fields:
        assert set(f) >= {"key", "label", "type", "required"}, f
    keys = [f["key"] for f in fields]
    assert len(keys) == len(set(keys)), "field key が重複している"


def test_field_keys_are_safe_identifiers(schema):
    """review.html が f.key を未エスケープで id=/data-key= に埋めるための Python 側ガード。"""
    for f in schema["fields"]:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", f["key"]), f["key"]


def test_field_types_are_known_to_the_agent(schema):
    for f in schema["fields"]:
        assert f["type"] in KNOWN_TYPES, f"{f['key']}: 未知の型 {f['type']}"


def test_load_schema_rejects_name_mismatch(tmp_path, monkeypatch):
    (tmp_path / "foo.yaml").write_text(
        yaml.safe_dump({"name": "bar", "fields": []}), encoding="utf-8"
    )
    monkeypatch.setattr(schemas, "SCHEMAS_DIR", tmp_path)
    with pytest.raises(ValueError, match="mismatch"):
        schemas.load_schema("foo")
