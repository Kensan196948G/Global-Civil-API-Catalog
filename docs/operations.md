# 運用メモ

## Web UI

- URL: `http://192.168.0.185:49231`
- 固定ポート: `49231`
- ポート定義: `deploy/PORT.lock`
- Dockerコンテナ名: `global-civil-api-catalog-web`
- Dockerイメージ名: `global-civil-api-catalog-web:local`

このサービスでは登録済みポート `49231` を基本とします。ホストIPがDHCP等で変わる場合でも、ポート番号は維持します。
Windows ネイティブ起動（`--auto-port`）では、`49231` が他プロセスに占有されている場合のみ空きポートへ自動フォールバックし、実際のポートを `deploy/PORT.lock` に記録します。現在のポートは `.\deploy\register-windows-service.ps1 -Status` で確認できます。

---

## Linux（旧環境 / 参考）

> ⚠️ 本番は Windows 完結（Task Scheduler 自動起動）へ移行済み。以下は旧 Linux 環境の参考情報です。

### 状態確認

```bash
systemctl --user status global-civil-api-catalog-web.service
docker ps --filter name=global-civil-api-catalog-web
curl http://127.0.0.1:49231/api/health
```

### 再起動

```bash
systemctl --user restart global-civil-api-catalog-web.service
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

- `deploy/global-civil-api-catalog-web.service`（systemd）は Linux 専用。Windows では使用しません。
- `Makefile` の `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` はbash構文のため Windows CMD では動作しません。`.\make.ps1 test` を使用してください。
- ファイルパスに日本語が含まれる場合、Docker Desktop の設定で「Use the WSL 2 based engine」を有効にしてください。

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
