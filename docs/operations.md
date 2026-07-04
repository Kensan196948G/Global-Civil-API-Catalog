# 運用メモ

## Web UI

- URL: `http://192.168.0.185:49231`
- 固定ポート: `49231`
- ポート定義: `deploy/PORT.lock`
- Dockerコンテナ名: `global-civil-api-catalog-web`
- Dockerイメージ名: `global-civil-api-catalog-web:local`

このサービスでは登録済みポート `49231` を変更しません。ホストIPがDHCP等で変わる場合でも、ポート番号は維持します。

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

### 自動起動（タスクスケジューラ）

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
