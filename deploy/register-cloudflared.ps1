#Requires -Version 7.0
<#
.SYNOPSIS
    Cloudflare Tunnel (gc-api-catalog) を Task Scheduler タスクとして登録・管理する。

.DESCRIPTION
    api.mirai-dx-platform.com へ Web UI (localhost:49231) を公開する Tunnel を
    OS 起動時にバックグラウンド（ウィンドウ非表示）で自動起動する。
    既存の "Cloudflared" Windows サービス（他プロジェクト用）とは独立して動作する。
    事前条件: cloudflared tunnel login / create / route dns 済み、
    deploy\cloudflare\config.yml 作成済み。
#>
[CmdletBinding()]
param(
    [switch]$Register,
    [switch]$Unregister,
    [switch]$Status,
    [switch]$Start,
    [switch]$Stop,
    # Interactive (既定・後方互換) / S4U (ログオン非依存・推奨) / LocalService / NetworkService (最小権限)
    [ValidateSet('Interactive', 'S4U', 'LocalService', 'NetworkService')]
    [string]$Principal = 'Interactive'
)

$ErrorActionPreference = 'Stop'
$TaskName    = 'GlobalCivilApiCatalog-Tunnel'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath  = Join-Path $ProjectRoot 'deploy\cloudflare\config.yml'

function Resolve-Cloudflared {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        Write-Host "❌ cloudflared が見つかりません。" -ForegroundColor Red
        exit 1
    }
    return $cmd.Source
}

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "✅ タスクを削除しました: $TaskName" -ForegroundColor Green
} elseif ($Status) {
    Write-Host "🔍 Tunnel タスク状態: $TaskName" -ForegroundColor Cyan
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "❌ 未登録です。-Register で登録してください。" -ForegroundColor Red
    } else {
        Write-Host "   📊 State : $($task.State)" -ForegroundColor Gray
        Write-Host "   🔐 LogonType : $($task.Principal.LogonType) (UserId: $($task.Principal.UserId))" -ForegroundColor Gray
        & (Resolve-Cloudflared) tunnel --config $ConfigPath info gc-api-catalog 2>$null |
            Select-Object -First 6 | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }
        Write-Host "   🌐 https://api.mirai-dx-platform.com" -ForegroundColor Cyan
    }
} elseif ($Start) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "✅ Tunnel を開始しました: $TaskName" -ForegroundColor Green
} elseif ($Stop) {
    Stop-ScheduledTask -TaskName $TaskName
    Write-Host "✅ Tunnel を停止しました: $TaskName" -ForegroundColor Green
} else {
    if (-not (Test-Path $ConfigPath)) {
        Write-Host "❌ $ConfigPath がありません (config.yml.example をコピーして編集)。" -ForegroundColor Red
        exit 1
    }
    $cloudflared = Resolve-Cloudflared

    if ($Principal -eq 'Interactive') {
        # Hidden window: launch cloudflared through powershell Start-Process so the
        # interactive-token scheduled task does not pop a console at logon.
        # 既知の欠陥: Task Scheduler が監視するのはこの powershell.exe ラッパーのみで
        # 即座に終了するため、cloudflared.exe が後でクラッシュしても RestartCount は働かない。
        # 再発防止には -Principal S4U (推奨) を使うこと。
        $inner = "Start-Process -FilePath '$cloudflared' " +
            "-ArgumentList 'tunnel','--config','$ConfigPath','run' -WindowStyle Hidden"
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
            -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -Command `"$inner`"" `
            -WorkingDirectory $ProjectRoot
    } else {
        # S4U / LocalService / NetworkService は非対話セッションで実行されるため
        # コンソールが表示されず、cloudflared.exe を直接アクションにできる。
        # → Task Scheduler が実プロセスを監視し、RestartCount/RestartInterval が機能する。
        $action = New-ScheduledTaskAction -Execute $cloudflared `
            -Argument "tunnel --config `"$ConfigPath`" run" `
            -WorkingDirectory $ProjectRoot
    }

    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)

    if ($Principal -ne 'Interactive') {
        $principalObj = switch ($Principal) {
            'S4U'             { New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited }
            'LocalService'    { New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\LocalService' -LogonType ServiceAccount -RunLevel Limited }
            'NetworkService'  { New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\NetworkService' -LogonType ServiceAccount -RunLevel Limited }
        }
        $trigger = New-ScheduledTaskTrigger -AtStartup
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
            -Principal $principalObj `
            -Description "Cloudflare Tunnel: api.mirai-dx-platform.com -> localhost:49231 (Principal=$Principal)" `
            -Force -ErrorAction Stop | Out-Null
        Write-Host "✅ 登録完了 (OS 起動時 / AtStartup / Principal: $Principal)" -ForegroundColor Green
    } else {
        $trigger = New-ScheduledTaskTrigger -AtStartup
        try {
            Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
                -Description 'Cloudflare Tunnel: api.mirai-dx-platform.com -> localhost:49231' `
                -Force -ErrorAction Stop | Out-Null
            Write-Host "✅ 登録完了 (OS 起動時 / AtStartup / バックグラウンド)" -ForegroundColor Green
        } catch {
            $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
            Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
                -Description 'Cloudflare Tunnel: api.mirai-dx-platform.com -> localhost:49231' `
                -Force -ErrorAction Stop | Out-Null
            Write-Host "✅ 登録完了 (ログオン時 / AtLogOn へフォールバック)" -ForegroundColor Yellow
        }
    }
    Write-Host "🔒 Cloudflare Zero Trust で Access ポリシー設定を推奨します（現状アプリ認証なし）。" -ForegroundColor Yellow
}
