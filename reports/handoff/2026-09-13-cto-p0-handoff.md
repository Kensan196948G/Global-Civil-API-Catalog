# 引き継ぎメモ — Global-Civil-API-Catalog CTO総合評価 P0/P1対応（2026-09-13）

Task Passport: **TP-FQPZ-7JJF**（`task_passport_new` で作成済み）
※ `task_passport_checkpoint` が `passport_id is required` を返して失敗したため、
  状態は本文書に記録する（パスポート本体の state は作成時の内容のまま）。

## 現在地

| 項目 | 値 |
| --- | --- |
| clone | `/home/kensan/Projects/Mirai-DX-Project/Global-Civil-API-Catalog` |
| branch | `fix/cto-p0-hardening-v2`（origin/main = `2856ad6` から分岐、5コミット） |
| PR | **#98**（作成済み・Required CI 4ジョブすべて success） |
| Issue | **#99**（DB接続先の是正 — 人間の運用判断待ち） |
| 本番 | **無変更**（サービス稼働継続、DB接続先は未修正） |

## 完了した修正（P0/P1）

1. `web/auth.py` — 認証バイパスを許可リスト方式（`{development, demo}`）へ **fail-closed** 化
2. `web/api_v1.py` — `/api/v1/health` が DB 不可時に **503 + `status=degraded`**（+ `env`/`commit`）
3. `db/session.py` — `connect_timeout`（既定5秒）で **fail-fast**。**URLクエリ方式で付与すること**
   （`connect_args` は psycopg3 dialect が破棄する）
4. `scripts/health_check.py` — **DEGRADED**（DBのみ停止）と **FAIL**（プロセス無応答）を区別
5. `.gitignore` — `.env` / `*.env` / `*.dump` / `backups/` を追加
6. `scripts/db_backup.py`（新規）— 日次 `pg_dump`・14世代・取得時 `pg_restore` 検証・sha256
   ＋ `deploy/global-civil-api-catalog-db-backup.{service,timer}`（03:40 JST、稼働中）
   ＋ `deploy/install-systemd-units.sh`
7. ローカルDBへ migration **06→07→08 適用済み**（`alembic current` = `20260906_08` head）
8. `pg_dump`/`pg_restore` を **16系に版固定**（PATH 依存だと復元不能になる2事象を実測で再現→解消）

## 検証結果（実行済み）

```
ruff check .                     -> All checks passed
mypy web scripts db              -> Success: no issues found in 34 source files
python -m pytest (非DB)          -> 194 passed, 6 skipped, 9 deselected
python -m pytest <DB 7ファイル>   -> 63 passed
scripts/validate_catalog.py      -> OK: 50 catalog records, 30 verification results, 0 warning(s)
python scripts/db_backup.py      -> OK / 11 table data entries readable
scratch DB へリストア             -> 全10テーブル件数一致・ID集合md5一致
```
CI（PR #98）: `catalog` / `db-api` / `static-ui` / `fullstack` = **すべて success**

## 未解決（次に必要な作業）

1. **Issue #99 の判断**（人間）: 本番 `~/.config/global-civil-api-catalog/api.env` の
   `CATALOG_DATABASE_URL` を **ローカル PostgreSQL**（推奨: `127.0.0.1:5432/global_civil_api_catalog`）
   にするか、Neon の現行資格情報を再取得するか。
   → 現在 Neon は `password authentication failed` で、**api_v1 の書込/RBAC/監査/承認が停止**。
2. **PR #98 のレビューとマージ**（Auto Merge はしない方針で保留）。
3. マージ後、**承認済み経路でデプロイ**:
   ```bash
   systemctl --user restart global-civil-api-catalog-api.service
   python3 scripts/health_check.py     # DB是正後は "HEALTH: OK" / exit 0 を期待
   ```
4. Phase 1: 主要業務Flow（登録→レビュー→承認→公開→監査→Webhook）の **E2E自動化**、
   **RBAC 全ロール×全エンドポイント自動検証**、**migration自動適用**のデプロイ手順組込。

## 評価サマリ

- 改善前: **52.4点** / 総合判定 **PoC** / 代替率 **43%**
- 改善後: リポジトリ **67.6点** / 本番実効 **59.1点** / 総合判定 **条件付き利用可** / 代替率 **49%**
- Investment Decision: **条件付き継続**
- 詳細: `reports/evaluation/2026-09-13-before-assessment.md` /
  `reports/evaluation/2026-09-13-after-assessment.md`

## 既知の残存リスク

- Critical: 本番DB接続先の停止（#99）、本番未デプロイのため監視改善が未実効
- High: migration自動適用なし / MVPがunit無しの手動プロセスで本番と別コード /
  検証が HTTP 200 のみ / `last_checked_at` が全件固定 / 19件が検証成功済なのに滞留 /
  `X-Forwarded-For` 無検証
- 未確認: 実ブラウザUI操作、axe実測、Cloudflare Accessポリシー内容、Entra実ログイン、
  負荷特性、**独立した第三者セキュリティレビュー**（SubAgent委任がハーネス設定不具合
  「未登録ツール `pwsh`」で2回失敗したため自ら実施）

## ツール上の不具合（記録）

- `subagent_explore` / `subagent_architect` 等の SubAgent 委任が
  `tools.restrict() names unknown global tool "pwsh"` で失敗する（本環境は Linux で pwsh 未登録）。
  → 並列委任が使えず、本作業は Main Agent 単独で実施した。
- `task_passport_checkpoint` が `passport_id is required` を返す（`passport_id` を
  トップレベルで渡しても解消せず）。→ 本文書で代替記録。
