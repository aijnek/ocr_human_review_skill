# OCR Human-Review Skill

アップロードされた PDF/画像 (在籍証明書など) を Claude Code エージェントが OCR・構造化抽出し、
ローカル Web アプリ上で人間がレビュー・修正して SQLite に永続化する Claude Code skill。
[petergyang/human-review](https://github.com/petergyang/human-review) にインスパイアされた構成。

## 仕組み

```
┌──────────────┐    upload/review/confirm     ┌─────────────────────┐
│   ブラウザ    │ ───────────────────────────▶ │  FastAPI (localhost) │
│ (人間)       │ ◀─────────────────────────── │  + SQLite            │
└──────────────┘                              └─────────┬───────────┘
                                                ジョブキュー (jobs)
                                                        │ long-poll
                                            ┌───────────▼───────────┐
                                            │ Claude Code エージェント │
                                            │ poll.py で待機 →        │
                                            │ Read(vision) で OCR →   │
                                            │ 結果を POST             │
                                            └───────────────────────┘
```

- **Web アプリは LLM を呼ばない**。OCR は skill を発動した Claude Code
  エージェントがジョブキュー経由で処理する (LLM コストはユーザーのサブスクリプションに乗る)
- エージェントのポーリングは**バックグラウンド実行** (Bash run_in_background)。待機中も
  Claude Code への入力は通常どおり処理され、ジョブ完了通知でエージェントが処理を再開する。
- OCR エンジン不要。Claude の vision (Read ツール) で PDF/画像を直接読み、
  `schemas/*.yaml` のスキーマに沿って「値 + confidence + 根拠」を抽出する
- 確度の低いフィールドはレビュー画面で色付け表示され、人間が修正して確定する
- 抽出値と修正値は両方 `extractions` に残る (精度の監査・評価に使える)

## 使い方

Claude Code でこのプロジェクトを開き、skill を発動する:

```
/ocr-human-review
```

エージェントがサーバーを起動しブラウザが開くので、PDF/画像をアップロード →
OCR 完了後に「レビュー」からフィールドを確認・修正 → 確定で SQLite に保存される。

- `http://localhost:8765/` — アップロードと受信箱
- `http://localhost:8765/review/{id}` — レビュー画面 (文書プレビュー + 抽出フィールド)
- `http://localhost:8765/admin` — 確定データの確認・編集・削除

保存データについての質問は Claude Code のチャットで直接聞けばよい
(エージェントが `data/app.db` を読み取り専用で照会して答える)。

終了はページ右上の「セッション終了」ボタン。

## 動作確認用サンプル

レイアウトの異なる合成在籍証明書 (PDF ×3、スキャン風 PNG ×1) を生成できる:

```bash
uv run python scripts/make_samples.py
```

## 手動起動 (skill を使わない場合)

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

エージェントワーカーの代わりは `scripts/poll.py` / `scripts/complete.py` を参照。

## 構成

| パス | 役割 |
|---|---|
| `.claude/skills/ocr-human-review/SKILL.md` | skill 定義 (エージェントへの手順書) |
| `app/` | FastAPI アプリ (ページ + API + ジョブキュー) |
| `schemas/employment_certificate.yaml` | 抽出スキーマ (追加すれば他文書タイプに拡張可) |
| `scripts/poll.py` / `scripts/complete.py` | エージェント用ジョブ取得/結果送信 CLI |
| `scripts/make_samples.py` | 合成サンプル生成 |
| `data/` | SQLite (`app.db`)・アップロード・プレビュー (gitignore) |
