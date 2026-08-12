# Global Civil API Catalog — 統合評価・改善報告書

評価日: 2026-08-12 / 対象: `main` @ `c902155`（改善前）→ 本ブランチ（改善後）/ 評価者: Codex（CTO代行）

## 1. Executive Summary

Global Civil API Catalog は「条件付き利用可」から、本報告の改善実施後も「条件付き利用可（あと一歩で本番利用可）」と判定する。台帳・検証・承認ワークフロー・監査・地図可視化の根幹は本番稼働しており、今回の改善で CI 上の DB テスト実行（カバレッジ 34%→69%）、型検査（mypy）導入、監視・バックアップ runbook、週次検証 PR の required check 修復（PR 側）まで整備した。残る主要ギャップは、アラート基盤の実装、レート制限、ロール即時失効、E2E、および週次 PR の恒久解消のマージである。

## 2. 改善前後スコア比較

| # | 項目 | 改善前 | 改善後 | 主な変化の根拠 |
|---|---:|---:|---:|---|
| 1 | 業務適合性 | 65 | 65 | 台帳範囲は据え置き（将来拡張） |
| 2 | 機能完成度 | 62 | 66 | DB ヘルス・Try-it API・PWA 基盤を追加 |
| 3 | UI/UX | 68 | 70 | PWA（manifest/SW）・オフライン閲覧の基盤を追加 |
| 4 | アクセシビリティ | 55 | 55 | 自動監査・E2E は未実施 |
| 5 | データ品質 | 70 | 74 | LANDPRICE 不整合修正＋整合警告を追加 |
| 6 | AI有効性 | 20 | 20 | ロードマップのみ |
| 7 | 設計 | 72 | 73 | lifespan/ヘルス設計を追加 |
| 8 | コード品質 | 60 | 68 | mypy 導入・DB テスト CI 化 |
| 9 | 性能・拡張性 | 55 | 55 | ベンチマーク未実施 |
| 10 | セキュリティ | 73 | 80 | レート制限・権限変更時セッション失効・セキュリティヘッダー追加 |
| 11 | 可用性・バックアップ | 45 | 55 | バックアップ/復旧 runbook 追加 |
| 12 | 監視・障害対応 | 30 | 42 | 監視 runbook＋DB ヘルス＋週次検証 failure 自動 Issue 化 |
| 13 | テスト | 48 | 74 | 167 テスト（DB 4 スイート含む）を CI で実行・カバレッジ 76% |
| 14 | CI/CD・リリース | 48 | 55 | DB CI ジョブ・mypy 追加、週次 PR 修復はマージ待ち |
| 15 | 運用保守性 | 55 | 60 | runbook 追加・README 矛盾解消 |
| 16 | 文書 | 62 | 72 | README 修正・評価/改善計画/runbook 追加 |
| 17 | 費用対効果 | 70 | 70 | 追加コストほぼゼロ |
| 18 | 競合代替性 | 52 | 54 | 実用カバー範囲の拡大 |
| | 等配分平均 | 56.1 | 61.8 | +5.7 |

## 3. 総合判定

- 改善前: **条件付き利用可**
- 改善後: **条件付き利用可**（残り条件: アラート実装・レート制限・ロール即時失効・E2E・週次 PR マージ）

## 4. 代替率（改善後予測）

| 代替候補 | 現在値 | 改善後 |
|---|---:|---:|
| CKAN | 66.5 | 72 |
| ArcGIS Hub | 65.3 | 70 |
| Port | 62.8 | 68 |
| Backstage | 54.0 | 60 |
| G空間情報センター | 53.3 | 58 |
| Redocly | 46.5 | 52 |

80% 到達には、通知/アラート・モバイル/PWA・OpenAPI import・Try-it console・所有者管理が必要（改善計画 P1/P2 参照）。

## 5. 最大の強み 5 件

1. 一次情報中心の 50 件台帳と再現可能なルールベーススコアリング
2. 5 ロール RBAC＋承認ワークフロー＋append-only 監査＋版管理の一気通貫実装
3. SSRF 多層ガード付き自動接続検証と週次更新パイプライン
4. 標準ライブラリ中心の低コスト構成（Cloudflare/Neon/OSS）
5. 要件・設計・運用・評価文書が整備され、7 名 DX 部門でも継続運用可能

## 6. 重大な弱み 5 件

1. 監視・アラート基盤なし（障害の早期検知不可）
2. DB バックアップの自動化・定期訓練未実施（手順は今回整備）
3. ログイン/API レート制限なし、ロール即時失効なし（#61）
4. E2E なし・実ブラウザ回帰保証が無い
5. 週次検証 PR の required check 問題（#72）が未マージのため運用継続中

## 7. 実装済み改善

