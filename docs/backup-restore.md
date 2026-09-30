# バックアップ・復旧手順

対象: PostgreSQL（業務データ正本）＋ `data/*.json`（台帳スナップショット）＋ Git（ソース・文書正本）

> **2026-09-13 更新（CTO総合評価での実測に基づく）**
> 本文書は以前「Neon 自動バックアップ（PITR）」を前提としていたが、実測の結果:
> - 本番 origin の DB は **ローカル PostgreSQL 16.14**（127.0.0.1:5432 / `global_civil_api_catalog`）である。
> - 一方 `~/.config/global-civil-api-catalog/api.env` の `CATALOG_DATABASE_URL` は
>   **Neon（ep-spring-dust-aw25w51h…/neondb）を指したままで、認証に失敗していた**
>   （`password authentication failed for user 'neondb_owner'`）。
>   つまり **api_v1 の書込層は稼働しておらず、PITR も存在しない**。
> - その状態で pg_dump を定期実行する機構が**存在しなかった**（`backups/` 無し・unit 無し・timer 無し）。
>
> 本版では (1) 事実に合わせて記述を修正し、(2) 日次バックアップの自動化を追加し、
> (3) 復元を実測した手順のみを掲載する。**DB 接続先の是正は別途の運用判断事項**（§5 参照）。

## 1. バックアップ構成

| 層 | 媒体 | 頻度 | 保持 | 実装 |
|---|---|---|---|---|
| DB データ | `scripts/db_backup.py` → `pg_dump --format=custom` | 日次 03:40 JST | 14世代 | `global-civil-api-catalog-db-backup.timer` |
| 台帳 JSON スナップショット | Git（`data/`・`export/`） | 週次検証 workflow で PR 化 | Git 履歴に準ずる | `.github/workflows/scheduled-verify.yml` |
| JSON＋成果物のコピー | `scripts/backup_catalog.py` | 任意 | 任意 | 手動実行 |
| ソース・文書・設定 | Git/GitHub | コミット時 | リポジトリ | — |

保存先の既定: `~/backups/global-civil-api-catalog/gcac-<UTC時刻>.dump`（＋ `.sha256`）
変更する場合: `CATALOG_BACKUP_DIR` または `--dest`。

> ⚠️ **残課題（重要）**: 保存先が同一ホスト内であるため、**ホスト障害時には
> バックアップごと失われる**。外部ストレージ（NAS / オブジェクトストレージ）への
> 退避と RPO/RTO の決定が必要。これは未決定事項であり、本番運用可の判断には
> 別途の承認を要する。

## 2. DB 論理バックアップ

### 2.1 自動実行（systemd user unit）

```bash
# 登録（未登録の場合のみ）
bash deploy/install-systemd-units.sh

# 状態確認
bash deploy/install-systemd-units.sh --status
systemctl --user list-timers --all | grep db-backup

# 手動で今すぐ1回実行
systemctl --user start global-civil-api-catalog-db-backup.service
systemctl --user show -p Result --value global-civil-api-catalog-db-backup.service   # success
journalctl --user -u global-civil-api-catalog-db-backup.service -n 20 --no-pager
```

接続は **Unix ソケットの peer 認証**（`--host /var/run/postgresql`）を使う。
パスワードを引数・環境変数・ログのどこにも出さないためである。

### 2.2 手動実行

```bash
python3 scripts/db_backup.py --keep 14
python3 scripts/db_backup.py --dry-run          # 実行内容のみ確認
python3 scripts/db_backup.py --dest /mnt/nas/gcac-backup --keep 30
```

### 2.3 pg_dump / pg_restore のバージョン固定（再発防止・重要）

本ホストには PostgreSQL 16 / 17 / 18 のクライアントが混在しており、PATH 依存では
**「バックアップは取れるが復元できない」**状態になる。2026-09-13 に実測した2つの障害:

| 事象 | 症状 |
|---|---|
| `pg_dump`=17（`/usr/local/bin`）・`pg_restore`=16（`/usr/bin`）のメジャー不一致 | `pg_restore: ファイルヘッダ内のバージョン(1.16)はサポートされていません` |
| `pg_dump`=18 で取得し、サーバ 16.14 へ復元 | `unrecognized configuration parameter "transaction_timeout"`（dump に `SET transaction_timeout = 0;` が埋め込まれる） |

