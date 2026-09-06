# RBAC ロール × API操作マトリクス

> 📌 本書は Issue #45（epic: 認証基盤 + RBAC 導入）の Completion Criteria
> 「5ロールそれぞれで許可される API 操作がドキュメント化・実装されている」を満たすための文書です。
> 認可ロジック自体（`web/auth.py` の `require_role`、`web/api_v1.py` の各エンドポイント）は
> 実装済みであり、本書はそれを正確に反映するドキュメントです。コードの変更は含みません。
>
> - 🔗 ロール割当方法の詳細: [`docs/entra-id-setup.md`](./entra-id-setup.md)（Entra ID App Roles）
> - 🔗 ローカル認証でのロール割当: `scripts/create_local_user.py`（後述 §5）
> - 🧩 実装根拠: `web/auth.py`（`require_role`, `ROLE_*` 定数）, `web/api_v1.py`（各 `Depends(require_*)` および `_TRANSITIONS`）

---

## 1. 📋 ロール一覧

| ロール定数         | 表示名               | 役割の説明                                                                                        |
| ------------------ | -------------------- | ------------------------------------------------------------------------------------------------- |
| `Catalog.Admin`    | 🛡️ 管理者 (Admin)    | 全操作を実行可能。削除・復元・Webhook管理・全ワークフロー遷移を含む唯一のロール                   |
| `Catalog.Editor`   | ✏️ 編集者 (Editor)   | エントリの登録・更新・try-it 実行・ワークフローの `submit`（提出）/`reopen`（再オープン）を担当   |
| `Catalog.Verifier` | 🔍 検証者 (Verifier) | ワークフローの `review_ok`（レビュー合格）/`send_back`（差し戻し）を担当（epic #47 レビュー段）   |
| `Catalog.Approver` | ✅ 承認者 (Approver) | ワークフローの `approve`（公開承認）/`send_back`（差し戻し）を担当（epic #47 承認段）             |
| `Catalog.Viewer`   | 👁️ 閲覧者 (Viewer)   | ログイン済みの閲覧専用ユーザー。API v1 の書込・スタッフ限定エンドポイントへのアクセス権は持たない |

> ⚠️ **既知の注意点(実装ベースの事実)**: `docs/entra-id-setup.md` の App Roles 一覧では
> `Catalog.Viewer` を「閲覧者（内部メモ含む読取）」と説明していますが、`web/api_v1.py` の
> 現在の実装では `ROLE_VIEWER` は一切参照されておらず（`_STAFF_ROLES` にも不含）、
> Viewer ロールを持つログイン済みセッションは **未認証ユーザーと同一の読み取り権限**
> （`published` 状態のエントリのみ閲覧可能）です。ドラフトや内部メモ相当のフィールドを
> Viewer ロールだからといって追加で閲覧できる実装は現時点では存在しません。将来的に
> フィールド単位のマスキングを実装する場合は、本書と `docs/entra-id-setup.md` を合わせて
> 更新してください。

---

## 2. 🔓 未認証ユーザー(anonymous)の扱い

- ✅ 未認証ユーザーは **閲覧(GET)のみ** 可能です。
- ✅ `status=published` のエントリのみが見え、`draft` / `in_review` / `pending_approval` / `rejected`
  状態のエントリは 404 として扱われ、存在自体が秘匿されます(`web/api_v1.py` `_staff_session()` / `_workflow_state()`)。
- 🚫 書込系(POST/PATCH/DELETE)は全て 401（未認証）で拒否されます(`test_write_requires_authentication`,
  `test_try_it_requires_authentication` で検証済み)。
- 🚫 `/api/v1/tasks`, `/api/v1/audit`, `/api/v1/audit/export.csv`, `/api/v1/entries/{id}/versions*`,
  `/api/v1/webhooks*` はスタッフ限定(`require_staff` または `require_admin`)であり未認証・Viewer では 401/403。

---

## 3. 🧭 API操作 × ロール マトリクス

凡例: ✅=許可 / ➖=対象外(該当ロールでは意味を持たない) / 🚫=拒否(401 or 403)
「Staff」列は `require_staff`（Editor・Verifier・Approver・Admin のいずれか）の意味です。

