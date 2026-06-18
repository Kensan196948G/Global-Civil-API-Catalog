# Global Civil API Catalog 詳細仕様設計書

- プロジェクト名: Global Civil API Catalog
- 日本語名: 国内外土木建設APIカタログシステム
- リポジトリ名: `Global-Civil-API-Catalog`
- 文書区分: 詳細仕様設計書
- 版数: v1.0
- 作成日: 2026-06-18
- 前提: 初期版は軽量なWebUI + Markdown/JSONデータ管理を基本とし、将来PostgreSQL/PostGISへ拡張可能にする。

---

## 1. システム全体構成

### 1.1 初期構成

```text
Global-Civil-API-Catalog
├── WebUI
│   ├── API一覧
│   ├── API詳細
│   ├── 接続検証結果
│   ├── 優先度評価
│   └── 成果物出力
├── Catalog Data
│   ├── api_catalog.yaml
│   ├── api_catalog.json
│   ├── verification_results.json
│   └── samples/
├── Connector Scripts
│   ├── gsi_tiles_check.py
│   ├── gsi_elevation_check.py
│   ├── ksj_geojson_check.py
│   ├── hazard_tile_check.py
│   └── jma_forecast_check.py
└── Export
    ├── API台帳.md
    ├── 接続優先度.md
    ├── サンプルリクエスト.md
    └── サンプルレスポンス.md
```

### 1.2 将来構成

```text
Browser
  ↓
WebUI
  ↓
API Server
  ↓
PostgreSQL + PostGIS
  ↓
Connector Workers
  ↓
External APIs / Open Data
```

---

## 2. 技術スタック案

| 層 | 初期版 | 本格版候補 |
|---|---|---|
| フロントエンド | React / Next.js / Vite | Next.js |
| UI | Tailwind CSS または素のCSS | Tailwind CSS |
| データ管理 | YAML + JSON + Markdown | PostgreSQL + PostGIS |
| 接続検証 | Python 3.12 | Python Workers |
| HTTP | requests / httpx | httpx |
| 地理処理 | geopandas, shapely, pyproj | PostGIS + geopandas |
| Markdown出力 | Pythonテンプレート | API + Worker |
| CI | GitHub Actions | GitHub Actions |
| 公開モック | Cloudflare Pages | 社内認証付き環境 |
| 認証 | なし/Basic相当 | Entra ID / HENNGE ONE連携想定 |

---

## 3. ディレクトリ構成

```text
Global-Civil-API-Catalog/
├── README.md
├── docs/
│   ├── requirements.md
│   ├── detailed-design.md
│   ├── api-catalog.md
│   ├── verification-plan.md
│   └── usage-policy.md
├── data/
│   ├── api_catalog.yaml
│   ├── api_catalog.json
│   ├── categories.yaml
│   ├── providers.yaml
│   ├── scoring_rules.yaml
│   └── verification_results.json
├── samples/
│   ├── requests/
│   ├── responses/
│   └── screenshots/
├── scripts/
│   ├── validate_catalog.py
│   ├── export_markdown.py
│   ├── run_verification.py
│   └── connectors/
│       ├── gsi_tiles.py
│       ├── gsi_elevation.py
│       ├── ksj_geojson.py
│       ├── hazard_tiles.py
│       ├── jma_forecast.py
│       ├── usgs_water.py
│       └── noaa_nws.py
├── web/
│   ├── src/
│   └── public/
├── tests/
│   ├── test_catalog_schema.py
│   ├── test_scoring.py
│   └── test_export.py
└── .github/
    └── workflows/
        ├── validate.yml
        └── verify-samples.yml
```

---

## 4. データ設計

