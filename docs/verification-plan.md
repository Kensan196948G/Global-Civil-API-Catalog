# 接続検証計画

## 方針

初期版では、CIや通常テストで外部APIへアクセスしません。外部APIのライブ検証は、担当者が明示的に `scripts/run_verification.py --live` を指定した場合のみ実行します。

## 優先検証対象

1. `GSI-TILE-STD-001`
2. `GSI-ELEVATION-001`
3. `MLIT-KSJ-N03-001`
4. `MLIT-KSJ-FLOOD-001`
5. `GSI-HAZARD-FLOOD-001`
6. `MLIT-REINFOLIB-LANDPRICE-001`
7. `MLIT-PLATEAU-001`
8. `JMA-FORECAST-001`
9. `USGS-WATER-001`
10. `NOAA-NWS-001`

## 判定

- `success`: HTTP取得と形式確認に成功。
- `warning`: 到達可能だが、年度選択、大容量、仕様変更などの注意がある。
- `skipped`: APIキー、利用条件、認証方式が未確定。
- `failure`: 接続失敗、認証失敗、形式不正。

## 保存ルール

サンプルレスポンスは `scripts/run_verification.py` の `MAX_SAMPLE_BYTES`(64KB)でキャップします。詳細は下記「サンプル保存サイズ上限(MAX_SAMPLE_BYTES)方針」を参照してください。大容量データ、画像、バイナリ、秘密情報を含むレスポンスは、この上限で自動的に切り詰められ、`sample_truncated: true` と `note` へ明記されます。

## サンプル保存サイズ上限(MAX_SAMPLE_BYTES)方針(issue #49 / #41 フォローアップ)

Issue #41 で記録済みの、`MAX_SAMPLE_BYTES`(64KB)によるレスポンスサンプル切り詰め問題について、issue #49 で以下の方針を決定しました。

- **現状維持(64KBで切り詰め)を継続する。** 切り詰めサイズの拡張は今回行いません。
- 理由:
  - レスポンスサンプルが肥大化すると、Git管理下の `samples/responses/` および `data/verification_results.json` / `data/verification_history.jsonl` の保存コストが増大する。
  - カタログのエンドポイントはエディタ経由で編集可能なため、SSRFガード(`scripts/url_guard.py`)を通過した先であっても、意図的または誤設定により巨大なレスポンスを返すエンドポイントが登録されうる。上限を緩和すると、単一の検証対象がCI実行時間・保存容量を圧迫するリスクが増す。
  - 64KBはJSON/GeoJSON形式の代表的なレコード件数を確認する(`extract_record_count`)には十分なサンプルサイズであり、切り詰め時は `sample_truncated` フラグと `note` で明示されるため、利用者は「完全なレスポンスではない」ことを常に判別できる。
- 切り詰めが発生した場合の扱い:
  - `sample_truncated: true` を結果へ付与する。
  - `note` に `sample truncated to 64KB` を追記する。
  - `record_count` が切り詰めによりJSONとしてパースできない場合は `None` のままとし、`note` に `record_count unavailable (payload exceeds sample cap)` を追記する(黙って `record_count=None` にしない)。
- 将来、切り詰めサイズの拡張やストリーミング検証(全量チェックサム比較など)が必要になった場合は、別Issueとして再検討する。

## 検証結果の時系列履歴管理(issue #49)

`data/verification_results.json` は従来どおり**直近の実行結果のスナップショット**(毎回上書き)として維持します。これに加えて、時系列の履歴を `data/verification_history.jsonl` (JSON Lines形式、1行1レコード。レコード形式は `verification_results.json` の各要素と同一)に蓄積します。

