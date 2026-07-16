#Requires -Version 7.0
<#
.SYNOPSIS
    Global Civil API Catalog Web UI を OS 起動時に自動起動する
    Windows Task Scheduler タスクを登録・管理する。

.DESCRIPTION
    ネイティブ Python (web\server.py) を Task Scheduler タスクとして登録し、
    OS 起動時 (AtStartup) に Web UI を自動起動する。管理者権限が無い場合は
    ログオン時 (AtLogOn) トリガーへ自動フォールバックする。

.PARAMETER Register
    タスクを登録する (既定動作)。

.PARAMETER Unregister
    タスクを削除する。

.PARAMETER Status
    タスクの状態・最終実行結果・現在ポート・アクセス URL を表示する。

.PARAMETER Start
    登録済みタスクを即時開始する。

.PARAMETER Stop
    実行中タスクを停止する。

.PARAMETER Port
    Web UI が listen するポート (既定: 49231)。

.PARAMETER Principal
    タスクの実行アカウント種別。既定は Interactive (現行動作を維持)。
    - Interactive : 現ユーザーの対話セッション依存 (既定・後方互換)
    - S4U         : 現ユーザー権限のままログオン非依存で実行 (ログオフ/切断でも常駐継続、推奨)
    - LocalService / NetworkService : Windows 組み込みサービスアカウント (最小権限。
      プロジェクトディレクトリへの読み取り ACL が必要。事前に -Status で動作確認すること)

.EXAMPLE
    pwsh -NoProfile -File .\deploy\register-windows-service.ps1 -Register

.EXAMPLE
    pwsh -NoProfile -File .\deploy\register-windows-service.ps1 -Register -Principal S4U

.EXAMPLE
    pwsh -NoProfile -File .\deploy\register-windows-service.ps1 -Status
#>
[CmdletBinding()]
param(
    [switch]$Register,
    [switch]$Unregister,
    [switch]$Status,
    [switch]$Start,
    [switch]$Stop,
    [int]$Port = 49231,
    [ValidateSet('Interactive', 'S4U', 'LocalService', 'NetworkService')]
    [string]$Principal = 'Interactive'
)

$ErrorActionPreference = 'Stop'

# ---- 定数 / パス解決 ------------------------------------------------------
$TaskName     = 'GlobalCivilApiCatalog-Web'
$ProjectRoot  = Split-Path -Parent $PSScriptRoot
$ServerScript = Join-Path $ProjectRoot 'web\server.py'
$PortLockRel  = 'deploy\PORT.lock'
$PortLockPath = Join-Path $ProjectRoot $PortLockRel

# ---- ヘルパ ----------------------------------------------------------------
function Resolve-PythonPath {
    # pythonw.exe (コンソール窓なし) を優先し、無ければ python.exe / py を返す。
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $cmd -and $cmd.Source) {
        $pythonw = Join-Path (Split-Path -Parent $cmd.Source) 'pythonw.exe'
        if (Test-Path $pythonw) {
            return $pythonw
        }
        return $cmd.Source
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py -and $py.Source) {
        return $py.Source
    }
    return $null
}

function Get-LanIPAddress {
    # LAN IP を推定する。DHCP 由来の IPv4 を優先し、無ければ
    # 169.254 (APIPA) / 127 (loopback) 以外の最初の IPv4 を返す。
    try {
        $addrs = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop
    } catch {
        return $null
    }

    $dhcp = $addrs | Where-Object { $_.PrefixOrigin -eq 'Dhcp' } | Select-Object -First 1
    if ($null -ne $dhcp) {
        return $dhcp.IPAddress
    }

    $fallback = $addrs |
        Where-Object { $_.IPAddress -notmatch '^(169\.254\.|127\.)' } |
        Select-Object -First 1
    if ($null -ne $fallback) {
        return $fallback.IPAddress
    }
    return $null
}

