#Requires -Version 7.0
<#
.SYNOPSIS
    Cloudflare Tunnel (cloudflared) を Windows サービスとして登録・管理する。

.DESCRIPTION
    Named Tunnel で Web UI (localhost:49231) をサブドメイン公開するための補助スクリプト。
    事前に人間側で以下を実施しておくこと:
      1. cloudflared tunnel login          (ブラウザで Cloudflare 認証)
      2. cloudflared tunnel create catalog (Tunnel 作成)
      3. cloudflared tunnel route dns catalog <サブドメイン>
      4. deploy\cloudflare\config.yml.example を config.yml にコピーして編集
    ⚠️ 本アプリは認証なしのため、公開前に Cloudflare Access ポリシー設定を必須とする。

.PARAMETER Install
    cloudflared を Windows サービスとして登録する (既定動作)。

.PARAMETER Uninstall
    サービスを解除する。

.PARAMETER Status
    サービス状態と設定を表示する。
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath  = Join-Path $ProjectRoot 'deploy\cloudflare\config.yml'

function Resolve-Cloudflared {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        Write-Host "❌ cloudflared が見つかりません。https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ からインストールしてください。" -ForegroundColor Red
        exit 1
    }
    return $cmd.Source
}

if ($Uninstall) {
    & (Resolve-Cloudflared) service uninstall
    Write-Host "✅ cloudflared サービスを解除しました。" -ForegroundColor Green
} elseif ($Status) {
    Write-Host "🔍 cloudflared サービス状態" -ForegroundColor Cyan
    $svc = Get-Service -Name 'cloudflared' -ErrorAction SilentlyContinue
    if ($null -eq $svc) {
        Write-Host "❌ サービス未登録です。-Install で登録してください。" -ForegroundColor Red
    } else {
        Write-Host "   📊 Status : $($svc.Status)" -ForegroundColor Gray
    }
    if (Test-Path $ConfigPath) {
        Write-Host "   📄 Config : $ConfigPath" -ForegroundColor Gray
        Get-Content $ConfigPath | Select-String 'hostname:' | ForEach-Object {
            Write-Host "   🌐 $($_.Line.Trim())" -ForegroundColor Gray
        }
    } else {
        Write-Host "⚠️ $ConfigPath が未作成です (config.yml.example をコピーして編集)。" -ForegroundColor Yellow
    }
} else {
    if (-not (Test-Path $ConfigPath)) {
        Write-Host "❌ $ConfigPath がありません。config.yml.example をコピーして編集してください。" -ForegroundColor Red
        exit 1
    }
    # Windows service registration requires admin rights.
    & (Resolve-Cloudflared) service install --config $ConfigPath
    Write-Host "✅ cloudflared を Windows サービスとして登録しました (OS 起動時に自動起動)。" -ForegroundColor Green
    Write-Host "🔒 Cloudflare Zero Trust ダッシュボードで Access ポリシーを必ず設定してください。" -ForegroundColor Yellow
}
