# Global Civil API Catalog

国内外の土木建設関連API・公開データを台帳化し、利用条件、APIキー要否、接続検証結果、優先度を管理するための初期実装です。

## 現在のRelease Ready範囲

- API/公開データ台帳50件: `data/api_catalog.json`
- 接続検証結果10件: `data/verification_results.json`
- 初期接続サンプル5件: `scripts/connectors/`
- サンプルリクエスト/レスポンス: `samples/`
- Markdown/CSV/JSON成果物出力: `scripts/export_markdown.py`
- スキーマ、スコアリング、出力、コネクタのテスト: `tests/`
- Docker常駐Web UI: `web/`, `Dockerfile`, `deploy/`

本番公開、認証、DB、外部サービス設定、定期実行は未実装です。

## ディレクトリ構成

```text
data/                 台帳JSONと接続検証結果
docs/                 方針・計画ドキュメント
export/               自動生成される成果物
samples/requests/     curl等のサンプルリクエスト
samples/responses/    最小化したサンプルレスポンス
scripts/              検証・出力・接続サンプル
tests/                自動テスト
web/                  Web UIとJSON API
deploy/               固定ポート、systemdユーザーサービス設定
```

## セットアップ

Python 3.12以上を推奨します。テスト実行には `pytest` が必要です。

```bash
python -m pip install pytest
```

## 主要コマンド

```bash
make check
```

Pythonの構文チェック、台帳検証、テスト、成果物出力をまとめて実行します。

```bash
python scripts/validate_catalog.py
```

台帳と検証結果の必須項目、ID重複、許可値、日付形式を検証します。

```bash
python scripts/export_markdown.py
```

`export/API台帳.md`、`export/接続優先度.md`、`export/接続検証結果.md`、`export/本格利用候補.md` を生成します。

```bash
python scripts/run_verification.py --limit 10
```

オフラインモードで検証対象の実行計画を表示します。実HTTPアクセスを行う場合のみ `--live` を付けてください。

## Web UI

固定ポートは `deploy/PORT.lock` の `49231` です。この番号はサービス登録後に変更しません。

```bash
docker build -t global-civil-api-catalog-web:local .
docker run --rm -p 49231:8080 global-civil-api-catalog-web:local
```

systemdユーザーサービスとして常時起動する場合:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/global-civil-api-catalog-web.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now global-civil-api-catalog-web.service
```

起動後は `http://<host-ip>:49231` でWeb UIを表示します。

この環境では `http://192.168.0.185:49231` として登録済みです。運用メモは `docs/operations.md` を参照してください。

## セキュリティ方針

APIキー、トークン、個人情報、本番データはコミット禁止です。APIキーが必要なデータソースは、キーなしで台帳登録し、接続検証は `skipped` として記録します。サンプルレスポンスは最小化し、大容量バイナリや機密情報を保存しません。

## 仕様書

- `Global-Civil-API-Catalog_要件定義書.md`
- `Global-Civil-API-Catalog_詳細仕様設計書.md`
- `AGENTS.md`
