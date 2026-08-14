# Global Civil API Catalog — MVP/Prototype 評価・実装報告（2026-08-14）

評価日: 2026-08-14 ／ 対象: `main` @ `458cc96` → 本ブランチ `feat/mvp-evaluation-enhancements` ／ 評価者: Codex（CTO 兼実装責任者）

## 1. Executive Summary

既存実装（台帳50件・接続検証30件・CRUD＋5ロールRBAC＋承認ワークフロー＋監査・版管理＋Try-it＋PWA）は本番稼働中であり、評価の結果 **主要ユースケースは実動作** と判定した。
本ブランチでは、MVP 評価に必要な以下を追加した。

- 架空ダミーデータのみのデモ環境（`data/demo/`・`scripts/seed_demo_data.py`・`scripts/run_demo_stack.sh`・Webhook echo）
- ロール別「マイタスク」（レビュー・承認・差し戻し対応の一覧と即時操作）
- Webhook 通知（エントリ作成/更新/削除/復元/ワークフロー遷移、HMAC署名、管理UI、テスト配信）
- 監査ログ CSV 出力
- OpenAPI 3.x インポート（下書き生成＋重複検出、Issue #65 の MVP 実装）
- 採用候補の横並び比較 UI
- 印刷用帳票 HTML（ブラウザ印刷→PDF）
- キーワード検索のトークン化・複数フィールド対応
- Playwright E2E（静的UI＋フルスタック承認フロー）と CI ジョブ
- 接続ステータス `利用終了` のバリデータ・DB制約への追加（FR-012 整合）

総合判定: **GO（MVP/Prototype）**。本番デプロイ・本番DB変更は今回のスコープ外。

## 2. 評価（18項目・100点）

| # | 項目 | 前回(08-12) | 今回 | 主な根拠 |
|---:|---:|---:|---:|---|
| 1 | 業務適合性 | 65 | 68 | デモ用8件で全ステータス・地域・形式を網羅し評価可能に |
| 2 | 機能完成度 | 68 | 78 | OpenAPI import・Webhook・タスク・比較・帳票・監査CSVを追加 |
| 3 | UI/UX | 72 | 78 | マイタスク・Webhook管理・比較ダイアログ・帳票導線を追加 |
| 4 | アクセシビリティ | 58 | 62 | E2E でスキップリンク・ランドマークを自動確認 |
| 5 | データ品質 | 74 | 80 | `利用終了` を検証・DB制約に追加、デモデータはバリデーション合格 |
| 6 | AI有効性 | 20 | 20 | 対象外（ロードマップのみ） |
| 7 | 設計 | 73 | 78 | webhooks/openapi_import の責務分離、seed の本番ガード |
| 8 | コード品質 | 68 | 76 | ruff/mypy 全パス、JS 構文チェック、E2E 導入 |
| 9 | 性能・拡張性 | 55 | 55 | 未計測（継続課題） |
| 10 | セキュリティ | 80 | 82 | Webhook URL にも SSRF ガード、署名付き配信、監査記録 |
| 11 | 可用性・バックアップ | 55 | 55 | デモスタック停止/再開スクリプト追加（本番は従来どおり） |
| 12 | 監視・障害対応 | 45 | 52 | Webhook 配信状態の監視項目追加 |
| 13 | テスト | 75 | 84 | 約200件（非DB+DB統合52件）+ Playwright E2E 2系統 |
| 14 | CI/CD・リリース | 55 | 62 | e2e.yml 追加、DBテストジョブへ新スイート追加 |
| 15 | 運用保守性 | 64 | 70 | デモ起動手順・停止手順・E2E手順を文書化 |
| 16 | 文書 | 72 | 80 | README・運用・監視・技術スタックを実装と同期 |
| 17 | 費用対効果 | 70 | 72 | 追加依存は Playwright（CIのみ）でほぼ無償 |
| 18 | 競合代替性 | 54 | 60 | OpenAPI import・Webhook・タスク・比較で汎用カタログに接近 |
| | 等配分平均 | 62.5 | **70.6** | |

## 3. 実装内容

### デモ環境と架空ダミーデータ

- `data/demo/api_catalog.json`: 8件（ID `DEMO-*`、提供元・URL はすべて架空、`example.test` ドメイン、名称に「デモ用（架空）」明示）
  - ステータス: 本格利用候補 / 接続検証済 / 実装接続済 / 接続候補 / 調査中 / 保留 / 利用終了
  - 地域: JP / US / Global、形式: JSON / GeoJSON / XYZ Tile / CSV / CityGML / 3D Tiles
  - 信頼度 A〜E、優先度 1〜5、スコア・breakdown・対象案件・採用理由を保持