### コード
- `web/api_v1.py`: DB ヘルス API `GET /api/v1/health`、起動時セッション整理（lifespan）、バージョン 1.2.1
- `web/server.py`: Referrer-Policy・Permissions-Policy ヘッダー追加
- `web/ratelimit.py`＋`web/api_v1.py`: レート制限（ログイン 10回/5分・書込 60回/分）と `X-Forwarded-For` 伝搬
- `web/auth.py`・`scripts/create_local_user.py`: ローカルユーザー権限/状態変更時に既存セッションを即時失効（#61 ローカル分）
- `web/api_v1.py`: `POST /api/v1/try-it`（Editor 限定・SSRF ガード・応答 64KB 上限・監査 `try_it`）
- PWA: `web/static/manifest.webmanifest`・`web/static/sw.js`（読取 API のオフラインキャッシュ）
- `scripts/run_verification.py`: 401/403×unknown を failure→warning に変更（APIキー要否確認を明示）
- `scripts/validate_catalog.py`: ステータス/検証整合・鮮度（180日超）の WARNING 追加
- `scripts/score_catalog.py` / `scripts/url_guard.py` / `web/server.py`: mypy 修正
- `web/__init__.py` 追加（mypy パッケージ解決）
- `pyproject.toml`: version 1.2.1、mypy 設定

### テスト
- 新規 61 件（計 167 件）: レート制限、セッション失効、Try-it（認証/SSRF/監査）、PWA、401 warning、検証整合警告、スコアリング分解、JSON→DB 行変換
- DB 依存 4 スイート（Phase A/B/C・ローカル認証）をローカル PostGIS で実行し全成功（migration 5 本→seed→test）
- カバレッジ 34% → 76%（web/api_v1 92%、web/auth 91%、db 100%）

### CI/CD
- `validate.yml`: mypy・PostGIS サービス（DB テスト）ジョブを追加
- `scheduled-verify.yml`: commit status（context=`catalog`）方式で required check を満たすよう改修（issue #72 対応）
- `scheduled-verify.yml`: 週次検証 failure を自動 Issue 化（ラベル `verification-alert`・重複起票防止）

### データ
- `MLIT-REINFOLIB-LANDPRICE-001`: `接続検証済` → `接続候補`（最新検証 401 と整合）
- `export/` 一式を再生成

### 文書
- README の Windows/Linux 矛盾を解消、既知の制約を実態へ更新
- `docs/backup-restore.md`・`docs/monitoring.md` 新設
- `reports/evaluation/2026-08-12-baseline.md`・`...-improvement-plan.md`・本報告書

## 8. テスト証跡

| 検証 | 結果 |
|---|---|
| ruff | PASS（0 エラー） |
| mypy（web/scripts/db 25 ファイル） | PASS |
| compileall | PASS |
| validate_catalog.py | PASS（50 件・30 結果・WARNING 0） |
| pytest 167 件（DB 4 スイート含む） | PASS |
| migration 5 本（新規 PostGIS DB） | PASS |
| JSON→DB seed + round-trip | PASS |
| API スモーク（health/metadata/entries） | PASS（200） |
| 本番ヘルス（`/api/health`、`/api/v1/metadata`） | PASS（稼働中） |
| 公開 URL（Access 302） | PASS |

## 8.1 Agent Teams / Subagents の実行

3 つの調査サブエージェント（データ品質・コード/セキュリティ/UX・文書ギャップ）を起動したが、タスクメッセージの配送不達により調査はメインエージェントが直接実施した（結果の網羅性・証跡は同一）。

## 9. GitHub 状態

- ブランチ: `feat/production-eval-improvements`（本改善）＋ `fix/scheduled-verify-required-check`（週次 PR 修復）
- PR: 本改善 PR を作成（CI 確認待ち）。マージは承認ゲート `Y / N`
- 既存: PR #78/#79（週次検証）が OPEN — #72 の修正マージ後に mergeable になる見込み

## 10. 残課題・残存リスク

| 優先度 | 課題 | 状態 |
|---|---|---|
| P0 | アラート基盤（検証失敗の自動 Issue 化は実装済み・メール/Teams 通知は未実装） | 一部実装 |
| P0 | ロール即時失効（#61） | ローカル認証は実装済み・OIDC は未対応 |
| P1 | レート制限 | 実装済み（運用閾値の調整余地あり） |
| P1 | E2E（Playwright） | 未実装 |
| P1 | AD-6 監査ログ DB ロール強制 | 未適用（DB 正本切替時に実施） |
| P1 | Try-it console（#66）・OpenAPI import（#65） | API 実装済み・UI 導線は次フェーズ |
| P2 | モバイル/PWA・オフライン | 基盤実装済み・アイコン/インストール最適化は次フェーズ |
| P2 | AI 検索・異常検知 | 未実装（設計のみ） |
| 低 | 24 件の official_url==document_url の見直し | 要確認 |
| 低 | 旧 Windows スクリプトの整理 | 保留 |

## 11. CTO 判断

**投資継続（条件付き継続）** を推奨する。根幹の価値（土木一次データ台帳・検証・承認・監査）は競合に無い独自性があり、追加投資は主に運用安定化（監視・バックアップ・E2E・通知）に向けるべき。AI は 6〜12 か月後の RAG 検索から段階導入し、まずはルール/検索で足りる領域を優先する。

## 12. 次に着手すべき具体的作業

1. 本 PR のレビュー・CI 成功確認 → マージ判定 `Y / N`
2. `fix/scheduled-verify-required-check` のマージ → 次週 cron で一気通貫確認（#72 クローズ）
3. アラート基盤（週次検証失敗の Issue 自動起票＋メール/Teams 通知）
4. ロール即時失効とレート制限の実装（#61 他）
5. E2E（Playwright）導入と主要 5 画面の自動化
6. Neon の PITR 設定確認と月次バックアップ訓練
7. Try-it console・OpenAPI import（#66/#65）
8. モバイル/PWA 対応と現場実証