### 3.1 読み取り系（`web/api_v1.py` 冒頭 `# --- read (public) ---`）

| エンドポイント              | 概要           | 未認証                          | Viewer             | Editor            | Verifier          | Approver          | Admin             |
| --------------------------- | -------------- | ------------------------------- | ------------------ | ----------------- | ----------------- | ----------------- | ----------------- |
| `GET /api/v1/entries`       | 一覧取得       | ✅(published のみ)              | ✅(published のみ) | ✅(draft含む全件) | ✅(draft含む全件) | ✅(draft含む全件) | ✅(draft含む全件) |
| `GET /api/v1/entries/{id}`  | 単体取得       | ✅(published のみ、それ以外404) | ✅(published のみ) | ✅(全状態)        | ✅(全状態)        | ✅(全状態)        | ✅(全状態)        |
| `GET /api/v1/verifications` | 検証結果一覧   | ✅                              | ✅                 | ✅                | ✅                | ✅                | ✅                |
| `GET /api/v1/metadata`      | 件数等メタ情報 | ✅                              | ✅                 | ✅                | ✅                | ✅                | ✅                |
| `GET /api/v1/health`        | ヘルスチェック | ✅                              | ✅                 | ✅                | ✅                | ✅                | ✅                |

> 📎 根拠: `_staff_session()` は `_STAFF_ROLES = {Editor, Verifier, Approver, Admin}` のみを
> スタッフ判定に用いる（`web/api_v1.py:174-182`）。Viewer は未認証と同じ分岐に入る。

### 3.2 書込系（要ログイン、`require_editor` = Editor or Admin）

| エンドポイント                | 概要                                     | 未認証 | Viewer | Editor | Verifier | Approver | Admin |
| ----------------------------- | ---------------------------------------- | ------ | ------ | ------ | -------- | -------- | ----- |
| `POST /api/v1/try-it`         | 安全な疎通確認実行                       | 🚫401  | 🚫403  | ✅     | 🚫403    | 🚫403    | ✅    |
| `POST /api/v1/entries`        | エントリ新規登録(draftとして作成)        | 🚫401  | 🚫403  | ✅     | 🚫403    | 🚫403    | ✅    |
| `POST /api/v1/import/openapi` | OpenAPI仕様からの一括インポート(draft)   | 🚫401  | 🚫403  | ✅     | 🚫403    | 🚫403    | ✅    |
| `PATCH /api/v1/entries/{id}`  | エントリ部分更新(draft/rejected状態のみ) | 🚫401  | 🚫403  | ✅     | 🚫403    | 🚫403    | ✅    |

### 3.3 削除・復元系（Admin専用）

| エンドポイント                      | 概要                                   | 未認証 | Viewer | Editor | Verifier | Approver | Admin |
| ----------------------------------- | -------------------------------------- | ------ | ------ | ------ | -------- | -------- | ----- |
| `DELETE /api/v1/entries/{id}`       | 論理削除(FR-012)                       | 🚫401  | 🚫403  | 🚫403  | 🚫403    | 🚫403    | ✅    |
| `POST /api/v1/entries/{id}/restore` | バージョン復元(draft/rejected状態のみ) | 🚫401  | 🚫403  | 🚫403  | 🚫403    | 🚫403    | ✅    |

### 3.4 ワークフロー遷移（`POST /api/v1/entries/{id}/transitions`）

基底の依存性は `require_staff`（Editor/Verifier/Approver/Admin のいずれかでログインが必要、
Viewer・未認証は 401/403）。さらに `action` ごとに `_TRANSITIONS` テーブル
（`web/api_v1.py:755-779`）で許可ロールが絞り込まれ、不一致は 403「role cannot perform '{action}'」。

