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

## Linux（現行環境）

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

| 必須 | バージョン目安 |
|---|---|
| Docker Desktop | 4.30+ (WSL2 バックエンド) |
| Python | 3.12+ |
| PowerShell | 7.4+（Windows 11 25H2 標準） |

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

| 項目 | 内容 |
|---|---|
| 🗓️ タスク名 | `GlobalCivilApiCatalog-Web` |
| 🔌 ポート | 既定 `49231`。競合時は `--auto-port` により空きポートへ自動移行し `deploy/PORT.lock` に記録 |
| 🌐 IP | DHCP 自動割当の LAN IP を起動ログと `-Status` で表示 |
| ⏰ トリガー | OS 起動時（管理者権限が無い場合はログオン時へ自動フォールバック） |
| 🔓 認証 | なし（社内 LAN 限定公開が前提） |

> ⚠️ **既知の制約**: タスクは対話ユーザーのトークンで登録されるため、OS 起動時トリガーでも実際のサーバ起動は**該当ユーザーのログオン後**になります。ログオン不要の完全無人起動が必要な場合は、管理者権限で `Register-ScheduledTask -Principal (New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U)` 相当の再登録が必要です。

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