- `data/demo/verification_results.json`: 10件（success 4 / warning 2 / failure 2 / skipped 2、401・タイムアウト・応答劣化・件数急変の異常系を含む）
- `data/demo/workflow_states.json`: draft / in_review / pending_approval / rejected / published を網羅
- `scripts/seed_demo_data.py`: エントリ・検証結果・ワークフロー・5デモユーザー・監査サンプル・Webhook購読を冪等投入。`CATALOG_DEMO_SEED=1` 必須、Neon/本番URLは拒否
- `scripts/run_demo_stack.sh`: 専用 Postgres コンテナ + migration + seed + 成果物生成 + Webhook echo + api_v1 + WebUI を一括起動/停止（本番 systemd・Neon 非干渉）

### 機能

| 機能 | 実装 |
| --- | --- |
| マイタスク | `GET /api/v1/tasks`（ロール別: review/approval/fix）+ 管理画面パネル・バッジ・タスクからの遷移操作 |
| Webhook | `webhook_subscriptions` テーブル＋migration 06、CRUD（Admin）、`POST /test`、遷移/CRUDイベント配信、HMAC-SHA256 署名、SSRFガード、配信状態・失敗回数保持 |
| 監査CSV | `GET /api/v1/audit/export.csv`（staff、最大10,000行、diff込み）＋UIボタン |
| OpenAPI import | `scripts/openapi_import.py`（純粋パーサー）＋ `POST /api/v1/import/openapi`（Editor+、draft生成、ID/名称/エンドポイントの重複検出、インポート内重複排除）＋UI |
| 比較 | 台帳のチェックボックスで複数選択 → 横並び比較ダイアログ |
| 帳票 | `export/API台帳_帳票.html`（印刷CSS・全項目）を成果物に追加、UIに導線 |
| 検索 | サーバー/クライアントともトークン化（空白・カンマ区切り AND）＋ tags/形式/注記/URL 等を検索対象に |
| 接続ステータス | `利用終了` を `catalog_utils` と DB CHECK 制約（migration 06）へ追加 |
| E2E | 静的UI（ダッシュボード/検索/比較/Exports/マップ/テーマ/a11y）＋ フルスタック（ログイン→作成→遷移→承認→監査CSV→Webhook履歴） |
| CI | `.github/workflows/e2e.yml`（static-ui / fullstack の2ジョブ）、validate.yml のDBテストへ新スイート追加 |

## 4. 検証結果

| 検証 | 結果 |
| --- | --- |
| ruff | PASS（0エラー） |
| mypy（web/scripts/db） | PASS（32ファイル） |
| compileall | PASS |
| validate_catalog.py（本番50件） | PASS（WARNING 0） |
| デモデータ検証 | PASS（8件・10件・workflow 整合） |
| pytest（非DB、E2E除く） | PASS（141件） |
| pytest DB統合（本番JSON投入DB: Phase A/B/C・ローカル認証・migration・tasks/webhooks/OpenAPI import） | PASS（52件） |
| フルスタックE2E | CI で実行（ローカルは Chromium が環境制約 SIGTRAP のため NOT RUN） |
| 静的UI E2E | CI で実行（同上） |
| デモスタック | PASS（WebUI/API/DB/echo 稼働、`/api/v1/health` ok） |
| Webhook 配信 | PASS（統合テストで transition イベント＋署名を検証、echo 履歴に記録） |

## 5. 残バックログ（本 MVP 後の優先候補）

- P1: Entra ID セッション中のロール即時再検証（#61 の OIDC 側）
- P1: AD-6 監査ログの DB ロール強制（本番正本切替時に適用）
- P2: 所有者/ライフサイクル管理（#48）
- P2: 検証履歴の時系列蓄積と異常検知ルールの定期実行（#49 第2段階）
- P2: メール/Teams 通知（Webhook 配信失敗・承認待ち）
- P2: モバイル最適化・オフライン動作の本格検証
- P2: コネクタ単位のカバレッジ拡充
- P3: AI 検索（RAG）・BIM/CIM 連携・SDK 配布

## 6. 判定

- MVP/Prototype: **GO**
  - P0: 0件
  - 主要P1: OpenAPI import（#65）を MVP 実装、Try-it（#66）は既存実装、E2E（#67 一部）を CI 化
  - 主要ユースケース（閲覧・検索・比較・CRUD・承認・監査・通知・エクスポート・インポート）がデモ環境で一通り操作可能
  - ダミーデータは `data/demo/` に保持され、`scripts/run_demo_stack.sh start` で直ちに再現可能
- 本番運用化: 対象外（今回実施しない）