| action      | 遷移                               | 未認証 | Viewer | Editor | Verifier | Approver | Admin |
| ----------- | ---------------------------------- | ------ | ------ | ------ | -------- | -------- | ----- |
| `submit`    | draft/rejected → in_review         | 🚫401  | 🚫401  | ✅     | 🚫403    | 🚫403    | ✅    |
| `review_ok` | in_review → pending_approval       | 🚫401  | 🚫401  | 🚫403  | ✅       | 🚫403    | ✅    |
| `approve`   | pending_approval → published       | 🚫401  | 🚫401  | 🚫403  | 🚫403    | ✅       | ✅    |
| `send_back` | in_review/pending_approval → draft | 🚫401  | 🚫401  | 🚫403  | ✅       | ✅       | ✅    |
| `reopen`    | published → draft                  | 🚫401  | 🚫401  | ✅     | 🚫403    | 🚫403    | ✅    |

> ℹ️ Viewer は `require_staff` の時点（役割共通チェック）で 401 になる点に注意
> （未認証も同じく `require_role` の最初の分岐で 401）。一方 Editor が `approve` を試みる等
> スタッフではあるがアクション別ロールに合致しない場合は、`require_staff` は通過するが
> `_TRANSITIONS["approve"]["roles"]` チェックで 403 になります(実装上の 401/403 の使い分けに関する
> 参考: `web/auth.py` `require_role()` のコメント「401 when unauthenticated, 403 when the session
> lacks every allowed role」)。

### 3.5 バージョン・監査・タスク（`require_staff`）

| エンドポイント                          | 概要                           | 未認証 | Viewer | Editor           | Verifier         | Approver         | Admin    |
| --------------------------------------- | ------------------------------ | ------ | ------ | ---------------- | ---------------- | ---------------- | -------- |
| `GET /api/v1/entries/{id}/versions`     | バージョン一覧                 | 🚫401  | 🚫401  | ✅               | ✅               | ✅               | ✅       |
| `GET /api/v1/entries/{id}/versions/{v}` | バージョン詳細                 | 🚫401  | 🚫401  | ✅               | ✅               | ✅               | ✅       |
| `GET /api/v1/audit`                     | 監査ログ一覧                   | 🚫401  | 🚫401  | ✅               | ✅               | ✅               | ✅       |
| `GET /api/v1/audit/export.csv`          | 監査ログCSVエクスポート        | 🚫401  | 🚫401  | ✅               | ✅               | ✅               | ✅       |
| `GET /api/v1/tasks`                     | ロール別タスクキュー(下表参照) | 🚫401  | 🚫401  | ✅(自分向けのみ) | ✅(自分向けのみ) | ✅(自分向けのみ) | ✅(全件) |

`GET /api/v1/tasks` はロールに応じて見えるタスク種別が変わります(`_task_groups_for_roles()`,
`web/api_v1.py:968-977`)。

| ロール   | 見えるタスク種別               | 対応するワークフロー状態                      |
| -------- | ------------------------------ | --------------------------------------------- |
| Editor   | fix（差し戻された修正待ち）    | `rejected`                                    |
| Verifier | review（レビュー待ち）         | `in_review`                                   |
| Approver | approval（承認待ち）           | `pending_approval`                            |
| Admin    | fix + review + approval の全て | `rejected` + `in_review` + `pending_approval` |

### 3.6 Webhook購読管理（Admin専用、`require_admin`）

| エンドポイント                    | 概要                               | 未認証 | Viewer | Editor | Verifier | Approver | Admin |
| --------------------------------- | ---------------------------------- | ------ | ------ | ------ | -------- | -------- | ----- |
| `GET /api/v1/webhooks`            | 購読一覧                           | 🚫401  | 🚫403  | 🚫403  | 🚫403    | 🚫403    | ✅    |
| `POST /api/v1/webhooks`           | 購読作成                           | 🚫401  | 🚫403  | 🚫403  | 🚫403    | 🚫403    | ✅    |
| `PATCH /api/v1/webhooks/{id}`     | 購読更新(secretローテーション含む) | 🚫401  | 🚫403  | 🚫403  | 🚫403    | 🚫403    | ✅    |
| `DELETE /api/v1/webhooks/{id}`    | 購読削除                           | 🚫401  | 🚫403  | 🚫403  | 🚫403    | 🚫403    | ✅    |
| `POST /api/v1/webhooks/{id}/test` | テスト配信                         | 🚫401  | 🚫403  | 🚫403  | 🚫403    | 🚫403    | ✅    |

