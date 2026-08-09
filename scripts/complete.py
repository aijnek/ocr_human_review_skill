#!/usr/bin/env python3
"""エージェント用: ジョブの結果をアプリに POST する。

使い方:
    uv run python scripts/complete.py JOB_ID --result path/to/result.json
    uv run python scripts/complete.py JOB_ID --fail "エラー内容"

result.json の形式:
    {"fields": {"<field_key>": {"value": "...", "confidence": 0.95,
                                "evidence": "根拠となる原文"}, ...}}
"""

import argparse
import json
import sys
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id", type=int)
    parser.add_argument("--result", help="結果 JSON ファイルのパス (省略時は stdin から読む)")
    parser.add_argument("--fail", help="ジョブを失敗として報告する場合のエラーメッセージ")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    if args.fail is not None:
        endpoint = f"{args.base_url}/api/agent/jobs/{args.job_id}/fail"
        body = {"error": args.fail}
    else:
        endpoint = f"{args.base_url}/api/agent/jobs/{args.job_id}/complete"
        if args.result:
            with open(args.result, encoding="utf-8") as f:
                body = json.load(f)
        else:
            body = json.load(sys.stdin)

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            print(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": e.read().decode("utf-8")}, ensure_ascii=False))
        sys.exit(1)
    except urllib.error.URLError as e:
        print(json.dumps({"error": f"server unreachable: {e}"}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
