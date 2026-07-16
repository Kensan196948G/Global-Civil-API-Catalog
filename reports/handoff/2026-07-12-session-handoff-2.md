# 📋 セッション引き継ぎ (Session Handoff) — 2026-07-12 #2（MCP整理セッション）

> 🧭 前 handoff（`2026-07-12-session-handoff.md`）の続き。本セッションは「MetaMCP は必要か」という問いから始まり、MCP 設定の drift 解消まで完遂した。**次セッションは §3 の P1 に着手すること。**

---

## 📌 1. セッション概要

| 項目            | 内容                                                          |
| --------------- | ------------------------------------------------------------- |
| 📅 日付         | 2026-07-12（JST 11:37 終了 / 02:06Z 開始・約31分）            |
| 🎯 テーマ       | MetaMCP 要否判断 → MCP 設定 drift 解消                        |
| 🏗️ フェーズ     | maintenance / Monitor                                         |
| 🌿 作業ブランチ | `chore/cleanup-mcp-failed-entries`（PR#36・merged・削除済み） |
| 🔀 成果         | **PR#36 merged**（sha=`110cb8f`、`.mcp.json` のみ16行削除）   |

---

## ✅ 2. 完了・検証済み（VERIFIED）

### 🎉 MetaMCP 撤去 + MCP 設定 drift 解消（PR#36 MERGED）

- 🗑️ **MetaMCP 撤去**: user-scope `mirai-universal-mcp`（`http://localhost:12008/metamcp/MIrai-Universal-Mcp/mcp`）を `claude mcp remove -s user` で削除。長期 Failed to connect のまま放置、集約対象（serena/cipher/claude-context/codex/cph-lsp）は未使用だった。→ git 管理外（`~/.claude.json`）・完全可逆。
- 🧹 **project `.mcp.json` 掃除**: 壊れた `github`（存在しないパッケージ `@anthropic/mcp-server-github`）と失敗する `context7`（`CONTEXT7_API_KEY` 欠如）を削除。両者 plugin scope が代替。`memory`/`sequential-thinking` は温存（**後者は唯一定義のため削除するとツール喪失**）。
- 📊 **検証**: `claude mcp list` の Failed 件数 **3 → 0**。13サーバー全て ✔ Connected。CI(`catalog`)/CodeRabbit 両 pass、mergeable CLEAN。
- 📝 **Memory 保存**: `mcp-config-and-metamcp-decision.md`（判断根拠・再導入条件・scope 注意点）。
- 💡 **判断**: MetaMCP はこの単一 Claude Code 運用では**不要**。`deferred tools + ToolSearch` が集約を代替済み。autocompact thrashing の主因も MCP でなく CLAUDE.md 肥大（PR#35 で解決済み）だった。再導入は「複数クライアント共有／50+MCPガバナンス／serena等plugin非対応MCP」の要件が出た時のみ。

---

## 🚨 3. 次セッション最優先 — Monitor 分析が検出した P1（未着手）

> バックグラウンド Monitor ワークフロー（7 agent 並列・30候補→12選定・実コード裏取り済み）が検出。**MCP 掃除より深刻。** task output ID: `w437c7w9g`。

### ▶️ 第1PR（即効・高レバレッジ）: Rank2 + Rank1

- 🔒 **Rank2 [P1 security]** — HTTP サーバ既定 bind を `127.0.0.1` 化
  - 実測: `web/server.py:376` の `--host` 既定=`0.0.0.0`、`docker-compose.yml` の `ports:"49231:8080"` も全IF公開、`deploy/service.env` に `PUBLIC_HOST=192.168.0.185`。
  - 影響: #31 の Cloudflare Access（`mirai-const.co.jp` 限定）が、同一LANの任意端末から `http://192.168.0.185:49231` への平文HTTP直到達で**バイパス可能**。
  - 対策: app 既定を `127.0.0.1`（env `CATALOG_HOST`）、docker を `ports:"127.0.0.1:49231:8080"`（tunnel は localhost 接続で足りる）。**数行・即効**。
  - files: `web/server.py` / `docker-compose.yml` / `deploy/service.env`

