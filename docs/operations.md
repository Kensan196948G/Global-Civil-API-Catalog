# 運用メモ

## Web UI

- URL: `http://192.168.0.185:49231`（LAN）/ `https://api.mirai-dx-platform.com`（Cloudflare Tunnel + Access 経由）
- 固定ポート: `49231`（Web UI）・`49232`（api_v1 / `127.0.0.1` 限定・プロキシ経由でのみ到達）
- ポート定義: `deploy/PORT.lock`
- 稼働方式: ネイティブ Python（Windows: Task Scheduler / Linux: systemd ユーザーサービス）。Docker は開発・検証用の代替（コンテナ名 `global-civil-api-catalog-web` / イメージ `global-civil-api-catalog-web:local`）

このサービスでは登録済みポート `49231` を基本とします。ホストIPがDHCP等で変わる場合でも、ポート番号は維持します。
Windows ネイティブ起動（`--auto-port`）では、`49231` が他プロセスに占有されている場合のみ空きポートへ自動フォールバックし、実際のポートを `deploy/PORT.lock` に記録します。現在のポートは `.\deploy\register-windows-service.ps1 -Status` で確認できます。

### 🔗 編集・承認UI（RBAC統合 / Issue #64）

Web UI の「登録・承認管理」画面（ログイン・エントリCRUD・ワークフロー承認・監査ログ）は、静的サーバー（`web/server.py`）が `/api/v1/*` と `/auth/*` を FastAPI プロセス（`web/api_v1.py`）へ**リバースプロキシ**して実現します。ブラウザは常に単一オリジンで完結するため、CSP `connect-src 'self'`・SameSite Cookie・Origin検査（CSRF対策）はそのまま成立します。

- プロキシ先の既定値: `http://127.0.0.1:49232`（環境変数 `CATALOG_API_UPSTREAM` で変更可）
- API v1 起動: `uvicorn web.api_v1:app --host 127.0.0.1 --port 49232`（`CATALOG_DATABASE_URL` 必須）
- **api_v1 未起動時の挙動**: 閲覧UIは従来どおり動作し、編集操作のみ `503`（「編集サービスに接続できません」）となる — graceful degradation
- 外部公開時は `CATALOG_BASE_URL` を公開オリジン（例: `https://api.mirai-dx-platform.com`）へ一致させること（Origin検査・Secure Cookie 判定に使用）

---

## Linux（検証 origin / 参考）

> ⚠️ 本番は Windows 完結（Task Scheduler 自動起動）へ移行済み。Linux はリリース前検証・待機系として維持する（ネイティブ Python / Docker 不使用）。

### 構成（systemd ユーザーサービス2本）

| unit                                   | 役割                                                      |
| -------------------------------------- | --------------------------------------------------------- |
| `global-civil-api-catalog-web.service` | Web UI（`:49231`、`--port-lock-file deploy/PORT.lock`）   |
| `global-civil-api-catalog-api.service` | 編集用 api_v1（uvicorn、`127.0.0.1:49232`、要 `api.env`） |

### 初回セットアップ

```bash
# 1) api_v1 の環境変数（deploy/api.env.example を基に作成。実値は Git 管理しない）
mkdir -p ~/.config/global-civil-api-catalog
cp deploy/api.env.example ~/.config/global-civil-api-catalog/api.env
chmod 600 ~/.config/global-civil-api-catalog/api.env
# api.env を編集して実値を設定（CATALOG_BASE_URL は「UI のオリジン」にする）

# 2) 依存導入（api_v1 のみ必要。Web UI は stdlib のみで動作）
pip install -e ".[db]"

# 3) unit 配置と有効化
mkdir -p ~/.config/systemd/user
cp deploy/global-civil-api-catalog-web.service ~/.config/systemd/user/
cp deploy/global-civil-api-catalog-api.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now global-civil-api-catalog-web.service
systemctl --user enable --now global-civil-api-catalog-api.service
```

### 状態確認