### 3.7 認証エンドポイント（`web/auth.py`, プレフィックス `/auth`）

これらはロールベースの `require_role` ではなく、認証セッションの有無だけで判定されます。

| エンドポイント       | 概要                                                                        | 未認証                       | ログイン済み(任意ロール)       |
| -------------------- | --------------------------------------------------------------------------- | ---------------------------- | ------------------------------ |
| `POST /auth/login`   | ローカルID/PWログイン試行(`CATALOG_AUTH_MODE=local`時のみ有効、それ以外404) | ✅(ログイン試行として利用)   | ✅(再ログイン可)               |
| `GET /auth/login`    | Entra IDログイン開始 or ログインダイアログへリダイレクト                    | ✅                           | ✅                             |
| `GET /auth/callback` | Entra ID OIDCコールバック                                                   | ✅(ログインフロー完了に必要) | ➖(通常未認証状態から呼ばれる) |
| `GET /auth/logout`   | ログアウト(セッション破棄)                                                  | ✅(no-op)                    | ✅                             |
| `GET /auth/me`       | 自分のセッション情報(`sub`/`name`/`roles`)取得                              | 🚫401                        | ✅                             |

---

## 4. 🧪 検証根拠

上記マトリクスは以下の実コード・既存テストと突き合わせて作成しています。

- `web/auth.py`: `ROLE_ADMIN` / `ROLE_EDITOR` / `ROLE_VERIFIER` / `ROLE_APPROVER` / `ROLE_VIEWER` /
  `ALL_ROLES` の定義、および `require_role(get_db, *allowed)` の 401/403 分岐。
- `web/api_v1.py`:
  - `require_editor = require_role(get_session, ROLE_EDITOR, ROLE_ADMIN)`
  - `require_admin = require_role(get_session, ROLE_ADMIN)`
  - `require_staff = require_role(get_session, ROLE_EDITOR, ROLE_VERIFIER, ROLE_APPROVER, ROLE_ADMIN)`
  - `_STAFF_ROLES` / `_staff_session()`（読み取り時のdraft可視性判定）
  - `_TRANSITIONS`（ワークフロー遷移ごとの許可ロール）
  - `_task_groups_for_roles()`（タスクキューのロール別フィルタ）
  - 各エンドポイントの `Depends(require_editor|require_admin|require_staff)`
- `tests/test_auth_rbac.py`: `test_viewer_cannot_write`, `test_write_requires_authentication`,
  `test_try_it_requires_authentication`, `test_editor_create_update_and_admin_delete_lifecycle`,
  `test_me_reports_roles` 等で上記の一部が既にテストされている。

---

## 5. 🔑 ロールの割当方法

### 5.1 Entra ID OIDC モード（`CATALOG_AUTH_MODE=oidc`）

Entra ID テナント側で 5 つの App Role（`Catalog.Admin` / `Catalog.Editor` / `Catalog.Verifier` /
`Catalog.Approver` / `Catalog.Viewer`）を作成し、Enterprise applications の
"Users and groups" でユーザーへ割当てます。ID トークンの `roles` クレームがそのまま
セッションのロールとして扱われます（複数ロールの同時付与が可能）。
詳細な作成手順・値の対応表は [`docs/entra-id-setup.md`](./entra-id-setup.md) §3 を参照してください。

### 5.2 ローカルID/PW モード（`CATALOG_AUTH_MODE=local`、既定）

`scripts/create_local_user.py --username <name> --role <ROLE>` で作成・更新します。
ローカルモードでは 1 ユーザーにつき **単一ロールのみ**（`LocalUser.role`、DBカラムは単一値）
が割当てられ、セッションの `roles` は `[user.role]` という1要素のリストになります
（Entra IDモードのような複数ロール同時付与はできません）。
ロール変更後は `revoke_user_sessions()` で既存セッションを失効させる運用です
（`scripts/create_local_user.py` 内で実行）。

---

## 6. 📝 変更履歴

- 2026-09-06: 初版作成（Issue #45 Completion Criteria対応、実装への変更なし）