- 🔴 **Rank1 [P1 data-integrity]** — `catalog_metadata.json` ドリフトを検証で塞ぎ再整合
  - 実測: metadata `verification_count=32`（実30）、`catalog_sha256=51c4c9d3…`（実 `2fa6648c…`）、`verification_sha256=f2a7d696…`（実 `add31223…`）で件数・両ハッシュとも不一致。
  - 原因: `scheduled-verify.yml`(weekly) が `run_verification`/`score_catalog` を `--write` するが metadata を再計算せず、`validate_catalog.py` に整合チェックが無いため **CI が緑のまま毎週ズレ拡大**。README「32件」も誤り。
  - 対策: (1) `validate_catalog.py` に record_count/verification_count/各sha256 の一致検証を追加、(2) metadata を実データから再生成 or weekly に再計算ステップ追加、(3) README を実30件へ訂正。
  - files: `data/catalog_metadata.json` / `data/verification_results.json` / `data/api_catalog.json` / `scripts/validate_catalog.py` / `scripts/export_markdown.py` / `.github/workflows/scheduled-verify.yml` / `README.md`
  - ⚠️ weekly CI 挙動に関わるため、再計算ステップ追加後は scheduled-verify の動作確認必須。

### 📦 推奨バッチ順（Monitor 統括 agent 提案）

1. **第1PR**: Rank2（bind・数行）+ Rank1（metadata 整合）← weekly ジョブの悪化を即停止
2. **テスト基盤**: Rank3→6→7→10（カバレッジ底上げ。現 TOTAL 43%）
3. **ガバナンス/運用**: Rank4（main ブランチ保護 — ⚠️ weekly bot の直push許可 or PR化と両立設計が必須）、Rank5（外形監視 — 工数最大・後追い可）
4. **docs/CI衛生**: Rank8（API リファレンス）、Rank12（validate.yml ハードニング）

### 📊 全 Rank 一覧（12件）

| Rank | P   | カテゴリ       | 要点                                                              |
| ---- | --- | -------------- | ----------------------------------------------------------------- |
| 1    | P1  | data-integrity | catalog_metadata ドリフト整合＋検証追加                           |
| 2    | P1  | security       | server.py bind `0.0.0.0`→`127.0.0.1`（Access バイパス）           |
| 3    | P1  | test-security  | server.py path-traversal(287-297/305-329)/ヘッダ統合テスト（41%） |
| 4    | P1  | security       | main ブランチ保護（現在 404 未保護）                              |
| 5    | P1  | operations     | 本番外形監視/アラート（検知がユーザー報告頼み）                   |
| 6    | P2  | test           | score_catalog テスト（0%/140文）                                  |
| 7    | P2  | test           | run_verification テスト（0%/80文）                                |
| 8    | P2  | api-docs       | JSON API リファレンス新設（実装との乖離明記）                     |
| 9    | P2  | ci             | カバレッジ閾値ゲート `--cov-fail-under`（tdd警告根絶）            |
| 10   | P2  | test-data      | import_production テスト（37%）                                   |
| 11   | P2  | refactor       | trust 二重実装単一化（catalog_utils↔score_catalog）               |
| 12   | P2  | ci-security    | validate.yml ハードニング（permissions/SHA-pin/SAST/secret-scan） |

---

## ⏳ 4. 未解決・保留

- 🔸 **pending_human_decision**: 5 stale branches 全て main の下位互換と判明（stale-branch-review agent 調査済み・cherry-pick 不要）。削除可否をユーザー確認中（2026-07-12T00:15 起票）。
- 🔸 **tdd_required 警告**: 31件・11回反復（主に ClaudeOS scaffold の hooks/workflows JS）。Rank3/6/7/10 のテスト整備で**アプリ本体**カバレッジは改善するが、scaffold JS の警告は `tdd-coverage-scan` の対象範囲見直しが別途要る可能性。

---

## 🖥️ 5. 環境メモ

- **MCP**: plugin(11: github/context7/playwright/chrome-devtools/microsoft-docs/neon/cloudflare×5) + user `memory` + project `sequential-thinking` のみ。`claude mcp list` Failed=0 を設定健全性シグナルに使える。
- **git**: main = `110cb8f`。作業ツリーに `state.json`/`.claude/START_PROMPT.md` の M と `snapshots`/`.coverage`/`agent-transcripts` の untracked あり（telemetry 系・commit 任意）。
- **セッション**: 5h 制限に余裕。`phase_mode=maintenance` / release_deadline `2026-12-18`（残 ~5ヶ月）。
