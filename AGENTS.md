# Repository Guidelines

## プロジェクト構成とモジュール方針

このリポジトリは、Global Civil API Catalog の要件定義と詳細仕様を起点に構築します。`Global-Civil-API-Catalog_要件定義書.md` を要件の正本、`Global-Civil-API-Catalog_詳細仕様設計書.md` を実装方針の正本として扱ってください。

今後の想定構成は次のとおりです。

- `docs/`: 要件、詳細設計、利用方針、検証計画、出力済み台帳。
- `data/`: `api_catalog.yaml`、`categories.yaml`、`verification_results.json` などの台帳データ。
- `samples/`: サンプルリクエスト、レスポンス、スクリーンショット。
- `scripts/`: 検証、Markdown出力、接続確認、各種コネクタ。
- `web/`: 将来のWeb UIソースと公開アセット。
- `tests/`: スキーマ、スコアリング、出力、コネクタのテスト。

## ビルド・テスト・開発コマンド

現時点の作業ツリーには、実行可能なビルドやテスト設定はまだありません。実装追加後は、次のようなリポジトリ内コマンドを優先してください。

- `python scripts/validate_catalog.py`: 台帳データの必須項目とスキーマを検証する。
- `python scripts/export_markdown.py`: YAML/JSONからMarkdown成果物を再生成する。
- `python scripts/run_verification.py`: 外部API接続確認を実行し、検証結果を更新する。
- `cd web && npm install && npm run dev`: `package.json` 追加後にWeb UIを起動する。

新しいコマンドを追加した場合は、`README.md` に用途と実行例を追記してください。

## コーディング規約と命名規則

ドキュメントはMarkdown、台帳データはYAML/JSON、検証・出力処理はPython 3.12を基本とします。Pythonファイル、スクリプト名、JSON/YAMLキーは snake_case を使用してください。API IDは `GSI-TILE-STD-001` のように、提供元・種別・連番が分かる安定した形式にします。`api_key_required`、`connection_status`、`trust_rank` などの項目名は詳細仕様と一致させてください。

## テスト方針

Pythonスクリプトを追加する場合は `pytest` を前提に `tests/` 配下へテストを置きます。ファイル名は `test_<対象>.py` とし、例として `test_catalog_schema.py`、`test_export.py` を使用します。必須項目、スコアリング、Markdown出力、接続失敗時の処理を優先して検証してください。外部APIに依存するテストは、明示的に統合テストとして分離します。

## コミットとプルリクエスト

提供されたGitHubリポジトリの履歴は初期コミットのみのため、確立済みのコミット規約はまだありません。コミットメッセージは `Add catalog schema validation` のように短い命令形を推奨します。

プルリクエストには、目的、変更範囲、実施した検証、影響するAPIソースを記載してください。関連Issueがあればリンクし、Web UI変更ではスクリーンショットを添付します。APIキー、社内機密、個人情報、本番データはコミットしないでください。

## セキュリティと設定

APIキーは環境変数またはシークレット管理に保存し、台帳本文へ平文で記録しないでください。サンプルレスポンスは最小限にし、機密情報を除去してから保存します。各APIには公式URL、利用条件、商用利用可否、最終確認日を必ず記録してください。
