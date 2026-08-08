---
name: ocr-human-review
description: >
  アップロードされた PDF/画像 (在籍証明書など) を OCR し、ローカル Web アプリで
  人間がレビュー・修正して SQLite に保存するワークフローを起動する。
  ユーザーが「OCRレビューを開始」「証明書を読み取りたい」「human review を起動」
  などと言ったときに使う。起動後はジョブポーリングのループに入る。
---

# OCR Human-Review ワークフロー

あなた (エージェント) はこのワークフローの **OCR・チャット回答ワーカー** である。
Web アプリは LLM を呼ばない。文書の読み取りとチャット回答はすべてあなたが行う。

すべてのコマンドはプロジェクトルート (この SKILL.md がある `.claude/skills/ocr-human-review/` の 2 つ上のディレクトリ) で実行する。

## 1. 起動

1. サーバーをバックグラウンドで起動する:
   ```
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
   ```
   (Bash の run_in_background を使う。既に起動済みなら `curl -s http://127.0.0.1:8765/api/status` で確認してスキップ)
2. ブラウザで `http://localhost:8765` を開く (`open http://localhost:8765`、または Browser pane が使える環境ならそちらで開く)。
3. ユーザーに「アプリを起動しました。ブラウザから PDF/画像をアップロードしてください」と伝え、すぐに次のポーリングループに入る。

## 2. ポーリングループ

以下をフォアグラウンドで実行して待機する (Bash timeout は 300000ms に設定):

```
uv run python scripts/poll.py --timeout 230
```

出力 JSON の `status` に応じて処理する:

- **`timeout`**: 何もせず即座に再度 poll する。ユーザーへの報告は不要。
- **`job`**: 下記のジョブ処理を行い、完了したら即座に再度 poll する。
- **`shutdown`**: ユーザーが UI で「セッション終了」を押した。バックグラウンドのサーバーを停止し、ループを終えてユーザーに完了報告する。
- **`server_unreachable`**: サーバーを起動 (再起動) して再度 poll する。それでも失敗する場合のみユーザーに報告する。

ポーリング中に別の作業をしない。ユーザーから中断・別の指示があった場合はそちらを優先してよい (ループはいつでも `poll.py` の再実行で再開できる)。

## 3. OCR ジョブ (`job.type == "ocr"`)

`job.payload` には `document_id`, `file_path`, `schema` (抽出スキーマ) が入っている。

1. `file_path` のファイルを **Read ツールで読む** (PDF/画像は vision で読める)。
2. `schema.fields` の **全フィールド** について次の形式で抽出する:
   - `value`: 抽出した値 (文字列)。文書に存在しない・判読不能なら空文字列 `""`。
   - `confidence`: 0.0〜1.0。判読が曖昧な場合は正直に低くする。存在しないフィールドは 0.0。
   - `evidence`: 根拠となる文書中の原文の抜粋。存在しない場合はその旨を書く。
3. 抽出ルール:
   - **絶対に値を創作しない**。読めないものは空欄 + 低 confidence にする。人間がレビューで直すことが前提。
   - `type: date` のフィールドは `YYYY-MM-DD` に正規化する。和暦 (平成・令和) は西暦に変換する (例: 平成2年5月12日 → 1990-05-12)。日までない場合は分かる粒度で (例: 2021-10)。
   - 「現在に至る」「在職中」の終了日は空文字列にし、evidence にその旨を書く。
   - 各フィールドの `hint` に従う。
4. 結果 JSON を一時ファイルに書き、POST する:
   ```
   uv run python scripts/complete.py <job.id> --result /path/to/result.json
   ```
   形式: `{"fields": {"<field_key>": {"value": "...", "confidence": 0.95, "evidence": "..."}, ...}}`
5. ファイルが読めない・壊れている場合は失敗を報告する:
   ```
   uv run python scripts/complete.py <job.id> --fail "理由"
   ```

## 4. チャットジョブ (`job.type == "chat"`)

`job.payload` には `message` (質問), `history` (直近の会話), `db_path`, `schema` が入っている。

1. 必要に応じて SQLite を **読み取り専用** で照会する:
   ```
   sqlite3 -readonly data/app.db "SELECT ..."
   ```
   主なテーブル: `records` (確定データ。`data_json` にスキーマのフィールドが JSON で入る),
   `documents` (アップロード文書とステータス), `extractions` (抽出値と修正値)。
2. 質問に日本語で簡潔に回答し、POST する:
   ```
   echo '{"answer": "回答テキスト"}' | uv run python scripts/complete.py <job.id>
   ```
   (回答に引用符等が含まれる場合は一時ファイル + `--result` を使う)
3. DB を変更する SQL は実行しない。データの編集・削除は管理画面 (`/admin`) に誘導する。

## 補足

- 動作確認用のサンプル文書がない場合は `uv run python scripts/make_samples.py` で `samples/` に生成できる (ユーザーに求められたときのみ)。
- DB の実体は `data/app.db`、アップロードファイルは `data/uploads/`。
