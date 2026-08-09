#!/usr/bin/env python3
"""エージェント用: ジョブキューを long-poll して次のジョブを JSON で stdout に出力する。

使い方:
    uv run python scripts/poll.py --timeout 230

出力 (JSON):
    {"status": "job", "job": {"id": ..., "type": "ocr", "payload": {...}}}
    {"status": "timeout"}            # ジョブなし。再実行してよい
    {"status": "shutdown"}           # UI から終了指示。ループを抜ける
    {"status": "server_unreachable"} # サーバー未起動/停止
"""
import argparse
import json
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=230, help="long-poll 待機秒数")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    url = f"{args.base_url}/api/agent/jobs/next?wait={args.timeout}"
    try:
        with urllib.request.urlopen(url, timeout=args.timeout + 30) as res:
            print(res.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as e:
        print(json.dumps({"status": "server_unreachable", "error": str(e)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
