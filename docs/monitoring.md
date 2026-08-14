# 監視・障害対応

## 1. 監視対象と確認方法

| 対象 | 手段 | 正常条件 |
|---|---|---|
| Web UI プロセス | `systemctl --user status global-civil-api-catalog-web.service` | active (running)、Restart 回数が増えていない |
| API v1 プロセス | `systemctl --user status global-civil-api-catalog-api.service` | active (running) |
| Cloudflare Tunnel | `systemctl --user status gc-api-catalog-cloudflared.service` / `cloudflared tunnel info <ID>` | active、connector 接続あり |
| Web UI ヘルス | `curl http://127.0.0.1:49231/api/health` | `{"status":"ok"}` |
| API/DB ヘルス | `python scripts/health_check.py http://127.0.0.1:49231` | 出力末尾が `HEALTH: OK`（Web+API+DB の一括確認） |
| 外部公開 | `curl -s -o /dev/null -w '%{http_code}' https://api.mirai-dx-platform.com/api/health` | 302（Access ログインへリダイレクト） |
| 週次検証 | GitHub Actions `scheduled-verify`（毎週月曜 02:00 UTC） | 検証 PR が作成される |
| 台帳データ鮮度 | `python scripts/validate_catalog.py` | WARNING が無い（180日超の未確認データ無し） |
| Webhook 配信 | API v1 の Webhook 管理画面（`last_delivery_status` / `failure_count`） | 直近配信が HTTP 2xx または未設定。`failure_count` 増加時は宛先URL・署名を確認 |
| E2E 回帰 | GitHub Actions `e2e`（Playwright: 静的UI + フルスタック承認フロー） | PR/merge で成功 |

## 2. ログ確認

```bash
journalctl --user -u global-civil-api-catalog-web -n 100 --no-pager
journalctl --user -u global-civil-api-catalog-api -n 100 --no-pager
journalctl --user -u gc-api-catalog-cloudflared -n 100 --no-pager
```

アクセスログ（Cloudflare）: ダッシュボード → Analytics / HTTP Requests または Access ログで確認。

## 3. アラート

現状はアラート基盤なし。最低限、次の監視を段階的に導入する（epic #49 第2段階）:

1. 週次検証失敗時: `scheduled-verify` から GitHub Issue（ラベル `verification-alert`）を自動起票
2. ヘルスチェック失敗時: cron + メール/Teams 通知（HENNGE/SharePoint 連携は将来）
3. データ鮮度警告: `validate_catalog.py` の WARNING を CI で検知
4. Webhook 配信失敗: 管理画面の `last_delivery_status` / `failure_count` を定期確認し、連続失敗時は購読を停止・再発行（MVP 段階ではメール/Teams 通知は未導入）

即時運用では `python scripts/health_check.py` を cron で毎分実行し、exit code を監視する。失敗時に通知する仕組み（メール/Teams）は次のフェーズで導入する。

## 4. 障害対応フロー（インシデント手順）

1. **検知**: 上記ヘルス/ログ/CI で異常を確認
2. **切り分け**: Web / API / DB / Tunnel のどこで起きているか
   - `systemctl --user status` 4 サービス
   - `curl` ヘルス 2 本
   - `journalctl` で直近エラー
3. **復旧**:
   - プロセス再起動: `systemctl --user restart global-civil-api-catalog-web.service global-civil-api-catalog-api.service`
   - DB 異常: Neon ダッシュボードの稼働状態確認 → 必要なら PITR（docs/backup-restore.md）
   - コード起因: 原因修正 → テスト → 承認済み CI 経路で再デプロイ
4. **記録**: 原因・影響・復旧手順・再発防止を Issue または reports/handoff に記録
5. **自動 rollback 条件**: 主要 API 停止・認証不能・DB 異常・critical 脆弱性 → 事前検証済み rollback（docs/operations.md）

## 5. 停止条件

- 対象環境・リソースが一意に特定できない
- バックアップ・復旧手段なしに破壊的操作が必要
- critical セキュリティ問題が解消できない

いずれも無理な続行をせず、停止理由・影響・代替案・再開条件を報告する。