したがって **dump と restore は (a) 相互に同一メジャー、(b) サーバ以下** を満たす必要がある。
`scripts/db_backup.py` は既定で `/usr/lib/postgresql/16/bin` の組を使う。
サーバをメジャーアップグレードしたら `CATALOG_PG_BINDIR` を合わせること。

## 3. リストア手順（実測済み）

### 3.1 検証用DBへの復元（推奨・非破壊）

```bash
# 1) scratch DB を作る
createdb -h /var/run/postgresql gcac_restore_verify

# 2) 復元（取得時と同一メジャーの pg_restore を使う）
DUMP=$(ls -t ~/backups/global-civil-api-catalog/*.dump | head -1)
/usr/lib/postgresql/16/bin/pg_restore --no-owner --no-privileges \
  --dbname gcac_restore_verify "$DUMP"

# 3) 件数を突き合わせる
for t in catalog_entries verification_results audit_log entry_workflow \
         local_users webhook_subscriptions catalog_entry_versions; do
  echo "$t src=$(psql -h /var/run/postgresql -d global_civil_api_catalog -tAc "select count(*) from $t") \
restored=$(psql -h /var/run/postgresql -d gcac_restore_verify -tAc "select count(*) from $t")"
done

# 4) 後始末
dropdb -h /var/run/postgresql gcac_restore_verify
```

**2026-09-13 の実測結果（この手順で確認済み）**: 全10テーブルで件数一致
（catalog_entries 50 / verification_results 30 / audit_log 32 / entry_workflow 50 /
local_users 1 / webhook_subscriptions 4）、`catalog_entries` の ID 集合 md5 も一致。

### 3.2 本番DBへの復元（破壊的操作）

```bash
pg_restore --clean --if-exists --no-owner --no-privileges \
  --dbname global_civil_api_catalog "$DUMP"
```

※ 本番 DB へのリストアは破壊的操作。必ず Approval PR（対象・影響・backup・
rollback・検証方法を明記）の承認後に、**事前に §3.1 で復元テスト済みの手順のみ**
実行する。

## 4. 復旧シナリオ

| シナリオ | 復旧手段 | 確認事項 |
|---|---|---|
| エントリ誤更新 | `POST /api/v1/entries/{id}/restore`（版スナップショットから復元・監査記録付き） | 復元後は draft 状態 → 承認フローで再公開 |
| エントリ誤削除 | 同上（論理削除から復活） | deleted_at が解除され draft に戻る |
| DB 全体消失 | §3.1 で検証した dump を新規DBへ復元 → `alembic upgrade head` | 件数一致を確認後、接続先を切替 |
| スキーマのみ破損 | `alembic upgrade head`（履歴は `alembic_version` で管理） | `alembic current` が head と一致 |
| JSON 台帳破損 | Git 履歴から `data/api_catalog.json` を復元 → `python scripts/migrate_json_to_db.py --verify-only` | DB と JSON の round-trip 一致 |
| アプリ障害 | `git checkout <直前 tag>` → `systemctl --user restart ...`（docs/operations.md 参照） | `python3 scripts/health_check.py` が `HEALTH: OK` |

## 5. 残課題（未解決・要判断）

1. **本番 api.env の DB 接続先が稼働していない**（Neon のパスワード失効）。
   api_v1 を復旧するには、ローカル PostgreSQL（`global_civil_api_catalog`）へ
   切り替えて `systemctl --user restart global-civil-api-catalog-api` するか、
   Neon の現行資格情報を再取得する。**どちらを正とするかは運用判断が必要**。
   背景: README は「Neon PostgreSQL」、`docs/operations.md` は Linux 移行を記載しており、
   記述が一致していない。
2. **オフサイト退避**（§1 の ⚠️）と RPO/RTO の決定。
3. バックアップの**復元訓練の定期化**（§6）と、失敗時の通知
   （現状は systemd の failed 状態と journal のみ。他プロジェクトのような
   通知 unit は未設定）。

## 6. 定期訓練

- 月1回: §3.1 の non-destructive 復元検証を実施し、件数一致を記録する。
- 四半期1回: 誤削除 → 版復元 → 承認フローの通し確認。
- 復旧訓練の結果は `reports/handoff/` または Issue に記録し、手順の陳腐化を防ぐ。