```bash
systemctl --user status global-civil-api-catalog-web.service global-civil-api-catalog-api.service
curl http://127.0.0.1:49231/api/health
curl http://127.0.0.1:49231/api/v1/metadata   # プロキシ経由で api_v1 まで疎通確認
```

### 再起動

```bash
systemctl --user restart global-civil-api-catalog-web.service global-civil-api-catalog-api.service
```

### 常駐条件

`loginctl show-user "$USER" -p Linger` が `Linger=yes` のため、ログアウト後もユーザーsystemdサービスは継続します。サービスは `Restart=always` で登録済みです。

---

## Windows 11（移設先）

### 前提条件

| 必須           | バージョン目安               |
| -------------- | ---------------------------- |
| Docker Desktop | 4.30+ (WSL2 バックエンド)    |
| Python         | 3.12+                        |
| PowerShell     | 7.4+（Windows 11 25H2 標準） |

WSL2 が有効であれば Docker Desktop が Linux コンテナをそのまま動かすため、`Dockerfile` と `docker-compose.yml` は変更不要です。

### 起動（PowerShell 推奨）

```powershell
# 初回 or イメージ再ビルド
.\deploy\start.ps1

# 停止
.\deploy\start.ps1 -Stop

# ログ確認
.\deploy\start.ps1 -Logs
```

### 起動（CMD）

```cmd
deploy\start.bat
```

### docker compose 直接操作

```powershell
# 起動
docker compose up -d --build

# 状態確認
docker compose ps
docker compose logs web

# 停止
docker compose down
```

### 動作確認

```powershell
Invoke-WebRequest http://localhost:49231/api/health | Select-Object -ExpandProperty Content
# -> {"status": "ok"}
```

### 開発コマンド（Makefile 代替）

Linux では `make check` を使いますが、Windows では PowerShell スクリプトを使用します。

```powershell
.\make.ps1 check     # compile + validate + test + export（全て）
.\make.ps1 test      # テストのみ
.\make.ps1 validate  # カタログ検証のみ
.\make.ps1 export    # Markdown エクスポートのみ
```

### 自動起動（ネイティブ Python + タスクスケジューラ / 推奨）

Docker Desktop に依存せず、ネイティブ Python で OS 起動時に自動起動する方式です。
サーバは標準ライブラリのみで動作するため、Python 3.12+ があれば追加インストール不要です。

```powershell
# 登録（既定ポート 49231。使用中なら空きポートへ自動フォールバック）
.\deploy\register-windows-service.ps1 -Register

# 状態確認（登録状態・現在ポート・アクセスURLを表示）
.\deploy\register-windows-service.ps1 -Status

# 手動起動 / 停止
.\deploy\register-windows-service.ps1 -Start
.\deploy\register-windows-service.ps1 -Stop

# 登録解除
.\deploy\register-windows-service.ps1 -Unregister
```

| 項目        | 内容                                                                                        |
| ----------- | ------------------------------------------------------------------------------------------- |
| 🗓️ タスク名 | `GlobalCivilApiCatalog-Web`                                                                 |
| 🔌 ポート   | 既定 `49231`。競合時は `--auto-port` により空きポートへ自動移行し `deploy/PORT.lock` に記録 |
| 🌐 IP       | DHCP 自動割当の LAN IP を起動ログと `-Status` で表示                                        |
| ⏰ トリガー | OS 起動時（管理者権限が無い場合はログオン時へ自動フォールバック）                           |
| 🔓 認証     | なし（社内 LAN 限定公開が前提）                                                             |

### 🔐 実行プリンシパル（-Principal / Issue #22）

既定 (`Interactive`) はタスクが対話ユーザーのトークンで動作するため、**ログオフ/切断で常駐プロセスごと終了する**上、
`GlobalCivilApiCatalog-Tunnel`（後述）は powershell ラッパー越しの起動になり Task Scheduler の `RestartCount` が機能しない欠陥がありました
（2026-07-05 に Cloudflare Tunnel Error 1033 のダウンタイムとして顕在化・復旧済み）。

`-Principal` パラメータで実行方式を切り替えられます。

