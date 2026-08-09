"""scripts/poll.py と scripts/complete.py は SKILL.md が依存する契約面。

スクリプト自体のロジックは薄いが、出力の形と終了コードが崩れるとエージェント
ループがレビューではなく実行時に静かに壊れるため、実サーバー相手に検証する。
"""

import json
import socket
import subprocess
import time

import httpx
import pytest

from app import db
from tests.conftest import SAMPLE_PDF

SCRIPTS = db.PROJECT_ROOT / "scripts"


def test_default_base_url_matches_launch_config():
    """poll.py の既定ポートと .claude/launch.json のポートがずれるとスキルが壊れる。"""
    launch = json.loads((db.PROJECT_ROOT / ".claude" / "launch.json").read_text())
    expected = launch["configurations"][0]["port"]
    for script in ("poll.py", "complete.py"):
        source = (SCRIPTS / script).read_text(encoding="utf-8")
        assert f'default="http://127.0.0.1:{expected}"' in source, script


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """実 uvicorn を隔離した data dir で起動する。"""
    import os

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    data_dir = tmp_path_factory.mktemp("agent-scripts-data")
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=db.PROJECT_ROOT,
        env={**os.environ, "OCR_DATA_DIR": str(data_dir)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("uvicorn が起動前に終了した")
        try:
            httpx.get(f"{base}/api/status", timeout=1)
            break
        except httpx.TransportError:
            time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError("uvicorn が起動しなかった")
    yield base
    proc.terminate()
    proc.wait(timeout=10)


def run_script(name, *args):
    return subprocess.run(
        ["uv", "run", "python", str(SCRIPTS / name), *args],
        cwd=db.PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.mark.subprocess
def test_poll_reports_timeout_on_empty_queue(server):
    res = run_script("poll.py", "--timeout", "0", "--base-url", server)
    assert res.returncode == 0
    assert json.loads(res.stdout)["status"] == "timeout"


@pytest.mark.subprocess
def test_poll_and_complete_round_trip(server):
    httpx.post(
        f"{server}/api/upload",
        files={"files": (SAMPLE_PDF.name, SAMPLE_PDF.read_bytes(), "application/pdf")},
    ).raise_for_status()

    polled = json.loads(run_script("poll.py", "--timeout", "0", "--base-url", server).stdout)
    assert polled["status"] == "job"
    job_id = polled["job"]["id"]
    doc_id = polled["job"]["payload"]["document_id"]

    result = json.dumps({"fields": {"person_name": {"value": "田中太郎", "confidence": 0.9}}})
    done = subprocess.run(
        ["uv", "run", "python", str(SCRIPTS / "complete.py"), str(job_id), "--base-url", server],
        cwd=db.PROJECT_ROOT,
        input=result,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    detail = httpx.get(f"{server}/api/documents/{doc_id}").json()
    assert detail["document"]["status"] == "awaiting_review"

    # 二重報告は非ゼロ終了。エージェントが拒否に気づけないと結果を取りこぼす
    again = subprocess.run(
        ["uv", "run", "python", str(SCRIPTS / "complete.py"), str(job_id), "--base-url", server],
        cwd=db.PROJECT_ROOT,
        input=result,
        capture_output=True,
        text=True,
    )
    assert again.returncode == 1
    assert "409" in again.stdout or "not running" in again.stdout
