"""抽出スキーマ (schemas/*.yaml) のローダー。"""
from pathlib import Path

import yaml

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


def list_schemas() -> list[dict]:
    return [load_schema(p.stem) for p in sorted(SCHEMAS_DIR.glob("*.yaml"))]


def load_schema(name: str) -> dict:
    path = SCHEMAS_DIR / f"{name}.yaml"
    with open(path, encoding="utf-8") as f:
        schema = yaml.safe_load(f)
    if schema.get("name") != name:
        raise ValueError(f"schema name mismatch: file={name}, name={schema.get('name')}")
    return schema


def field_labels(schema: dict) -> dict[str, str]:
    return {f["key"]: f["label"] for f in schema["fields"]}