- `scripts/run_verification.py --append-history` を指定すると、今回の実行結果を `data/verification_history.jsonl` に追記します。`.github/workflows/scheduled-verify.yml` の週次実行では `--live --write --append-history` を指定し、スナップショットと履歴の両方を更新します。
- 保持方針: `verified_at` を基準に**直近90日分**を保持し、それより古いレコードは追記のたびに間引きます(`scripts.catalog_utils.VERIFICATION_HISTORY_RETENTION_DAYS`)。週次実行かつカタログ規模が小さいため、90日分でもファイルサイズは軽微です。
- 実装: `scripts/catalog_utils.py` の `load_verification_history()` / `append_verification_history()`。`verified_at` が欠落・不正な形式のレコードは削除せずそのまま保持します(データを黙って失わないため)。
- **これは epic #46(CRUD・DB移行)前の暫定実装です。** #46 完了後は、履歴管理を `db/models.py` の `VerificationResult` テーブル(既存スキーマ、`verification_results` テーブルに `api_id, verified_at` のインデックス済み)へ統合する想定です。今回のスコープでは DB スキーマ変更・Alembic migration には一切着手していません(将来のfast-follow)。

## 異常検知(issue #49)

`scripts/detect_verification_anomalies.py` が、直近の履歴(`data/verification_history.jsonl`)と今回の検証結果(`data/verification_results.json`)を比較し、以下の異常を検知します。判定ロジックは `detect_anomalies()` という純粋関数として実装されており、`tests/test_verification_anomalies.py` で単体テストしています。

- **result regression**: 前回 `success` だったAPIが今回 `failure` または `warning` になった。
- **response_time_degraded**: 応答時間が前回比2倍以上、または前回比+3000ms以上悪化した(小さい絶対値同士のノイズを誤検知しないよう、比率と絶対値の両基準を用意)。
- **record_count_change**: レコード件数が前回比50%以上増減した。

初回実行(対象APIの履歴が存在しない)場合はクラッシュせず、単に異常なしとして扱います。

`.github/workflows/scheduled-verify.yml` では、検証実行(履歴追記込み)の直後に `scripts/detect_verification_anomalies.py --output data/verification_anomalies.json` を実行し、検知結果を保存します。

## 通知機構(issue #49)

既存の「Create alert issue on verification failures and anomalies」ステップ(`.github/workflows/scheduled-verify.yml`)を拡張し、以下の両方を検知した場合にGitHub Issueを自動起票します。

- `result: failure` の検証結果(従来からの挙動)
- 上記の異常検知結果(`data/verification_anomalies.json`)

起票時は `verification-alert` ラベルの未クローズIssueが既に存在する場合は重複起票せず、既存Issueの確認を促すログのみ出力します(従来の重複防止ロジックを踏襲)。

**今回のスコープ外(将来のfast-follow)**:

- 新規のGitHub Actions secretや、Slack・メール等の外部通知チャネルの追加は行いません。`.github/workflows/scheduled-verify.yml` は `GITHUB_TOKEN` のみで完結する GitHub Issue 起票に留めます。
- 本番アプリ(FastAPI + DB)側の既存Webhook配信機構(`web/webhooks.py`, `db/models.py` の `WEBHOOK_EVENTS`)は、DB接続を持たない GitHub Actions ランナーからは直接利用できないため、今回は連携しません。
- issue #48(owner/steward管理)の support contact 情報と連携した「異常検知時の通知先自動解決」は、#48 が未実装のため今回は対応していません。#48 実装後にfast-followとして、`verification-alert` Issueの担当者アサインやメンションへ反映することを検討します。

## Neon DB統合(将来のfast-follow、issue #46 関連)

epic #46(CRUD・DB移行)完了後は、以下をあわせて実施することを想定しています(今回のスコープには含みません)。

- `data/verification_history.jsonl` の内容を `db/models.py` の `VerificationResult` テーブルへ移行する。
- `scripts/detect_verification_anomalies.py` の比較対象をJSON Linesファイルではなく `verification_results` テーブルへのクエリに置き換える。
- 通知先の自動解決を #48 の support contact 情報と統合する。
