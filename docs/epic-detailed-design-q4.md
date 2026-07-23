# 📐 Q4 大規模 Epic 詳細設計書（Issue #45〜#49）

> 📅 作成: 2026-07-23 ／ 👔 作成者: CTO 代行（Claude Code）
> 🔗 対象: [#45](https://github.com/Kensan196948G/Global-Civil-API-Catalog/issues/45) 認証基盤 ／ [#46](https://github.com/Kensan196948G/Global-Civil-API-Catalog/issues/46) DB 移行 + CRUD API ／ [#47](https://github.com/Kensan196948G/Global-Civil-API-Catalog/issues/47) 監査・版・承認 ／ [#48](https://github.com/Kensan196948G/Global-Civil-API-Catalog/issues/48) 所有者・ライフサイクル ／ [#49](https://github.com/Kensan196948G/Global-Civil-API-Catalog/issues/49) 品質検証強化
> 📌 位置づけ: 外部評価レポート P0 ロードマップ（ユーザー承認済み Q4 5 大重点項目）の**詳細設計**。実装は本書に基づき epic ごとの子 Issue / PR に分割して行う。

---

## 1. 🎯 全体アーキテクチャ方針

### 1.1 目標構成（To-Be）

```text
[利用者ブラウザ]
   │  HTTPS (Cloudflare Tunnel 経由 / 社内LAN)
   ▼
[FastAPI アプリ (Windows ホスト, uvicorn, Task Scheduler 起動)]
   │  ├─ 静的 UI 配信（現行 web/ 資産を継承）
   │  ├─ REST CRUD API (/api/v1/…)
   │  ├─ OIDC 認証 (Entra ID) + RBAC ミドルウェア
   │  └─ 監査ログ・版管理・承認ワークフロー
   ▼
[Neon PostgreSQL (+PostGIS) — データ正本]
   ├─ branch: production / preview / development
   └─ 週次検証・スコアリングのバッチも DB を読み書き
        │
        ▼（生成物として一方向エクスポート）
[Git リポジトリ: data/*.json, export/*.md = 生成 export 資産]
```

### 1.2 主要アーキテクチャ決定（ADR 要約）

| #    | 決定                                                                                                         | 根拠                                                                                                                                     | 却下案                                                                                                                                 |
| ---- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| AD-1 | 🗄️ DB は **Neon PostgreSQL + PostGIS 拡張**                                                                  | CLAUDE.md §5 標準構成（Neon = 業務データ正本）に整合。branch 機能で dev/preview/prod を分離し migration を非本番で先行検証できる（§13）  | セルフホスト PostgreSQL（Windows ホスト運用負荷・バックアップ責務が増える）、SQLite（§5 で本番正本禁止）                               |
| AD-2 | 🐍 API は **FastAPI + SQLAlchemy 2.x + Alembic**                                                             | 既存ツールチェーンが Python 3.12。型注釈・OpenAPI 自動生成・依存性注入により RBAC/監査の横断実装が容易。Alembic で migration を Git 管理 | 素の `http.server` 拡張（#46 記載どおり不十分）、Node/Workers 化（既存 Python バッチ資産と分断）                                       |
| AD-3 | 🖥️ アプリ実行基盤は **現行 Windows ネイティブ + Task Scheduler を継続**                                      | リポジトリの承認済み本番形態。Cloudflare は Tunnel による公開経路として現行どおり利用                                                    | Cloudflare Workers（Python 実行制約・既存バッチと二重管理）、コンテナ常駐（本番方針変更となり別途承認要）                              |
| AD-4 | 🔁 移行は **expand-and-contract（DB 併走 → 正本切替 → JSON は export 化）**                                  | NFR「台帳データは Git 管理できる形式を優先」を、**DB 正本 + Git は生成 export** という形で両立。切替前はいつでも JSON 正本へ戻せる       | ビッグバン切替（rollback 困難、§19 抵触リスク）                                                                                        |
| AD-5 | 🔑 認証は **Entra ID OIDC (Authorization Code + PKCE) をアプリ層で実装**、ロールは Entra ID App Roles で配布 | Issue #45 指定。App Roles はテナント側で人事異動に追従でき、アプリはトークンの `roles` クレームを読むだけで済む                          | フロントプロキシ (Cloudflare Access) のみでの認証（ロール粒度の API 制御が不可能）、独自パスワード認証（§19 セキュリティ方針に反する） |
| AD-6 | 📜 監査ログは **DB の append-only テーブル + DB ロールで UPDATE/DELETE 権限を剥奪**                          | アプリのバグでも改変不能にする多層防御。§13 の auditability 要件                                                                         | アプリ層のみでの防御（改変可能性が残る）                                                                                               |

### 1.3 実装順序と依存関係

```text
Phase A: #46 スキーマ + 読取 API + 移行スクリプト（併走開始）   ← 基盤・最初に着手
Phase B: #45 OIDC + RBAC（書込 API を保護してから書込系を公開）
Phase C: #47 監査ログ・版管理・承認ワークフロー（書込系と同時稼働）
Phase D: #48 所有者・ライフサイクル（スキーマ拡張 + 運用ルール）
Phase E: #49 検証履歴・異常検知・通知（DB 統合）
```

- ⚠️ **書込系 API は Phase B 完了まで公開しない**（未認証書込を一瞬でも露出させない）。Phase A の間、更新は従来どおり Git/PR 経由。
- 🔀 Phase D / E は Phase C と並行可能（スキーマ所有権が異なるため）。

---

## 2. 🗄️ Epic #46 詳細設計 — PostgreSQL/PostGIS 移行 + CRUD API

### 2.1 スキーマ設計（DDL 概要）

```sql
-- カタログ本体（現 data/api_catalog.json の 1 レコード = 1 行）
CREATE TABLE catalog_entries (
  id            text PRIMARY KEY,              -- 例: 'OPENAQ-API-001'（現行 ID を維持）
  name          text NOT NULL,
  category      text NOT NULL,
  sub_category  text,
  provider      text NOT NULL,
  provider_type text NOT NULL,
  region        text,
  official_url  text NOT NULL,
  document_url  text NOT NULL,                 -- NFR: 提供元ドキュメント URL 必須
  endpoint_template text,
  sample_endpoint   text,
  data_formats  text[] NOT NULL DEFAULT '{}',
  api_key_required text NOT NULL CHECK (api_key_required IN ('required','not_required','unknown')),
  auth_type     text,
  license_note  text,
  commercial_use text,
  update_frequency text,
  connection_status text NOT NULL,             -- 要件定義書 11 章（利用終了を含む 9 値）を lookup 表で管理
  trust_rank    text CHECK (trust_rank IN ('A','B','C','D','E')),
  connection_priority int,
  business_fit_score int,
  integration_score  int,
  score_breakdown jsonb,                       -- 導出値。第1段階は jsonb 保持、将来正規化
  geom          geometry(Geometry, 4326),      -- PostGIS: 提供範囲（国/領域）。当面 NULL 可
  tags          text[] NOT NULL DEFAULT '{}',
  usage_summary text,
  usage_notes   text,
  risk_note     text,
  last_checked_at date,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- 検証結果（現 data/verification_results.json。#49 で時系列蓄積に拡張）
CREATE TABLE verification_results (
  id            text PRIMARY KEY,              -- 'VERIFY-<api_id>-<yyyymmdd>'
  api_id        text NOT NULL REFERENCES catalog_entries(id),
  verified_at   timestamptz NOT NULL,
  verified_by   text NOT NULL,
  result        text NOT NULL CHECK (result IN ('success','failure','warning','skipped')),
  http_status   int,
  response_time_ms int,
  response_size_bytes int,
  record_count  int,
  sample_truncated boolean NOT NULL DEFAULT false,
  error_message text,
  note          text
);
CREATE INDEX ON verification_results (api_id, verified_at DESC);
```

- 📎 `catalog_metadata.json`（件数・ハッシュ）は**テーブル化しない**。エクスポート生成時に導出する（drift の構造的根絶。PR #37 の再発防止）。
- 📎 PostGIS は Neon の `CREATE EXTENSION postgis;` で有効化。座標を持たない現行データは `geom NULL` で開始し、#48 のデータ整備で漸次充足。

### 2.2 API 設計（v1）

| メソッド  | パス                            | 権限（#45 のロール） | 説明                                                                                        |
| --------- | ------------------------------- | -------------------- | ------------------------------------------------------------------------------------------- |
| GET       | `/api/v1/entries`               | 全員（未認証含む）   | 一覧 + フィルタ（category/provider/status/keyword、FR-101〜107 互換）                       |
| GET       | `/api/v1/entries/{id}`          | 全員                 | 詳細                                                                                        |
| POST      | `/api/v1/entries`               | 編集者以上           | 登録（FR-001〜010）                                                                         |
| PUT/PATCH | `/api/v1/entries/{id}`          | 編集者以上           | 更新（FR-011）。接続ステータス変更を含む（利用終了への変更は編集者以上 = 要件定義書 17 章） |
| DELETE    | `/api/v1/entries/{id}`          | 管理者のみ           | 削除（FR-012。実体は論理削除 → #47 と整合）                                                 |
| GET       | `/api/v1/verifications?api_id=` | 全員                 | 検証履歴（#49 で時系列化）                                                                  |
| GET       | `/api/v1/metadata`              | 全員                 | 現 `/api/metadata` 互換（件数・ハッシュは DB から導出）                                     |

- 🧩 既存 WebUI（静的 HTML）の読取系 JSON 契約は**互換維持**（現行 `/api/*` パスをリバースエイリアス）。UI 改修は本 epic のスコープ外。
- 📤 `export/*.md`・`data/*.json` は `scripts/export_markdown.py` を DB 読取に切替えて従来どおり生成（Completion Criteria「静的サイト機能の再現」を充足）。

### 2.3 移行手順（expand-and-contract）

1. 🧪 **Neon development branch** でスキーマ適用（Alembic）+ `scripts/migrate_json_to_db.py`（ワンショット・冪等）で全件投入 → 件数・フィールド一致を自動照合
2. 🔁 **併走期**: 正本は引き続き JSON。週次検証は DB にも書き込み（dual-write）、`export` 生成物を JSON 版と diff 照合し drift ゼロを 2 週連続確認
3. ✅ **切替**: DB を正本宣言（Approval PR）。JSON は export 生成物へ降格（Git 履歴は継続）
4. ⏪ **rollback**: 切替後も export された JSON は常に最新のため、`migrate_json_to_db.py` 再実行のみで DB を再構築可能（双方向の復元性）

### 2.4 テスト戦略

- 🧪 unit: スキーマ制約・リポジトリ層（testcontainers または Neon preview branch）
- 🧪 integration: CRUD → export 再生成 → 既存 `validate_catalog.py` PASS
- 🧪 migration: 現 50 件の実データで投入 → 全フィールド round-trip 一致

---

## 3. 🔑 Epic #45 詳細設計 — Entra ID/OIDC SSO + RBAC

### 3.1 認証フロー

- 🔐 **Authorization Code + PKCE**（confidential client、`authlib` 使用）。実装先は **FastAPI アプリ層**（AD-5。プロキシ案は却下）
- 🍪 セッション: サーバー側セッション（DB `sessions` テーブル）+ `__Host-` prefix・`Secure`・`HttpOnly`・`SameSite=Lax` cookie。トークンはセッションストアのみに保持しブラウザへ出さない
- 🚪 ログアウト: セッション破棄 + Entra ID front-channel logout。トークン失効はセッション TTL（8h）+ refresh 時の再検証で担保

### 3.2 ロールモデル（5 ロール）

| App Role (Entra ID) | 要件定義書 17 章との対応 | 主な許可                                           |
| ------------------- | ------------------------ | -------------------------------------------------- |
| `Catalog.Admin`     | 管理者                   | 全操作・評価基準変更・削除（FR-012）               |
| `Catalog.Editor`    | 編集者                   | 登録・更新・接続ステータス変更・検証・成果物出力   |
| `Catalog.Verifier`  | （#47 検証者）           | 検証実行・レビュー（承認ワークフローのレビュー段） |
| `Catalog.Approver`  | （#47 承認者）           | 承認・公開（承認ワークフローの承認段）             |
| `Catalog.Viewer`    | 閲覧者                   | 読取のみ（未認証と同等 + 内部メモ閲覧）            |

- 🧭 未認証: 読取 API のみ（外部共有用ビュー = 個人情報・API キー・内部メモを除外）
- 🛡️ 実装: FastAPI 依存性注入 `require_role(...)` を書込系エンドポイントに宣言的に付与。ロール判定は ID トークン `roles` クレーム
- 📝 Entra ID アプリ登録手順・必要な redirect URI・App Role 定義は `docs/entra-id-setup.md`（本 epic 内で作成）に記載。**テナント設定変更はユーザー実施**（Approval 対象外の外部管理操作）

### 3.3 セキュリティ要件

- ✅ state/nonce/PKCE 検証、`iss`/`aud`/`exp` 検証、クロックスキュー 5 分
- ✅ secrets（client secret）は環境変数 + Windows 資格情報ストア／CI は GitHub Secrets。コード・ログ非出力（§19）
- ✅ 認証失敗・権限不足は 401/403 を区別し監査ログへ記録（#47 連携）

---

## 4. 📜 Epic #47 詳細設計 — 監査ログ・版管理・承認ワークフロー

### 4.1 スキーマ

```sql
-- append-only 監査ログ（AD-6: アプリ用 DB ロールに UPDATE/DELETE を GRANT しない）
CREATE TABLE audit_log (
  seq         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  at          timestamptz NOT NULL DEFAULT now(),
  actor       text NOT NULL,                  -- OIDC sub / 'system:scheduled-verify'
  actor_roles text[] NOT NULL,
  action      text NOT NULL,                  -- create/update/delete/status_change/review/approve/publish/login/…
  record_id   text,
  diff        jsonb,                          -- 変更前後（before/after）
  reason      text,                           -- 変更理由（書込 API で必須化）
  request_id  uuid
);

-- レコード版管理（更新のたびに旧版を snapshot）
CREATE TABLE catalog_entry_versions (
  record_id  text NOT NULL,
  version    int  NOT NULL,
  snapshot   jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  created_by text NOT NULL,
  PRIMARY KEY (record_id, version)
);

-- 承認ワークフロー状態
CREATE TABLE entry_workflow (
  record_id  text PRIMARY KEY REFERENCES catalog_entries(id),
  state      text NOT NULL CHECK (state IN ('draft','in_review','pending_approval','published','rejected')),
  updated_at timestamptz NOT NULL DEFAULT now()
);
```

### 4.2 状態遷移

```text
draft ──(編集者: 提出)──▶ in_review ──(検証者: OK)──▶ pending_approval ──(承認者: 承認)──▶ published
  ▲                         │(差し戻し)                  │(差し戻し)
  └─────────────────────────┴────────────────────────────┘
```

- 📌 全遷移は `audit_log` に記録（Completion Criteria 対応）。閲覧系 API は `published` のみ返す（編集者以上は下書きも閲覧可）
- 📌 **FR-012 整合（Issue #44 委譲分）**: DELETE は論理削除（`entry_workflow` 外 + `deleted_at` 列 expand）とし、版・監査ログは保持。「利用終了」ステータス変更は update 系として編集者以上 + 監査記録 — 要件定義書 8/11/17 章（PR #52 改訂）を実装仕様へ落とす
- 📌 復元: 管理者のみ。`catalog_entry_versions` の指定版から restore（監査記録付き）

---

## 5. 👥 Epic #48 詳細設計 — 所有者管理 + API 定義ライフサイクル

### 5.1 スキーマ拡張（catalog_entries へ expand）

```sql
ALTER TABLE catalog_entries
  ADD COLUMN owner_contact    jsonb,   -- {name, org, email}（PII 最小限・業務連絡先のみ）
  ADD COLUMN steward_contact  jsonb,
  ADD COLUMN reviewer_contact jsonb,
  ADD COLUMN support_contact  jsonb,
  ADD COLUMN lifecycle_status text NOT NULL DEFAULT 'active'
      CHECK (lifecycle_status IN ('draft','active','deprecated','retired')),
  ADD COLUMN lifecycle_changed_at timestamptz;
```

### 5.2 責務分担（#47 との境界）

- 🧭 **#48 = 「API 定義そのもの」の所有とライフサイクル**（draft→active→deprecated→retired）。`retired` は要件定義書 11 章「利用終了」に対応
- 🧭 **#47 = 「レコード値の変更」の承認プロセス**。ライフサイクル遷移も #47 のワークフロー・監査ログを通す（遷移 = 状態フィールドの update）
- 🚨 責任者未設定・`deprecated` 長期滞留の検出: 週次検証バッチに検査を追加し、#49 の通知機構で警告

---

## 6. 📈 Epic #49 詳細設計 — 品質検証強化 + 履歴 + 通知

### 6.1 履歴蓄積

- 🗄️ `verification_results` を**上書きせず追記**（2.1 のスキーマは最初から時系列対応済み: PK に日付を含む現行 ID 形式を維持しつつ `(api_id, verified_at)` で参照）
- 📤 現行 JSON（最新スナップショット）は export として生成継続 → WebUI 契約を破壊しない

### 6.2 異常検知ルール（初期セット）

| ルール      | 条件                                              | 重大度 |
| ----------- | ------------------------------------------------- | ------ |
| 🔴 接続失敗 | `result=failure` が同一 API で 2 回連続           | High   |
| 🟠 応答劣化 | `response_time_ms` が直近 4 回中央値の 3 倍超     | Medium |
| 🟠 件数急変 | `record_count` が前回比 ±50% 超（両方非 NULL 時） | Medium |
| 🟡 検証欠落 | 7 日超検証されていない active エントリ            | Low    |

### 6.3 通知機構

- 📮 **第 1 段階: GitHub Issue 自動起票**（`scheduled-verify` workflow から `gh issue create`、ラベル `verification-alert`。既に Actions の PR/Issue 作成権限は有効化済み・2026-07-23）
- 📮 第 2 段階: #48 の `support_contact` を通知先として解決（メール/Slack は着手時にユーザー選定）
- 📌 **64KB 切り詰め問題の方針決定**: 検証は「到達性・応答性・形式」の確認であり全量取得は目的でない → **切り詰め前提の検証設計を正**とする。PR #52 で導入済みの `sample_truncated` + note 明示を仕様として確定し、`record_count` は Content-Range / ページネーション metadata から取得可能な API のみ optional 拡張（コネクタ単位）

---

## 7. 🛡️ 横断: セキュリティ・運用・移行ガバナンス

- 🔒 接続文字列・client secret は環境変数 + Secret 管理（§5/§19）。`.env.example` に実値を書かない
- 🧪 すべての migration は Neon development/preview branch で先行検証（§13）。破壊的変更は expand-and-contract に再設計
- 📋 DB 正本切替・Entra ID 連携有効化・通知先設定は **Approval PR**（§17）として分離
- 📊 各 Phase の完了条件は epic Issue の Completion Criteria を正とし、実装 PR は epic の子 Issue に分割して起票する

## 8. 📆 マイルストーン目安（release_deadline 2026-12-18 逆算）

| Phase | 内容                                                | 目安           |
| ----- | --------------------------------------------------- | -------------- |
| A     | #46 スキーマ + 読取 API + 移行スクリプト + 併走開始 | 〜2026-09 上旬 |
| B     | #45 OIDC + RBAC + 書込 API 公開                     | 〜2026-10 上旬 |
| C     | #47 監査・版・承認                                  | 〜2026-11 上旬 |
| D/E   | #48 + #49（並行）                                   | 〜2026-11 末   |
| —     | DB 正本切替 Approval・安定化・文書化                | 〜2026-12-18   |