| 値                                | 説明                                                                                                                                                                                                                                                                                                            | 用途                                              |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `Interactive`（既定）             | 現ユーザーの対話セッション依存。後方互換のため既定値のまま維持                                                                                                                                                                                                                                                  | 旧構成との互換性が必要な場合のみ                  |
| `S4U`（**本番採用・推奨**）       | 現ユーザー権限のままログオン非依存で常駐。Task Scheduler がプロセスを直接監視するため `RestartCount`/`RestartInterval` が実際に機能する                                                                                                                                                                         | 24/7 公開サービス（本プロジェクトの本番機はこれ） |
| `LocalService` / `NetworkService` | Windows 組み込みサービスアカウントによる最小権限実行。⚠️ 現状のフォルダ ACL は `Authenticated Users:(M)`（Modify）を継承しており**最小権限の根拠にはならない**。採用時は実行ファイル・設定を Read/Execute に限定し、書込は data/・log 専用ディレクトリへ分離した ACL を設定すること（本番未適用・追加検証必須） | さらなる権限最小化が必要な場合                    |

```powershell
# 本番で採用している再登録コマンド（ログオフ非依存・再発防止）
.\deploy\register-windows-service.ps1 -Register -Principal S4U
.\deploy\register-cloudflared.ps1 -Register -Principal S4U
```

サーバを直接起動する場合:

```powershell
python web\server.py --port 49231 --auto-port --port-lock-file deploy\PORT.lock
# -> Global Civil API Catalog WebUI listening on 0.0.0.0:49231 (LAN: http://192.168.x.x:49231)
```

### 🧩 api_v1 バックエンド（編集・承認 UI 用 / Windows）

編集・承認 UI（`/api/v1/*`・`/auth/*`）を本番で有効にするには、Web UI と同一ホストで api_v1 を常駐させる。
未起動でも閲覧 UI は従来どおり動作し、編集操作のみ 503 になる（graceful degradation）。

```powershell
# 1) 依存導入（初回のみ）
pip install -e ".[db]"

# 2) 環境変数ファイル（deploy/api.env.example を基に作成。実値は Git 管理しない）
#    %APPDATA%\global-civil-api-catalog\api.env に配置し、ACL を自ユーザーのみに限定する

# 3) 手動起動（動作確認。api.env の内容をプロセス環境へ読み込んでから実行）
python -m uvicorn web.api_v1:app --host 127.0.0.1 --port 49232
```

- 常駐化は Web UI と同様に Task Scheduler（`-Principal S4U` 相当）で行う。専用登録スクリプト
  （`register-windows-api-service.ps1`）は未整備のため Issue で追跡する
- ⚠️ この手順の Windows 実機検証は本番反映時に実施する（開発機が Linux のため、Windows 上では NOT RUN）

### 自動起動（Docker Desktop 方式 / 代替）

Docker Desktop 自体の「Start Docker Desktop when you log in」を有効にした上で、
以下のコマンドでタスクを登録することで OS 起動時に自動起動できます。

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
           -Argument "-NonInteractive -File C:\path\to\deploy\start.ps1" `
           -WorkingDirectory "C:\path\to\Global-Civil-API-Catalog"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "GlobalCivilAPICatalog" -Action $action -Trigger $trigger -RunLevel Highest
```

パスは実際のクローン先に合わせて変更してください。

### 注意事項

- `deploy/global-civil-api-catalog-web.service` / `deploy/global-civil-api-catalog-api.service`（systemd）は Linux 専用。Windows では使用しません。
- `Makefile` の `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` はbash構文のため Windows CMD では動作しません。`.\make.ps1 test` を使用してください。
- ファイルパスに日本語が含まれる場合、Docker Desktop の設定で「Use the WSL 2 based engine」を有効にしてください。

---

## 🚀 リリース反映手順（本番 origin = Windows）

GitHub 上で main へマージし tag を作成した後、本番 origin（Windows ホスト）で以下を実施して反映する。
Linux 開発機から本番 origin は操作できないため、この手順は**人手で実行**する。