### 4.1 API台帳エンティティ

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|---|---|---|---|---|
| API ID | id | string | Yes | `GSI-TILE-STD-001` のような一意ID |
| 名称 | name | string | Yes | API/公開データ名 |
| 英名 | name_en | string | No | 英語名 |
| カテゴリ | category | string | Yes | 地図、地形、防災等 |
| サブカテゴリ | sub_category | string | No | 洪水、行政区域等 |
| 提供元 | provider | string | Yes | 国土地理院、国交省等 |
| 国・地域 | region | string | Yes | JP, US, Global等 |
| 公式URL | official_url | string | Yes | 提供元ページ |
| ドキュメントURL | document_url | string | No | API仕様等 |
| エンドポイント | endpoint_template | string | No | API/タイルURLテンプレート |
| データ形式 | data_formats | array | Yes | JSON, GeoJSON, XYZ Tile等 |
| APIキー要否 | api_key_required | enum | Yes | required / not_required / unknown |
| 認証方式 | auth_type | enum | Yes | none / api_key / oauth2 / other / unknown |
| 利用条件 | license_note | string | Yes | 利用規約、出典表記等 |
| 商用利用 | commercial_use | enum | Yes | allowed / restricted / unknown |
| 更新頻度 | update_frequency | string | No | 随時、年次、短周期等 |
| 最終確認日 | last_checked_at | date | Yes | 台帳確認日 |
| 接続状態 | connection_status | enum | Yes | 未調査等 |
| 信頼度 | trust_rank | enum | Yes | A-E |
| 接続優先度 | connection_priority | int | Yes | 1-5 |
| 業務適合度 | business_fit_score | int | Yes | 0-100 |
| 接続容易性 | integration_score | int | Yes | 0-100 |
| リスクメモ | risk_note | string | No | 仕様変更、制限等 |
| 利用候補PJ | target_projects | array | No | 後続PJ名 |
| タグ | tags | array | No | 検索用 |

### 4.2 接続検証エンティティ

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|---|---|---|---|---|
| 検証ID | id | string | Yes | 一意ID |
| API ID | api_id | string | Yes | 台帳API ID |
| 検証日時 | verified_at | datetime | Yes | 実行日時 |
| 検証者 | verified_by | string | No | 担当者 |
| 結果 | result | enum | Yes | success / warning / failure / skipped |
| HTTPステータス | http_status | int | No | 200等 |
| 応答時間ms | response_time_ms | int | No | 応答時間 |
| レスポンスサイズ | response_size_bytes | int | No | サイズ |
| レコード件数 | record_count | int | No | 取得件数 |
| サンプル要求パス | sample_request_path | string | No | 保存先 |
| サンプル応答パス | sample_response_path | string | No | 保存先 |
| エラー内容 | error_message | string | No | 失敗時 |
| 備考 | note | string | No | 注意事項 |

### 4.3 YAML例

```yaml
- id: GSI-TILE-STD-001
  name: 地理院標準地図タイル
  name_en: GSI Standard Map Tile
  category: 地図
  sub_category: ベースマップ
  provider: 国土地理院
  region: JP
  official_url: https://maps.gsi.go.jp/development/ichiran.html
  document_url: https://maps.gsi.go.jp/development/ichiran.html
  endpoint_template: https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png
  data_formats:
    - XYZ Tile
    - PNG
  api_key_required: not_required
  auth_type: none
  license_note: 出典「国土地理院」または「地理院タイル」の明示が必要
  commercial_use: allowed
  update_frequency: 随時
  last_checked_at: 2026-06-18
  connection_status: 接続候補
  trust_rank: A
  connection_priority: 5
  business_fit_score: 95
  integration_score: 95
  risk_note: タイルごとに個別出典が必要な場合あり
  target_projects:
    - Open Civil Site Risk Checker
    - Public Infrastructure Maintenance Map
  tags:
    - map
    - tile
    - jp
```

---

## 5. スコアリング仕様

### 5.1 信頼度スコア

| 条件 | 点 |
|---|---:|
| 官公庁・国際機関・公式団体 | 30 |
| 仕様ドキュメントあり | 20 |
| 利用条件が明確 | 20 |
| 更新頻度または最終更新日が明確 | 10 |
| 機械処理可能形式 | 10 |
| 接続検証成功 | 10 |

| スコア | ランク |
|---:|---|
| 90-100 | A |
| 70-89 | B |
| 50-69 | C |
| 30-49 | D |
| 0-29 | E |

### 5.2 接続優先度