function Get-CurrentPort {
    # PORT.lock から現在ポートを読む。無ければ指定ポートを返す。
    if (Test-Path $PortLockPath) {
        $raw = (Get-Content $PortLockPath -Raw).Trim()
        if ($raw -match '^\d+$') {
            return [int]$raw
        }
    }
    return $Port
}

# ---- アクション: Register --------------------------------------------------
function Invoke-Register {
    $python = Resolve-PythonPath
    if ($null -eq $python) {
        Write-Host "❌ python.exe が見つかりません。Python をインストールし PATH に追加してください。" -ForegroundColor Red
        exit 1
    }
    if (-not (Test-Path $ServerScript)) {
        Write-Host "❌ サーバースクリプトが見つかりません: $ServerScript" -ForegroundColor Red
        exit 1
    }

    Write-Host "🔧 タスク登録を開始します: $TaskName" -ForegroundColor Cyan
    Write-Host "   🐍 Python      : $python" -ForegroundColor Gray
    Write-Host "   📄 Server      : $ServerScript" -ForegroundColor Gray
    Write-Host "   📁 WorkingDir  : $ProjectRoot" -ForegroundColor Gray
    Write-Host "   🔌 Port        : $Port" -ForegroundColor Gray
    Write-Host "   🔐 Principal   : $Principal" -ForegroundColor Gray

    # -Force で上書き登録する（先に削除すると登録失敗時に既存設定を失うため）
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
        Write-Host "⚠️ 既存タスクを検出しました。上書き登録します。" -ForegroundColor Yellow
    }

    # README の運用手順は他端末からの LAN 直接 IP アクセスを前提としており
    # (`-Status` が案内する自動割当 IP での接続)、server.py 側の既定 bind は
    # #38 でセキュリティ強化のため 127.0.0.1 化されている。本番の Windows
    # ネイティブ経路ではここで明示的に 0.0.0.0 を指定し、LAN アクセスを維持する。
    $argLine = ('"{0}" --host 0.0.0.0 --port {1} --auto-port --port-lock-file "{2}"' -f `
        $ServerScript, $Port, $PortLockRel)

    $action = New-ScheduledTaskAction -Execute $python -Argument $argLine -WorkingDirectory $ProjectRoot

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero)

    $startupTrigger = New-ScheduledTaskTrigger -AtStartup

    if ($Principal -ne 'Interactive') {
        # S4U / LocalService / NetworkService: ログオン非依存で常駐し、Task Scheduler が
        # プロセスを直接監視するため RestartCount/RestartInterval が実際に機能する。
        $principalObj = switch ($Principal) {
            'S4U'             { New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited }
            'LocalService'    { New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\LocalService' -LogonType ServiceAccount -RunLevel Limited }
            'NetworkService'  { New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\NetworkService' -LogonType ServiceAccount -RunLevel Limited }
        }
        try {
            Register-ScheduledTask -TaskName $TaskName `
                -Action $action `
                -Trigger $startupTrigger `
                -Settings $settings `
                -Principal $principalObj `
                -Description "Global Civil API Catalog Web UI (native Python) auto-start at OS boot (Principal=$Principal)" `
                -Force -ErrorAction Stop | Out-Null
            Write-Host "✅ 登録完了 (トリガー: OS 起動時 / AtStartup / Principal: $Principal)" -ForegroundColor Green
        } catch {
            Write-Host "❌ タスク登録に失敗しました ($Principal): $($_.Exception.Message)" -ForegroundColor Red
            exit 1
        }
    } else {
        # 第一候補: AtStartup (管理者権限が必要)
        try {
            Register-ScheduledTask -TaskName $TaskName `
                -Action $action `
                -Trigger $startupTrigger `
                -Settings $settings `
                -Description 'Global Civil API Catalog Web UI (native Python) auto-start at OS boot' `
                -Force -ErrorAction Stop | Out-Null
            Write-Host "✅ 登録完了 (トリガー: OS 起動時 / AtStartup)" -ForegroundColor Green
        } catch {
            Write-Host "⚠️ AtStartup 登録に失敗しました (管理者権限が必要な可能性)。" -ForegroundColor Yellow
            Write-Host "   理由: $($_.Exception.Message)" -ForegroundColor Gray
            Write-Host "🔧 ログオン時トリガー (AtLogOn / 現ユーザー) へフォールバックします..." -ForegroundColor Cyan

            $logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
            try {
                Register-ScheduledTask -TaskName $TaskName `
                    -Action $action `
                    -Trigger $logonTrigger `
                    -Settings $settings `
                    -Description 'Global Civil API Catalog Web UI (native Python) auto-start at user logon' `
                    -Force -ErrorAction Stop | Out-Null
                Write-Host "✅ 登録完了 (トリガー: ログオン時 / AtLogOn / $env:USERNAME)" -ForegroundColor Green
            } catch {
                Write-Host "❌ タスク登録に失敗しました: $($_.Exception.Message)" -ForegroundColor Red
                exit 1
            }
        }
    }

    Write-Host ""
    Write-Host "🌐 起動後アクセス URL は -Status で確認できます:" -ForegroundColor Cyan
    Write-Host "   pwsh -NoProfile -File .\deploy\register-windows-service.ps1 -Status" -ForegroundColor Gray
}

# ---- アクション: Unregister ------------------------------------------------
function Invoke-Unregister {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        Write-Host "⚠️ タスクが存在しません: $TaskName" -ForegroundColor Yellow
        return
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "✅ タスクを削除しました: $TaskName" -ForegroundColor Green
}

# ---- アクション: Status ----------------------------------------------------
function Invoke-Status {
    Write-Host "🔍 タスク状態: $TaskName" -ForegroundColor Cyan
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "❌ 未登録です。-Register で登録してください。" -ForegroundColor Red
        return
    }

    $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host "   ✅ 登録済み" -ForegroundColor Green
    Write-Host "   📊 State           : $($task.State)" -ForegroundColor Gray
    Write-Host "   🔐 LogonType       : $($task.Principal.LogonType) (UserId: $($task.Principal.UserId))" -ForegroundColor Gray
    if ($null -ne $info) {
        Write-Host "   ⏱ LastRunTime      : $($info.LastRunTime)" -ForegroundColor Gray
        Write-Host "   🔢 LastTaskResult   : $($info.LastTaskResult)" -ForegroundColor Gray
        Write-Host "   ⏭ NextRunTime      : $($info.NextRunTime)" -ForegroundColor Gray
    }

    Write-Host ""
    if (Test-Path $PortLockPath) {
        $curPort = Get-CurrentPort
        $lan = Get-LanIPAddress
        Write-Host "🔌 現在ポート (PORT.lock): $curPort" -ForegroundColor Green
        Write-Host "🌐 アクセス URL:" -ForegroundColor Cyan
        Write-Host "   http://localhost:$curPort" -ForegroundColor Gray
        if ($null -ne $lan) {
            Write-Host "   http://${lan}:$curPort" -ForegroundColor Gray
        }
    } else {
        Write-Host "⚠️ PORT.lock が未生成です (タスク未起動の可能性)。" -ForegroundColor Yellow
    }
}

# ---- アクション: Start / Stop ---------------------------------------------
function Invoke-Start {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "❌ 未登録です。-Register で登録してください。" -ForegroundColor Red
        exit 1
    }
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "✅ タスクを開始しました: $TaskName" -ForegroundColor Green
}

function Invoke-Stop {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "❌ 未登録です。" -ForegroundColor Red
        exit 1
    }
    Stop-ScheduledTask -TaskName $TaskName
    Write-Host "✅ タスクを停止しました: $TaskName" -ForegroundColor Green
}

# ---- ディスパッチ ----------------------------------------------------------
if ($Unregister) {
    Invoke-Unregister
} elseif ($Status) {
    Invoke-Status
} elseif ($Start) {
    Invoke-Start
} elseif ($Stop) {
    Invoke-Stop
} else {
    # 既定動作は Register
    Invoke-Register
}