```powershell
cd C:\path\to\Global-Civil-API-Catalog
git fetch --tags origin
git checkout main
git pull --ff-only origin main

# 該当リリースに migration がある場合のみ、再起動前に適用する
#（v1.2.0 は追加 migration なし）
# 例: CATALOG_DATABASE_URL を読み込んだ上で python -m alembic upgrade head

# サービス再起動
.\deploy\register-windows-service.ps1 -Stop
.\deploy\register-windows-service.ps1 -Start
# api_v1 を常駐化済みの場合は api_v1 も再起動する

# smoke
Invoke-WebRequest http://localhost:49231/api/health | Select-Object -ExpandProperty Content
# ブラウザ: 「登録・承認管理」画面 → ログイン導線 → 一覧表示を確認
```

### ⏪ rollback（事前検証済み・非破壊）

```powershell
git checkout <直前の tag または commit SHA>
.\deploy\register-windows-service.ps1 -Stop
.\deploy\register-windows-service.ps1 -Start
```

- 📌 DB: migration を含まないリリース（v1.2.0 など）は DB rollback 不要。migration を含むリリースは各 PR 記載の downgrade 手順（例: `alembic downgrade -1`）に従う
- ✅ 反映後は Cloudflare Access 経由（`https://api.mirai-dx-platform.com`）で 302 → ログイン → UI 表示、および編集 UI の疎通を確認する

---

## ☁️ Cloudflare Tunnel（api.mirai-dx-platform.com 公開）

Named Tunnel + **Cloudflare Access（認証ゲート必須）** で Web UI をサブドメイン公開します。

### 人間側で必要な初期設定（1回のみ）

```powershell
cloudflared tunnel login                       # ブラウザで Cloudflare 認証
cloudflared tunnel create catalog              # Tunnel 作成
cloudflared tunnel route dns catalog <サブドメイン>  # DNS ルート作成
Copy-Item deploy\cloudflare\config.yml.example deploy\cloudflare\config.yml
# config.yml の <TUNNEL_ID> と hostname を編集
```

### サービス登録（OS 起動時自動起動）

```powershell
.\deploy\register-cloudflared.ps1 -Register -Principal S4U   # 推奨（ログオフ非依存）
.\deploy\register-cloudflared.ps1 -Status
.\deploy\register-cloudflared.ps1 -Start
.\deploy\register-cloudflared.ps1 -Stop
.\deploy\register-cloudflared.ps1 -Unregister
```

### ⚠️ セキュリティ必須事項

- 静的 Web UI（`web/server.py`）は**ログイン認証を持たない**ため、公開前に Cloudflare Zero Trust ダッシュボードで **Access アプリケーション + ポリシー（許可メールアドレス等）** を必ず設定する
- Access 未設定のままの公開は禁止（Security First）
- 新しい API v1 レイヤ（`web/api_v1.py`・opt-in）は **Entra ID OIDC + 5 ロール RBAC を実装済み**で、書込系（登録・更新・論理削除）は認証必須。公開時も Access による外側防御は併用する（多層防御。設定手順: `docs/entra-id-setup.md`）

### ✅ Access 設定状況（2026-07-05 適用済み）

| 項目               | 値                                                                                                                                                                                                    |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Access Application | `Global Civil API Catalog`（`api.mirai-dx-platform.com` 全体を保護）                                                                                                                                  |
| 許可ポリシー       | ドメイン `@mirai-const.co.jp` 全体 + 個別許可メールアドレス（いずれか一致・One-Time PIN 認証）。個別アドレスは Cloudflare Access ダッシュボード側でのみ管理し、本文書には記載しない（PII/標的型対策） |
| 動作確認           | 未認証アクセスは Cloudflare Access ログインページへ 302 リダイレクトされることを確認済み                                                                                                              |
| 変更方法           | Cloudflare Zero Trust ダッシュボード → Access → Applications → `Global Civil API Catalog` からポリシー編集可能                                                                                        |

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