```text
接続優先度 =
  信頼度スコア * 0.30
+ 業務適合度 * 0.35
+ 接続容易性 * 0.20
+ 後続PJ利用数スコア * 0.15
```

| 点数 | 優先度 |
|---:|---|
| 85以上 | 5 最優先 |
| 70-84 | 4 高 |
| 55-69 | 3 中 |
| 40-54 | 2 低 |
| 39以下 | 1 保留 |

---

## 6. 接続検証仕様

### 6.1 共通検証手順

1. 台帳から接続候補を取得する。
2. APIキー要否を確認する。
3. 認証情報が必要な場合は環境変数から取得する。
4. サンプルリクエストを生成する。
5. HTTPリクエストまたはファイル取得を実行する。
6. ステータスコード、応答時間、サイズを記録する。
7. レスポンスの形式を検証する。
8. サンプルレスポンスを保存する。
9. 接続検証結果を保存する。
10. 台帳の接続ステータスを更新する。

### 6.2 タイムアウト・リトライ

| 項目 | 値 |
|---|---:|
| 接続タイムアウト | 10秒 |
| 読み取りタイムアウト | 30秒 |
| リトライ回数 | 2回 |
| リトライ間隔 | 3秒 |
| 最大レスポンス保存サイズ | 1MB |
| 大容量データ | ヘッダ/メタデータのみ保存 |

### 6.3 接続結果判定

| 結果 | 条件 |
|---|---|
| success | 取得成功、形式検証成功 |
| warning | 取得成功だが利用条件・形式・サイズ等に注意あり |
| failure | 接続失敗、認証失敗、形式不正 |
| skipped | APIキー未設定、利用条件未確認等で意図的に未実施 |

---

## 7. 初期実装コネクタ仕様

| ID | 対象 | 検証内容 | 成功条件 | 注意 |
|---|---|---|---|---|
| GSI-TILE-STD-001 | 地理院標準地図タイル | 指定z/x/yのPNG取得 | HTTP 200、画像として取得 | 出典表記 |
| GSI-ELEVATION-001 | 地理院標高タイル | 指定タイルの標高データ取得 | 数値データとして解釈可能 | 測地成果・更新履歴 |
| MLIT-KSJ-N03-001 | 国土数値情報 行政区域 | 対象年度・地域データ取得 | GeoJSONまたは圧縮ファイル取得成功 | 年度・属性定義 |
| GSI-HAZARD-FLOOD-001 | ハザードマップ洪水タイル | 指定z/x/yのタイル取得 | HTTP 200またはタイルなし正常扱い | 出典表記 |
| JMA-FORECAST-001 | 気象庁 天気予報JSON | 地域コード指定でJSON取得 | JSONとしてパース可能 | 仕様変更リスク |

---

## 8. サンプルリクエスト仕様

### 8.1 curl形式

```bash
curl -L \
  -H "User-Agent: Global-Civil-API-Catalog/1.0" \
  -o samples/responses/gsi_std_tile.png \
  "https://cyberjapandata.gsi.go.jp/xyz/std/10/909/403.png"
```

### 8.2 Python形式

```python
import requests

url = "https://cyberjapandata.gsi.go.jp/xyz/std/10/909/403.png"
headers = {"User-Agent": "Global-Civil-API-Catalog/1.0"}
res = requests.get(url, headers=headers, timeout=30)
res.raise_for_status()

with open("samples/responses/gsi_std_tile.png", "wb") as f:
    f.write(res.content)
```

### 8.3 NOAA NWS API例

```bash
curl -L \
  -H "User-Agent: Global-Civil-API-Catalog/1.0 contact@example.local" \
  -H "Accept: application/geo+json" \
  "https://api.weather.gov/points/38.8894,-77.0352"
```

### 8.4 USGS Water API例

```bash
curl -L \
  -H "User-Agent: Global-Civil-API-Catalog/1.0" \
  "https://waterservices.usgs.gov/nwis/iv/?format=json&sites=01646500&parameterCd=00060"
```

---

## 9. WebUI設計

### 9.1 左サイドメニュー

