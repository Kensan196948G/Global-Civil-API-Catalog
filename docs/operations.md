# 運用メモ

## Web UI

- URL: `https://api.mirai-dx-platform.com`（本番・Cloudflare Tunnel + Access 経由）/ `http://192.168.0.185:49231`（LAN 直接）
- 固定ポート: `49231`（Web UI）・`49232`（api_v1 / `127.0.0.1` 限定・プロキシ経由でのみ到達）
- ポート定義: `deploy/PORT.lock`
- 稼働方式: **Linux ネイティブ Python + systemd ユーザーサービス（本番）**。Docker は開発・検証用の代替（コンテナ名 `global-civil-api-catalog-web` / イメージ `global-civil-api-catalog-web:local`）
- 📅 2026-07-30: 本番 origin を Windows から Linux へ切替え。旧 Windows 環境は撤去済み（後述の撤去記録参照）

このサービスでは登録済みポート `49231` を基本とします。ホストIPがDHCP等で変わる場合でも、ポート番号は維持します。
本番 unit は `--auto-port` を使わず固定ポートで起動します（Tunnel ingress が `localhost:49231` を指すため、ポートが取れない場合はドリフトさせずに fail させる設計）。

### 🔗 編集・承認UI（RBAC統合 / Issue #64）

Web UI の「登録・承認管理」画面（ログイン・エントリCRUD・ワークフロー承認・監査ログ）は、静的サーバー（`web/server.py`）が `/api/v1/*` と `/auth/*` を FastAPI プロセス（`web/api_v1.py`）へ**リバースプロキシ**して実現します。ブラウザは常に単一オリジンで完結するため、CSP `connect-src 'self'`・SameSite Cookie・Origin検査（CSRF対策）はそのまま成立します。

- プロキシ先の既定値: `http://127.0.0.1:49232`（環境変数 `CATALOG_API_UPSTREAM` で変更可）
- API v1 起動: `uvicorn web.api_v1:app --host 127.0.0.1 --port 49232`（`CATALOG_DATABASE_URL` 必須）
- **api_v1 未起動時の挙動**: 閲覧UIは従来どおり動作し、編集操作のみ `503`（「編集サービスに接続できません」）となる — graceful degradation
- 外部公開時は `CATALOG_BASE_URL` を公開オリジン（例: `https://api.mirai-dx-platform.com`）へ一致させること（Origin検査・Secure Cookie 判定に使用）
- 認証モード: 既定は**ローカルユーザー/パスワード認証**（`CATALOG_AUTH_MODE=local`）。アカウント作成・パスワード再設定・ロック解除は `CATALOG_DATABASE_URL` を読み込んだ上で `python scripts/create_local_user.py --username <名前> --role Catalog.Admin`（パスワードは対話入力・12文字以上・ログイン5回失敗で15分ロック）。Entra ID OIDC は `CATALOG_AUTH_MODE=oidc` + `ENTRA_*` 設定時のみ有効（`docs/entra-id-setup.md`）

---

## 🐧 Linux（本番 origin）

### 構成（systemd ユーザーサービス3本）

| unit                                   | 役割                                                                 |
| -------------------------------------- | -------------------------------------------------------------------- |
| `global-civil-api-catalog-web.service` | Web UI（`:49231`、`--port-lock-file deploy/PORT.lock`）              |
| `global-civil-api-catalog-api.service` | 編集用 api_v1（uvicorn、`127.0.0.1:49232`、要 `api.env`）            |
| `gc-api-catalog-cloudflared.service`   | Cloudflare Tunnel コネクタ（`api.mirai-dx-platform.com` の外部公開） |

### 初回セットアップ

```bash
# 1) api_v1 の環境変数（deploy/api.env.example を基に作成。実値は Git 管理しない）
mkdir -p ~/.config/global-civil-api-catalog
cp deploy/api.env.example ~/.config/global-civil-api-catalog/api.env
chmod 600 ~/.config/global-civil-api-catalog/api.env
# api.env を編集して実値を設定（CATALOG_BASE_URL は「UI のオリジン」にする）

# 2) 依存導入（api_v1 のみ必要。Web UI は stdlib のみで動作）
pip install -e ".[db]"

# 3) DB スキーマ適用と初回ユーザー作成（api.env の値を読み込んだ上で一度だけ）
python -m alembic upgrade head
python scripts/create_local_user.py --username admin --role Catalog.Admin
#   → パスワードは対話入力（12文字以上）。追加ユーザーも同コマンドで作成できる

# 4) Cloudflare Tunnel コネクタ（cert.pem = `cloudflared tunnel login` 済みが前提）
#    credentials は cert.pem からいつでも再生成できる（値は表示しないこと）:
cloudflared tunnel token --cred-file ~/.cloudflared/370aef2d-fb96-4ec8-89c4-c7a16bd3e147.json gc-api-catalog
#    config を ~/.cloudflared/gc-api-catalog-config.yml に作成
#    （tunnel ID・credentials-file・ingress: api.mirai-dx-platform.com → http://localhost:49231、その他 404。
#      雛形: deploy/cloudflare/config.yml.example）
cloudflared tunnel --config ~/.cloudflared/gc-api-catalog-config.yml ingress validate

# 5) unit 配置と有効化
mkdir -p ~/.config/systemd/user
cp deploy/global-civil-api-catalog-web.service ~/.config/systemd/user/
cp deploy/global-civil-api-catalog-api.service ~/.config/systemd/user/
cp deploy/gc-api-catalog-cloudflared.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now global-civil-api-catalog-web.service
systemctl --user enable --now global-civil-api-catalog-api.service
systemctl --user enable --now gc-api-catalog-cloudflared.service
```

