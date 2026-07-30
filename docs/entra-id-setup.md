# 🔑 Entra ID (Azure AD) セットアップ手順 — Phase B (epic #45)

> 🔄 **2026-07-30 更新**: 現行の本番認証は**ローカルユーザー/パスワード方式**（`CATALOG_AUTH_MODE=local`・`scripts/create_local_user.py` でアカウント管理）に切替済み。本書の Entra ID OIDC は `CATALOG_AUTH_MODE=oidc` を明示した場合のみ使うオプション構成として保全する。

> 📌 設計正本: `docs/epic-detailed-design-q4.md` §3 ／ タスク: Issue #59 B-0/B-6
> ⚠️ **client secret・接続文字列はこのリポジトリへ書かない**（`.gitignore` 済みのローカルメモまたは Secret 管理のみ）。

## 1. アプリ登録（Azure Portal → Microsoft Entra ID → App registrations）

| 設定                           | 値                                                                                                       |
| ------------------------------ | -------------------------------------------------------------------------------------------------------- |
| 名前                           | `Global-Civil-API-Catalog`                                                                               |
| サポートされるアカウントの種類 | この組織ディレクトリのみ（単一テナント）                                                                 |
| Redirect URI (Web)             | `http://localhost:49232/auth/callback`（開発）。本番公開時は `https://<本番ホスト>/auth/callback` を追加 |

## 2. クライアントシークレット

Certificates & secrets → New client secret。値は発行直後にのみ表示される。**環境変数へ保存**し、ポータル外へ平文で残さない。有効期限切れ前のローテーションを運用カレンダーへ登録すること。

## 3. App Roles（5 件・値は完全一致で作成）

| 表示名           | 値                 | 対応（要件定義書 17 章）             |
| ---------------- | ------------------ | ------------------------------------ |
| Catalog Admin    | `Catalog.Admin`    | 管理者（全操作・削除）               |
| Catalog Editor   | `Catalog.Editor`   | 編集者（登録・更新・ステータス変更） |
| Catalog Verifier | `Catalog.Verifier` | 検証者（epic #47 レビュー段）        |
| Catalog Approver | `Catalog.Approver` | 承認者（epic #47 承認段）            |
| Catalog Viewer   | `Catalog.Viewer`   | 閲覧者（内部メモ含む読取）           |

いずれも「Allowed member types: Users/Groups」。作成後、Enterprise applications → Users and groups で利用者へロールを割当てる（最低 1 名に `Catalog.Admin`）。

## 4. アプリケーション側の環境変数

| 変数                   | 内容                                                                                       |
| ---------------------- | ------------------------------------------------------------------------------------------ |
| `ENTRA_TENANT_ID`      | Directory (tenant) ID                                                                      |
| `ENTRA_CLIENT_ID`      | Application (client) ID                                                                    |
| `ENTRA_CLIENT_SECRET`  | 手順 2 のシークレット値                                                                    |
| `CATALOG_BASE_URL`     | 公開ベース URL（既定 `http://localhost:49232`。https のとき Secure cookie が有効化される） |
| `CATALOG_DATABASE_URL` | Neon 接続文字列（`postgresql+psycopg://` 形式）                                            |

## 5. 動作確認

```bash
uvicorn web.api_v1:app --port 49232
# ブラウザで http://localhost:49232/auth/login → Entra ID ログイン → / へ戻る
# http://localhost:49232/auth/me で {sub, name, roles} を確認
# http://localhost:49232/auth/logout でサインアウト
```

## 6. 実装済みのセキュリティ特性（design §3.3）

- ✅ Authorization Code + **PKCE (S256)** ／ state・nonce はサーバー側 DB 保管・single-use・TTL 10 分
- ✅ ID トークン検証: 署名 (JWKS)・`iss`・`aud`・`exp`（クロックスキュー 300 秒）・`nonce`
- ✅ サーバー側セッション（TTL 8h・opaque ID のみを HttpOnly / SameSite=Lax cookie で保持。トークンはブラウザへ渡らない）
- ✅ 401（未認証）と 403（権限不足）を区別
- 📌 既知の逸脱: `__Host-` プレフィックスは HTTPS 必須のため、http://localhost 開発では通常名 cookie + Secure off。本番 https 切替時に再確認する