```text
Dashboard
API Catalog
  ├─ すべて
  ├─ 地図・地形
  ├─ 防災・災害
  ├─ 気象・海象
  ├─ 河川・水文
  ├─ 都市計画・土地
  ├─ BIM/CIM・3D
  └─ 海外API
Verification
  ├─ 接続候補
  ├─ 検証結果
  ├─ 失敗・保留
  └─ 再検証予定
Priority
  ├─ 接続優先度
  ├─ 実装接続候補
  └─ 本格利用候補
Samples
  ├─ リクエスト
  └─ レスポンス
Export
Settings
```

### 9.2 ダッシュボード

| ウィジェット | 内容 |
|---|---|
| 登録件数 | 目標50件に対する現在件数 |
| 接続検証件数 | 目標10件に対する進捗 |
| 実装接続件数 | 目標5件に対する進捗 |
| 本格利用候補件数 | 目標3件に対する進捗 |
| 信頼度分布 | A-Eの件数 |
| カテゴリ分布 | 地図、防災、気象等 |
| 要確認項目 | APIキー不明、利用条件不明、更新頻度不明 |
| 直近失敗 | 接続失敗API一覧 |

### 9.3 API一覧カラム

| 表示名 | 物理名 |
|---|---|
| ID | id |
| 名称 | name |
| カテゴリ | category |
| 提供元 | provider |
| 国・地域 | region |
| 形式 | data_formats |
| APIキー | api_key_required |
| 更新頻度 | update_frequency |
| 信頼度 | trust_rank |
| 接続状態 | connection_status |
| 優先度 | connection_priority |
| 最終確認日 | last_checked_at |

### 9.4 API詳細タブ

1. 基本情報
2. 利用条件
3. 接続情報
4. サンプルリクエスト
5. サンプルレスポンス
6. 検証履歴
7. 後続プロジェクト
8. リスク・メモ

---

## 10. API Server設計 本格版

| Method | Path | 内容 |
|---|---|---|
| GET | `/api/catalog` | API台帳一覧 |
| GET | `/api/catalog/{id}` | API詳細 |
| POST | `/api/catalog` | API登録 |
| PUT | `/api/catalog/{id}` | API更新 |
| DELETE | `/api/catalog/{id}` | API削除 |
| GET | `/api/categories` | カテゴリ一覧 |
| GET | `/api/providers` | 提供元一覧 |
| POST | `/api/verification/{id}/run` | 接続検証実行 |
| GET | `/api/verification` | 検証結果一覧 |
| GET | `/api/priority` | 優先度一覧 |
| GET | `/api/export/markdown` | Markdown出力 |
| GET | `/api/export/json` | JSON出力 |
| GET | `/api/export/csv` | CSV出力 |

レスポンス例:

```json
{
  "id": "GSI-TILE-STD-001",
  "name": "地理院標準地図タイル",
  "category": "地図",
  "provider": "国土地理院",
  "api_key_required": "not_required",
  "data_formats": ["XYZ Tile", "PNG"],
  "trust_rank": "A",
  "connection_status": "接続検証済",
  "connection_priority": 5
}
```

---

## 11. DB設計 本格版

### 11.1 テーブル一覧

| テーブル | 内容 |
|---|---|
| api_catalogs | API台帳 |
| providers | 提供元 |
| categories | カテゴリ |
| verification_results | 接続検証結果 |
| sample_requests | サンプルリクエスト |
| sample_responses | サンプルレスポンス |
| scoring_results | スコアリング結果 |
| target_projects | 利用候補プロジェクト |
| audit_logs | 操作履歴 |

### 11.2 api_catalogs

