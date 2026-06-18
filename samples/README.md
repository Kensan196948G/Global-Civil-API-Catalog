# samples/

`scripts/run_verification.py` が実接続検証時に生成する、リクエスト/レスポンスの参考サンプルです。

- `requests/<API_ID>.txt` — 検証に用いた `curl` コマンド（`User-Agent` 付き）。
- `responses/<API_ID>.sample` — 実際のレスポンス本文の先頭部分。

## 注意：レスポンスは最大64KBに切り詰められます

レスポンスサンプルは `MAX_SAMPLE_BYTES = 64KB` で**先頭64KBのみ保存**します。
そのため、64KBを超えるレスポンス（例: 国土数値情報(KSJ)のHTMLランディングページ）は
**文書の途中（タグの途中を含む）で切れた不完全なHTML**になります。これは仕様です。

- 切り詰められたサンプルは `verification_results.json` の該当エントリで
  `"sample_truncated": true` と `note` の「sample truncated to 64KB」で識別できます。
- `response_size_bytes` は「保存したサンプルのバイト数」であり、
  切り詰め時は実レスポンス全長とは一致しません。
- これらのサンプルは内部の参考用アーティファクトで、Web UI からは配信されません
  （配信経路は `/api/*`, `/data/*`, `/exports/*`, `/design.html` のみ）。
