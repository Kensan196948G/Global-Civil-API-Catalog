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

サンプルレスポンスは1MB未満に制限します。大容量データ、画像、バイナリ、秘密情報を含むレスポンスは、メタデータのみ保存します。