```sql
CREATE TABLE api_catalogs (
  id VARCHAR(64) PRIMARY KEY,
  name TEXT NOT NULL,
  name_en TEXT,
  category VARCHAR(64) NOT NULL,
  sub_category VARCHAR(64),
  provider VARCHAR(128) NOT NULL,
  region VARCHAR(32) NOT NULL,
  official_url TEXT NOT NULL,
  document_url TEXT,
  endpoint_template TEXT,
  data_formats JSONB NOT NULL,
  api_key_required VARCHAR(32) NOT NULL,
  auth_type VARCHAR(32) NOT NULL,
  license_note TEXT NOT NULL,
  commercial_use VARCHAR(32) NOT NULL,
  update_frequency TEXT,
  last_checked_at DATE NOT NULL,
  connection_status VARCHAR(32) NOT NULL,
  trust_rank VARCHAR(8) NOT NULL,
  connection_priority INTEGER NOT NULL,
  business_fit_score INTEGER NOT NULL,
  integration_score INTEGER NOT NULL,
  risk_note TEXT,
  tags JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 11.3 verification_results

```sql
CREATE TABLE verification_results (
  id VARCHAR(64) PRIMARY KEY,
  api_id VARCHAR(64) NOT NULL REFERENCES api_catalogs(id),
  verified_at TIMESTAMP NOT NULL,
  verified_by VARCHAR(128),
  result VARCHAR(32) NOT NULL,
  http_status INTEGER,
  response_time_ms INTEGER,
  response_size_bytes INTEGER,
  record_count INTEGER,
  sample_request_path TEXT,
  sample_response_path TEXT,
  error_message TEXT,
  note TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## 12. GitHub Actions設計

### 12.1 validate.yml

```yaml
name: Validate Catalog

on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pyyaml jsonschema
      - run: python scripts/validate_catalog.py
      - run: python scripts/export_markdown.py
```

### 12.2 verify-samples.yml

```yaml
name: Verify Sample Connections

on:
  workflow_dispatch:
  schedule:
    - cron: "0 21 * * 0"

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install requests pyyaml
      - run: python scripts/run_verification.py --target initial-10
```

---

## 13. バリデーション仕様

### 13.1 必須チェック

1. `id` が一意である。
2. `name` が空でない。
3. `provider` が空でない。
4. `official_url` がURL形式である。
5. `api_key_required` が許可値である。
6. `auth_type` が許可値である。
7. `trust_rank` がA-Eである。
8. `connection_priority` が1-5である。
9. `business_fit_score` が0-100である。
10. `integration_score` が0-100である。

### 13.2 警告チェック

1. `document_url` が未登録。
2. `license_note` が短すぎる。
3. `update_frequency` が未登録。
4. `commercial_use` がunknown。
5. `api_key_required` がunknown。
6. `last_checked_at` が90日以上前。
7. `connection_status` が未調査のまま。
8. `risk_note` が未登録かつ信頼度C以下。

---

## 14. セキュリティ設計

### 14.1 APIキー管理

1. `.env` に保存し、Git管理しない。
2. GitHub ActionsではRepository Secretsを利用する。
3. UI上ではAPIキーを表示しない。
4. ログ出力時はマスクする。
5. サンプルリクエストでは`{API_KEY}`表記に置換する。

### 14.2 データ保存禁止事項

1. 個人情報
2. 社内機密
3. 本番業務データ
4. APIキー
5. 有償データの無断複製
6. 規約上再配布不可のレスポンス全文

---

## 15. エクスポート仕様

| 出力ファイル | 内容 |
|---|---|
| `export/API台帳.md` | 全件・カテゴリ別・信頼度別一覧 |
| `export/接続優先度.md` | 優先度順リスト |
| `export/接続検証結果.md` | 検証履歴 |
| `export/サンプルリクエスト.md` | curl/Python例 |
| `export/サンプルレスポンス.md` | 加工済みサンプル |

CSV出力カラム:

```csv
id,name,category,provider,region,api_key_required,data_formats,update_frequency,trust_rank,connection_status,connection_priority,last_checked_at
```

---

## 16. 初期マイルストーン

| Phase | 内容 | 完了条件 |
|---|---|---|
| Phase 0 | リポジトリ初期化 | README、docs、data雛形、validation雛形 |
| Phase 1 | API登録50件 | 国内35件以上、海外15件以上、全件に信頼度付与 |
| Phase 2 | 接続検証10件 | 結果JSON、サンプルrequest/response保存 |
| Phase 3 | 実装接続5件 | コネクタ5件、pytest、Markdown出力 |
| Phase 4 | 本格利用候補3件 | スコアリング、採用理由、後続PJ紐付け |

---

## 17. テスト仕様

### 17.1 単体テスト

| テスト | 内容 |
|---|---|
| catalog schema | 必須項目、型、許可値 |
| scoring | スコア計算 |
| export | Markdown/CSV/JSON生成 |
| connector | サンプルURL生成 |
| masking | APIキーがログに出ない |

### 17.2 結合テスト

| テスト | 内容 |
|---|---|
| 台帳読込→一覧表示 | YAML/JSONをWebUIに表示 |
| 台帳読込→接続検証 | 対象APIを検証 |
| 接続検証→結果保存 | verification_results更新 |
| 結果保存→Markdown出力 | 成果物生成 |
| スコアリング→候補抽出 | 本格利用候補3件表示 |

---

## 18. 運用設計

| 項目 | 頻度 |
|---|---|
| API台帳見直し | 月1回 |
| 接続検証 | 週1回または手動 |
| 利用条件確認 | 四半期1回 |
| 本格利用候補見直し | 後続PJ開始時 |
| 除外候補棚卸し | 半期1回 |

ステータス変更ルール:

```text
未調査 → 調査中 → 接続候補 → 接続検証済 → 実装接続済 → 本格利用候補
```

懸念がある場合:

```text
調査中 / 接続候補 / 接続検証済 → 保留 → 再調査 または 除外
```

---

## 19. 初期登録データ

## 初期API・公開データ登録候補 50件

> 「API」はREST/JSON等の狭義APIだけでなく、XYZタイル、GeoJSON、CSV、GML、CKAN、静的ダウンロードを含む「システム接続可能な公開データ」として扱う。

| No | 区分 | 名称 | 提供元 | 形式 | APIキー | 更新頻度目安 | 初期評価 | 用途 |
|---:|---|---|---|---|---|---|---|---|
| 1 | 地図 | 地理院標準地図タイル | 国土地理院 | XYZ Tile | 不要 | 随時 | A | ベースマップ |
| 2 | 地図 | 地理院淡色地図タイル | 国土地理院 | XYZ Tile | 不要 | 随時 | A | 業務画面背景 |
| 3 | 地図 | 地理院写真タイル | 国土地理院 | XYZ Tile | 不要 | 随時 | A | 現地概況 |
| 4 | 地形 | 地理院標高タイル | 国土地理院 | Tile/DEM | 不要 | 随時 | A | 標高・勾配 |
| 5 | 地形 | 地理院Vector | 国土地理院 | Vector Tile | 不要 | 随時 | A | GIS高度表示 |
| 6 | 行政 | 国土数値情報 行政区域 | 国土交通省 | GeoJSON/GML/SHP | 不要 | 年次 | A | 所在地判定 |
| 7 | 土地 | 国土数値情報 土地利用細分メッシュ | 国土交通省 | GeoJSON/GML/SHP | 不要 | 数年 | A | 候補地分析 |
| 8 | 都市 | 国土数値情報 都市地域 | 国土交通省 | GeoJSON/GML/SHP | 不要 | 随時 | A | 都市計画確認 |
| 9 | 交通 | 国土数値情報 道路密度・道路延長 | 国土交通省 | GeoJSON/GML/SHP | 不要 | 年次/随時 | B | 搬入ルート |
| 10 | 交通 | 国土数値情報 鉄道 | 国土交通省 | GeoJSON/GML/SHP | 不要 | 随時 | B | 近接施工 |
| 11 | 交通 | 国土数値情報 港湾 | 国土交通省 | GeoJSON/GML/SHP | 不要 | 随時 | A | マリコン案件 |
| 12 | 交通 | 国土数値情報 空港 | 国土交通省 | GeoJSON/GML/SHP | 不要 | 随時 | B | 制限確認 |
| 13 | 防災 | 国土数値情報 洪水浸水想定区域 | 国土交通省 | GeoJSON/GML/SHP | 不要 | 随時 | A | 候補地リスク |
| 14 | 防災 | 国土数値情報 土砂災害警戒区域 | 国土交通省 | GeoJSON/GML/SHP | 不要 | 随時 | A | 現場リスク |
| 15 | 防災 | 国土数値情報 津波浸水想定 | 国土交通省 | GeoJSON/GML/SHP | 不要 | 随時 | A | 海岸・港湾 |
| 16 | 防災 | 国土数値情報 高潮浸水想定 | 国土交通省 | GeoJSON/GML/SHP | 不要 | 随時 | A | 港湾・沿岸 |
| 17 | 防災 | ハザードマップ洪水タイル | 国土地理院/国交省 | XYZ Tile | 不要 | 随時 | A | 地図重ね合わせ |
| 18 | 防災 | ハザードマップ土砂災害タイル | 国土地理院/国交省 | XYZ Tile | 不要 | 随時 | A | 地図重ね合わせ |
| 19 | 防災 | ハザードマップ津波タイル | 国土地理院/国交省 | XYZ Tile | 不要 | 随時 | A | 地図重ね合わせ |
| 20 | 防災 | ハザードマップ高潮タイル | 国土地理院/国交省 | XYZ Tile | 不要 | 随時 | A | 地図重ね合わせ |
| 21 | 不動産 | 不動産情報ライブラリ 地価公示 | 国土交通省 | API/GeoJSON/PBF | 要確認 | 年次 | A | 工事候補地評価 |
| 22 | 不動産 | 不動産情報ライブラリ 地価調査 | 国土交通省 | API/GeoJSON/PBF | 要確認 | 年次 | A | 土地評価 |
| 23 | 不動産 | 不動産情報ライブラリ 不動産取引価格 | 国土交通省 | API/JSON | 要確認 | 四半期等 | B | 周辺相場 |
| 24 | 都市 | 不動産情報ライブラリ 都市計画 | 国土交通省 | API/GeoJSON/PBF | 要確認 | 随時 | A | 規制確認 |
| 25 | 周辺 | 不動産情報ライブラリ 学校 | 国土交通省 | API/GeoJSON/PBF | 要確認 | 随時 | C | 周辺施設 |
| 26 | 周辺 | 不動産情報ライブラリ 医療機関 | 国土交通省 | API/GeoJSON/PBF | 要確認 | 随時 | C | 周辺施設 |
| 27 | 3D都市 | PLATEAU 3D都市モデル | 国土交通省 | CityGML/3D Tiles等 | 不要 | 年次/随時 | A | BIM/CIM連携 |
| 28 | 3D都市 | PLATEAU SDK/ユースケースデータ | 国土交通省 | 各種 | 不要 | 随時 | B | 3D検討 |
| 29 | 気象 | 気象庁 天気予報JSON | 気象庁 | JSON | 不要 | 定時 | B | 施工判断 |
| 30 | 気象 | 気象庁 アメダスJSON | 気象庁 | JSON | 不要 | 短周期 | B | 現場気象 |
| 31 | 気象 | 気象庁 警報注意報JSON | 気象庁 | JSON | 不要 | 随時 | B | 安全判断 |
| 32 | 気象 | 気象庁 地震情報 | 気象庁 | XML/JSON相当 | 不要 | 随時 | B | 災害対応 |
| 33 | 気象 | 気象庁 台風情報 | 気象庁 | JSON/XML相当 | 不要 | 随時 | B | 海上工事 |
| 34 | 河川 | 水文水質データベース 雨量 | 国土交通省 | Web/CSV相当 | 不要 | 観測周期 | B | 河川判断 |
| 35 | 河川 | 水文水質データベース 水位 | 国土交通省 | Web/CSV相当 | 不要 | 観測周期 | B | 出水リスク |
| 36 | 河川 | 水文水質データベース 流量 | 国土交通省 | Web/CSV相当 | 不要 | 観測周期 | C | 河川工事 |
| 37 | 河川 | 川の防災情報 | 国土交通省 | Web/地図 | 不要 | リアルタイム | B | 災害監視 |
| 38 | 海象 | 海上保安庁 海しる | 海上保安庁 | API/地図/データ | 要確認 | 随時 | A | 海洋土木 |
| 39 | 海象 | NOWPHAS 港湾波浪情報 | 港湾空港技術研究所等 | Web/CSV相当 | 要確認 | 観測周期 | A | 港湾施工 |
| 40 | 環境 | 環境省 大気汚染物質広域監視 | 環境省 | Web/CSV相当 | 不要 | 時間 | B | 環境安全 |
| 41 | 国際地図 | OpenStreetMap Overpass API | OSM | Overpass QL/JSON/XML | 不要 | 随時 | B | 海外・補完 |
| 42 | 国際地図 | OSM Tile | OSM | XYZ Tile | 不要 | 随時 | B | 海外ベース |
| 43 | 国際地形 | OpenTopography API | OpenTopography | REST/GeoTIFF等 | 要確認 | 随時 | B | DEM取得 |
| 44 | 国際建物 | Overture Maps | Overture Maps Foundation | Parquet等 | 不要 | 随時 | B | 海外建物 |
| 45 | 国際気象 | NOAA NWS API | NOAA/NWS | REST/JSON-LD | 不要 | 随時 | B | 米国気象 |
| 46 | 国際気象 | NOAA Climate Data Online API | NOAA/NCEI | REST/JSON | 必要 | 日次等 | C | 気候データ |
| 47 | 国際水文 | USGS Water Data APIs | USGS | REST/JSON | 不要 | 短周期/日次 | A | 水位・流量 |
| 48 | 国際災害 | USGS Earthquake API | USGS | GeoJSON | 不要 | リアルタイム | A | 地震リスク |
| 49 | 国際環境 | OpenAQ API | OpenAQ | REST/JSON | 要確認 | 時間 | B | 大気環境 |
| 50 | 衛星 | NASA Earthdata / FIRMS | NASA | API/GeoJSON/CSV | 必要 | 随時 | C | 災害・火災 |


---

## 20. 実装時の注意点

1. 初期段階では「大量取得」より「存在確認・形式確認・利用条件確認」を優先する。
2. 公式APIでない気象庁JSON等は便利だが、仕様変更リスクを明記する。
3. 地理院タイルやハザードマップタイルは出典表記を必須にする。
4. 国土数値情報は年度・属性定義・データ形式差分を管理する。
5. APIキーが必要なものは、キーなしでも台帳登録は可能とし、接続検証はskippedにできる。
6. スクレイピング依存のデータは安易に本格利用候補へ昇格しない。
7. 有償APIや商用利用制限のあるデータは、必ず「要契約確認」にする。
8. 接続検証で保存するレスポンスは最小限にする。
9. 後続プロジェクトに渡す際は、利用条件と出典表記もセットで渡す。
10. 「便利そう」より「継続して安全に使える」を優先する。

---

## 参考情報・根拠URL

- 国土数値情報ダウンロードサイト（国土交通省）: https://nlftp.mlit.go.jp/ksj/
- 不動産情報ライブラリ API 操作説明（国土交通省）: https://www.reinfolib.mlit.go.jp/help/apiManual/
- 地理院タイル一覧（国土地理院）: https://maps.gsi.go.jp/development/ichiran.html
- 地理院地図ヘルプ（国土地理院）: https://maps.gsi.go.jp/help/
- ハザードマップポータル オープンデータ配信: https://disaportal.gsi.go.jp/hazardmapportal/hazardmap/copyright/opendata.html
- Project PLATEAU（国土交通省）: https://www.mlit.go.jp/plateau/
- 気象庁: https://www.jma.go.jp/
- 水文水質データベース（国土交通省）: https://www1.river.go.jp/
- 川の防災情報（国土交通省）: https://www.river.go.jp/
- USGS APIs: https://www.usgs.gov/products/web-tools/apis
- USGS Water Data APIs: https://www.usgs.gov/tools/usgs-water-data-apis
- National Weather Service API: https://www.weather.gov/documentation/services-web-api
- OpenStreetMap Overpass API: https://wiki.openstreetmap.org/wiki/Overpass_API
- OpenAQ: https://openaq.org/