### 状態確認

```bash
systemctl --user status global-civil-api-catalog-web.service global-civil-api-catalog-api.service gc-api-catalog-cloudflared.service
curl http://127.0.0.1:49231/api/health
curl http://127.0.0.1:49231/api/v1/metadata   # プロキシ経由で api_v1 まで疎通確認
cloudflared tunnel info 370aef2d-fb96-4ec8-89c4-c7a16bd3e147   # コネクタ接続状況
```

### 再起動

```bash
systemctl --user restart global-civil-api-catalog-web.service global-civil-api-catalog-api.service
systemctl --user restart gc-api-catalog-cloudflared.service   # トンネルは通常触らなくてよい
```

### 常駐条件

`loginctl show-user "$USER" -p Linger` が `Linger=yes` のため、ログアウト後もユーザーsystemdサービスは継続します。サービスは `Restart=always` で登録済みです。

---

## 🚀 リリース反映手順（本番 origin = Linux）

GitHub 上で main へマージし tag を作成した後、本番 origin（この Linux 機）で以下を実施して反映する。
開発機と本番 origin が同一のため、**承認済み PR の範囲で Claude Code（CTO代行）が自律実行できる**。

```bash
cd ~/Projects/Mirai-DX-Project/Global-Civil-API-Catalog
git fetch --tags origin
git checkout main
git pull --ff-only origin main
# state.json 等のローカル変更が pull を塞ぐ場合は、先に退避する:
#   git stash push -m "pre-release local state" -- state.json

# 該当リリースに migration がある場合のみ、再起動前に適用する
# 例: CATALOG_DATABASE_URL を読み込んだ上で python -m alembic upgrade head

# サービス再起動（web/api のみ。トンネルは対象外）
systemctl --user restart global-civil-api-catalog-web.service global-civil-api-catalog-api.service

# smoke
curl http://127.0.0.1:49231/api/health
curl http://127.0.0.1:49231/api/v1/metadata
# ブラウザ: https://api.mirai-dx-platform.com → Access ログイン → UI 表示・編集導線を確認
```

### ⏪ rollback（事前検証済み・非破壊）

```bash
git checkout <直前の tag または commit SHA>
systemctl --user restart global-civil-api-catalog-web.service global-civil-api-catalog-api.service
```

- 📌 DB: migration を含まないリリースは DB rollback 不要。migration を含むリリースは各 PR 記載の downgrade 手順（例: `alembic downgrade -1`）に従う
- ✅ 反映後は Cloudflare Access 経由（`https://api.mirai-dx-platform.com`）で 302 → ログイン → UI 表示、および編集 UI の疎通を確認する

---

## ☁️ Cloudflare Tunnel（api.mirai-dx-platform.com 公開）

Named Tunnel + **Cloudflare Access（認証ゲート必須）** で Web UI をサブドメイン公開します。

- トンネル: `gc-api-catalog`（ID: `370aef2d-fb96-4ec8-89c4-c7a16bd3e147`）
- コネクタ: Linux の user unit `gc-api-catalog-cloudflared.service`（テンプレート: `deploy/gc-api-catalog-cloudflared.service`）
- config: `~/.cloudflared/gc-api-catalog-config.yml`（ingress: `api.mirai-dx-platform.com` → `http://localhost:49231`、その他は 404）
- credentials: `~/.cloudflared/<TUNNEL_ID>.json`（`cloudflared tunnel token --cred-file` で cert.pem から再生成可。**値の表示・Git 管理は禁止**）

### 状態確認

```bash
systemctl --user status gc-api-catalog-cloudflared.service
cloudflared tunnel info 370aef2d-fb96-4ec8-89c4-c7a16bd3e147
journalctl --user -u gc-api-catalog-cloudflared -n 20 --no-pager
```

### ⚠️ セキュリティ必須事項

- 静的 Web UI（`web/server.py`）は**ログイン認証を持たない**ため、公開前に Cloudflare Zero Trust ダッシュボードで **Access アプリケーション + ポリシー（許可メールアドレス等）** を必ず設定する
- Access 未設定のままの公開は禁止（Security First）
- API v1 レイヤ（`web/api_v1.py`）は**ログイン認証（既定: ローカルユーザー/パスワード、オプションで Entra ID OIDC）+ 5 ロール RBAC を実装済み**で、書込系（登録・更新・論理削除）は認証必須。公開時も Access による外側防御は併用する（多層防御）

