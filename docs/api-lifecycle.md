# 📜 API定義ライフサイクル管理（epic #48）

## 1. 🎯 目的

各カタログエントリに owner(データ所有者) / steward(データスチュワード) / reviewer(レビュー担当) /
support contact(問い合わせ先) を記録し、**API定義自体の存続状態**(ライフサイクル)を管理する。

これは要件定義書 11 章および Issue #44 で指摘された「提供終了/利用終了」専用ステータス欠落問題
（`connection_status='除外'` と意味が異なるにもかかわらず区別する手段がなかった問題）を解消する。

## 2. 🧭 責務分担 — `lifecycle_status` と `entry_workflow.state`(#47) の違い

同じカタログエントリに2種類の「状態」が存在するため、混同しないよう明確に分離する。

| フィールド                         | 管轄 Epic | 対象                                                       | 例                                                                    |
| ---------------------------------- | --------- | ---------------------------------------------------------- | --------------------------------------------------------------------- |
| `catalog_entries.lifecycle_status` | #48(本書) | **API定義そのもの**が現在有効か・提供中か・廃止済みか      | `draft` / `active` / `deprecated` / `retired`                         |
| `entry_workflow.state`             | #47       | **レコード値の変更**が編集→レビュー→承認のどの段階にあるか | `draft` / `in_review` / `pending_approval` / `published` / `rejected` |

- 両者は独立した状態機械であり、片方の遷移がもう片方を自動的に変更することはない。
- 遷移操作はいずれも `entry_workflow`／`lifecycle_status` の値のフィールド更新として扱われ、
  #47 の監査ログ・版管理の仕組み（`record_audit` / `snapshot_entry`）を共通で利用する
  （設計書 §5.2 の方針どおり）。
- 語彙が偶然 `draft` を共有しているが意味は異なる点に注意（前者は「API定義がまだ下書き段階」、
  後者は「値の変更が未提出」）。

## 3. 🔄 `lifecycle_status` の状態遷移ルール

```
draft ──────────────▶ active
                        │
                        ├──▶ deprecated ──▶ retired
                        │
                        └──────────────────▶ retired
```

| 遷移元       | 遷移先       | 意味                                            |
| ------------ | ------------ | ----------------------------------------------- |
| `draft`      | `active`     | API定義の初回公開・提供開始                     |
| `active`     | `deprecated` | 非推奨化（新規利用は非推奨、既存利用は継続可）  |
| `active`     | `retired`    | 即時の提供終了/利用終了（後継なし、緊急停止等） |
| `deprecated` | `retired`    | 猶予期間終了後の正式な提供終了/利用終了         |

`retired` は終端状態であり、そこからの遷移は許可しない（要件定義書 11 章「利用終了」に対応する恒久ステータス）。
新規作成されたエントリは `lifecycle_status` カラムの `server_default` により `active` から開始する
（既存データの後方互換のための挙動と同一。将来的に「まだ定義中」の状態から始めたい場合は
`draft` を明示的に指定する API 拡張を別Issueで検討する）。

不正な遷移は `POST /api/v1/entries/{entry_id}/lifecycle` が `400 Bad Request` を返し拒否する。

## 4. 🔌 API

### `POST /api/v1/entries/{entry_id}/lifecycle`

- 権限: `Catalog.Editor` または `Catalog.Admin`（`require_editor` 相当）
- リクエスト: `{"lifecycle_status": "deprecated", "reason": "後継APIへ移行のため"}`
- 成功時: `entry_workflow` とは独立に `catalog_entries.lifecycle_status` /
  `lifecycle_updated_at` を更新し、`record_audit`(action=`lifecycle_transition`) と
  `dispatch_webhooks`(event=`entry.lifecycle_transition`) を実行する。
- 不正な遷移: `400`。エントリ不在/論理削除済み: `404`。

### `POST /api/v1/entries`, `PATCH /api/v1/entries/{entry_id}`

- `owner` / `steward` / `reviewer` / `support_contact` を任意項目として受け付ける
  （自由記入のテキスト。氏名・部署・連絡先メール等、業務上の連絡先情報を想定）。
- `lifecycle_status` はこれらのエンドポイントからは変更できない
  （専用の `/lifecycle` エンドポイントのみが遷移ルールを強制できる）。

### `GET /api/v1/entries`, `GET /api/v1/entries/{entry_id}`

- レスポンスに `owner` / `steward` / `reviewer` / `support_contact` /
  `lifecycle_status` / `lifecycle_updated_at` を含む。

### `GET /api/v1/entries/stewardship-gaps`

責任者未設定・ライフサイクル停滞エントリの検出用（Completion Criteria 対応）。

```json
{
  "missing_owner_steward": [ {"id": "...", "name": "...", "owner": null, "steward": null, ...} ],
  "stale_deprecated": [ {"id": "...", "lifecycle_status": "deprecated", "lifecycle_updated_at": "...", ...} ],
  "stale_deprecated_threshold_days": 90
}
```

- `missing_owner_steward`: `owner` と `steward` の両方が未設定のエントリ。
- `stale_deprecated`: `lifecycle_status='deprecated'` のまま `lifecycle_updated_at` から
  90日以上経過しているエントリ（`STALE_DEPRECATED_DAYS` で定義。設計書 §5.2 の
  「週次検証バッチへの検査追加」は本エントリポイントを叩く形で epic #49 側の通知機構と
  連携させる想定。バッチ本体への組み込みは本PRの対象外・残課題とする）。
- 認証: 読み取り専用 API と同じ可視性ルール（匿名は `published` のみ、staff は全件）。

## 5. 🗄️ スキーマ

`migrations/versions/20260906_07_owner_lifecycle.py`（additive、既存データは全て `active` として
バックフィル）。

```sql
ALTER TABLE catalog_entries
  ADD COLUMN owner               text,
  ADD COLUMN steward             text,
  ADD COLUMN reviewer            text,
  ADD COLUMN support_contact     text,
  ADD COLUMN lifecycle_status    text NOT NULL DEFAULT 'active'
      CHECK (lifecycle_status IN ('draft','active','deprecated','retired')),
  ADD COLUMN lifecycle_updated_at timestamptz;
```

### 設計書 §5.1 との差異（技術判断の記録）

`docs/epic-detailed-design-q4.md` §5.1 の初期スケッチでは連絡先を
`jsonb`（`{name, org, email}`）で持つ案を示していたが、実装時の Issue #48 詳細指示に基づき、
シンプルな `text` カラム（自由記入）を採用した。理由:

- CRUD スキーマ（`web/api_v1.py` の `EntryCreate`/`EntryPatch`）がフラットな文字列のままで済み、
  ネストしたバリデーションモデルが不要。
- 現段階では連絡先の構造化検索（組織名での絞り込み等）の要件がなく、過剰設計を避けた。
- 将来的に構造化が必要になった場合も、`text` → `jsonb` への移行は additive な
  expand-and-contract で対応可能（後方互換を維持したまま拡張できる）。

`lifecycle_changed_at` という初期案のカラム名は `lifecycle_updated_at` に統一した
（`entry_workflow.updated_at` や `catalog_entries.updated_at` との命名一貫性のため）。
