# バックアップ・復旧手順

対象: Neon PostgreSQL（業務データ正本）＋ `data/*.json`（台帳スナップショット）＋ Git（ソース・文書正本）

## 1. バックアップ構成

| 層 | 媒体 | 頻度 | 保持 |
|---|---|---|---|
| 台帳 JSON スナップショット | Git（`data/`・`export/`） | 週次検証 cron で PR 化 | Git 履歴に準ずる |
| DB データ | Neon 自動バックアップ（PITR） | 常時（Neon 側の既定） | Neon プランに準ずる |
| DB 論理バックアップ | `pg_dump` による手動/定期取得 | 任意（リリース前・重要変更前） | 外部ストレージ推奨 |
| ソース・文書・設定 | Git/GitHub | コミット時 | リポジトリ |

## 2. DB 論理バックアップ（pg_dump）

接続文字列は Secret 管理（`~/.config/global-civil-api-catalog/api.env`）から読み込む。実値をコマンド履歴やログへ出力しない。

```bash
set -a; source ~/.config/global-civil-api-catalog/api.env; set +a
pg_dump "$CATALOG_DATABASE_URL" \
  --format=custom \
  --no-owner \
  --file="$HOME/backups/gc-api-catalog-$(date -u +%Y%m%d-%H%M%S).dump"
```

リストアは Neon の PITR または論理リストアのいずれか:

```bash
pg_restore --clean --if-exists --no-owner \
  --dbname "$CATALOG_DATABASE_URL" \
  "$HOME/backups/gc-api-catalog-<日時>.dump"
```

※ 本番 DB へのリストアは破壊的操作。必ず Approval PR（対象・影響・backup・rollback・検証方法を明記）の承認後に、事前に復元テスト済みの手順のみ実行する。

## 3. 復旧シナリオ

| シナリオ | 復旧手段 | 確認事項 |
|---|---|---|
| エントリ誤更新 | `POST /api/v1/entries/{id}/restore`（版スナップショットから復元・監査記録付き） | 復元後は draft 状態 → 承認フローで再公開 |
| エントリ誤削除 | 同上（論理削除から復活） | deleted_at が解除され draft に戻る |
| DB 全体消失 | Neon PITR（任意時点）→ `alembic upgrade head` → 差分 JSON 再投入 | 復旧時刻以降の変更は audit/version から再適用 |
| JSON 台帳破損 | Git 履歴から `data/api_catalog.json` を復元 → `python scripts/migrate_json_to_db.py --verify-only` | DB と JSON の round-trip 一致 |
| アプリ障害 | `git checkout <直前 tag>` → `systemctl --user restart ...`（docs/operations.md 参照） | health check + metadata 疎通 |

## 4. 定期訓練

- 月1回: `pg_dump` 取得と、開発ブランチへのリストアを実施し結果を記録する。
- 四半期1回: 誤削除 → 版復元 → 承認フローの通し確認。
- 復旧訓練の結果は `reports/handoff/` または Issue に記録し、手順の陳腐化を防ぐ。