### ✅ Access 設定状況（2026-07-05 適用済み）

| 項目               | 値                                                                                                                                                                                                    |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Access Application | `Global Civil API Catalog`（`api.mirai-dx-platform.com` 全体を保護）                                                                                                                                  |
| 許可ポリシー       | ドメイン `@mirai-const.co.jp` 全体 + 個別許可メールアドレス（いずれか一致・One-Time PIN 認証）。個別アドレスは Cloudflare Access ダッシュボード側でのみ管理し、本文書には記載しない（PII/標的型対策） |
| 動作確認           | 未認証アクセスは Cloudflare Access ログインページへ 302 リダイレクトされることを確認済み                                                                                                              |
| 変更方法           | Cloudflare Zero Trust ダッシュボード → Access → Applications → `Global Civil API Catalog` からポリシー編集可能                                                                                        |

---

## 🪦 旧 Windows 環境（2026-07-30 撤去済み / 記録）

- 旧構成: Task Scheduler（`GlobalCivilApiCatalog-Web` / `GlobalCivilApiCatalog-Tunnel`、`-Principal S4U`）+ ネイティブ Python + cloudflared。2026-07-30 にタスク解除・プロセス停止・クローン（`D:\Mirai-Projects\Global-Civil-API-Catalog`）削除まで完了し、本番は Linux へ一本化
- 🔍 撤去時の知見: タスクを Unregister しても**起動済みプロセスは残る**。停止漏れの定番は **`pythonw.exe`**（`python.exe` 名指しの `Stop-Process` では捕捉できない）。`Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*<リポジトリ名>*" }` で全変種を列挙してから停止する。フォルダ削除が「使用中」で失敗する場合の犯人もこれ
- Windows 用スクリプト（`deploy/register-windows-service.ps1` / `register-cloudflared.ps1` / `start.ps1` / `start.bat` / `make.ps1`）と Docker 構成（`Dockerfile` / `docker-compose.yml`）は、開発・検証用の代替および将来の再展開の土台として残置

---

## 🗄️ DB レイヤ（Phase A / epic #46 — dual-run 期間中）

> 📌 正本は引き続き `data/*.json`。DB は expand-and-contract 移行の併走側であり、正本切替は別途 Approval PR で行う（設計正本: `docs/epic-detailed-design-q4.md`）。

- 🐘 DB: Neon PostgreSQL + PostGIS（project: `global-civil-api-catalog` / `billowing-cloud-38872160`、dev 用。接続文字列は Secret 管理 — リポジトリ・ログへ書かない）
- 📦 依存導入: `pip install -e ".[db]"`（既定の静的サイト・バッチは従来どおり stdlib のみで動作）
- 🧬 スキーマ適用: `CATALOG_DATABASE_URL=... python -m alembic upgrade head`（rollback は `alembic downgrade base`）
- 🔁 データ投入 + 照合: `CATALOG_DATABASE_URL=... python scripts/migrate_json_to_db.py`（冪等 upsert + field-by-field round-trip 検証。`--verify-only` で照合のみ）
- 🌐 API v1 起動: `CATALOG_DATABASE_URL=... ENTRA_TENANT_ID=... ENTRA_CLIENT_ID=... ENTRA_CLIENT_SECRET=... uvicorn web.api_v1:app --port 49232`（読取は公開、**書込系（登録・更新・論理削除）は Phase B で実装済み・OIDC+RBAC 認証必須**。URL フィールドは SSRF ガードで検証される。設定手順: `docs/entra-id-setup.md`）
- 🧪 DB テスト: `CATALOG_DATABASE_URL=... python -m pytest tests/test_db_phase_a.py`（env 未設定時は自動 skip — CI は現状 DB secret を持たないため skip される）

### 📜 Phase C: 監査ログ・版管理・承認ワークフロー（epic #47）

- 🔁 承認フロー: API 新規登録は `draft` で開始し、`submit`(編集者) → `review_ok`(検証者) → `approve`(承認者) で `published`。差戻しは `send_back`。**公開読取は published のみ**（既存 50 件は移行時に published へ backfill 済み）
- 📜 全変更・遷移・ログイン事象は `audit_log` へ append-only 記録（**変更理由 reason 必須**）。参照: `GET /api/v1/audit`（staff のみ）
- 🕐 版管理: 変更ごとに snapshot 保存。`GET /api/v1/entries/{id}/versions`、復元は `POST /api/v1/entries/{id}/restore`（Admin のみ・論理削除からの復活も可能・監査記録付き）
- ⚠️ AD-6 の DB ロールによる append-only 強制（専用 `catalog_app` ロール + UPDATE/DELETE 剥奪）は **DB 正本切替の Approval PR に含めて適用**する（Issue #47 参照）
