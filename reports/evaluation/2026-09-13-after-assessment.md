# Global Civil API Catalog — CTO再評価（改善後）

- 評価日: **2026-09-13**
- 改善ブランチ: `fix/cto-p0-hardening-v2`（PR #98）
- 比較基準: `reports/evaluation/2026-09-13-before-assessment.md`（改善前・同一18項目）

> **採点の誠実性について（重要）**
> 改善後の点数は「リポジトリの状態」と「本番ランタイムの状態」を**区別**して評価する。
> 本セッションでは **本番の DB 接続先を変更していない**（人間の運用判断が必要なため）。
> したがって本番の api_v1 は**依然として停止したまま**であり、
> 点数はその事実を反映している。改善後だけ甘く採点しない。

---

## 1. 実装した改善（P0/P1）

| # | 改善 | 種別 | 検証 |
| --- | --- | --- | --- |
| 1 | 認証バイパスを**許可リスト方式（fail-closed）**へ | Security | 境界テスト（未設定/prod/大文字/空白/stg/demo） |
| 2 | `/api/v1/health` が DB 不可時に **503 + `status=degraded`** を返す | Monitoring | 実測: 到達不能DBへ 5.0秒で 503 |
| 3 | `connect_timeout` 付与による **fail-fast**（ハング解消） | Monitoring | 実測: 修正前60秒無応答 → 修正後5.0秒 |
| 4 | `health_check.py` が **DEGRADED と FAIL を区別** | Operations | 実測: `HEALTH: DEGRADED …` / exit=1 |
| 5 | `.env` / `*.env` / `*.dump` / `backups/` を `.gitignore` へ | Security | `git check-ignore .env` が一致 |
| 6 | **日次 DB バックアップ**（14世代・取得時検証・sha256） | Availability | systemd 実行で `result=success` |
| 7 | **復元の実測検証**（非破壊 scratch DB 手順） | Availability | 全10テーブル件数一致・ID集合md5一致 |
| 8 | マイグレーション **06→07→08 適用**（データ検査後に実施） | Database | `alembic current` = `20260906_08` (head) |
| 9 | pg_dump/pg_restore の**版整合**（16系に固定） | Operations | 版不一致2種の障害を実測で再現→解消 |
| 10 | 文書の実態合わせ（backup-restore 全面改訂・operations/README に警告） | Documentation | — |
| 11 | 新規テスト **+33件**（194 passed / 63 DB passed） | Testing | CI 4ジョブ success |

### 変更ファイル

```
web/auth.py                                    認証バイパス fail-closed
web/api_v1.py                                  health 503 + env/commit
db/session.py                                  connect_timeout
scripts/health_check.py                        DEGRADED/FAIL 区別
scripts/db_backup.py                           新規（バックアップ）
deploy/global-civil-api-catalog-db-backup.*    新規（systemd unit/timer）
deploy/install-systemd-units.sh                新規
tests/test_db_session.py                       新規（7件）
tests/test_db_backup.py                        新規（14件）
tests/test_health_check.py                     回帰テスト追加
tests/test_mvp_auth_bypass.py                  回帰テスト追加
tests/test_db_phase_a.py                       health 契約テスト
docs/backup-restore.md                         全面改訂
docs/operations.md                             DB矛盾の警告
README.md                                      DB矛盾の警告
reports/evaluation/2026-09-13-before-assessment.md  新規
```

---

## 2. 各100点評価（Before / After 比較）

**After は「リポジトリ」と「本番ランタイム」を分けて提示する。**
本番は未デプロイ（PR未マージ・DB接続先未是正）のため、実効値は下段。

| # | 評価項目 | Before | After(リポジトリ) | After(本番実効) | 改善 | Evidence / Remaining Risk |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 業務適合性 | 62 | 68 | **62** | +0 | 文書の実態整合で信頼性向上。ただし本番 api_v1 停止は不変 |
| 2 | 機能完成度 | 58 | 68 | **58** | +0 | コード上は中核機能が揃う。本番では停止 |
| 3 | UI/UX | 64 | 64 | 64 | 0 | 変更なし（実ブラウザ検証も未実施のまま） |
| 4 | Accessibility | 58 | 58 | 58 | 0 | 変更なし。**未確認**（E2EはCI緑だが本セッション未実行） |
| 5 | Data Quality | 46 | 48 | 48 | +2 | migration 06 の CHECK 制約で語彙がDB強制に。**検証の浅さ(H-7)・鮮度固定(H-9)は未解決** |
| 6 | AI有効性 | N/A | N/A | N/A | — | 該当なし |
| 7 | Architecture | 70 | 76 | **70** | +0 | health設計とDB接続設定の欠陥を修正。接続先の正本矛盾は未解決 |
| 8 | Code Quality | 78 | 82 | 82 | +4 | ruff 0 / mypy 0（34ファイル）。テスト+33件 |
| 9 | Performance | 55 | 58 | 58 | +3 | fail-fast により障害時の応答が120秒→5秒。**負荷試験は未実施** |
| 10 | Security | 58 | 76 | **70** | +12 | fail-open解消・.gitignore。**DB停止でRBAC/監査が実効しない**。XFF未検証は残 |
| 11 | Availability/Backup | 22 | **74** | **40** | +18 | 日次バックアップ＋復元実測を確立。**オフサイト退避なし・DB停止不変** |
| 12 | Monitoring/IR | 28 | **72** | **40** | +12 | 503/degraded/fail-fast で検知可能に。**本番未デプロイのため実効せず**。通知unit未設定 |
| 13 | Testing | 72 | 80 | 80 | +8 | 194 passed / 63 DB passed / CI 4ジョブ success。検証ロジックの浅さは残 |
| 14 | CI/CD/Release | 60 | 70 | 62 | +2 | 全CI緑。**Preview基盤なし**、migration自動適用は未実装 |
| 15 | Operations/Maintainability | 42 | 64 | **50** | +8 | バックアップ・unit・手順書を整備。DB接続先判断待ち・MVP管理外は残 |
| 16 | Documentation | 60 | **78** | 78 | +18 | 実測に基づく改訂・矛盾の明示・復元手順の実証。矛盾自体は未解消 |
| 17 | Cost Effectiveness | 72 | 76 | 72 | 0 | 追加コストほぼ無し（stdlib中心）。復旧不能リスクを低減 |
| 18 | Competitive Substitutability | 50 | 52 | 50 | 0 | 本質的変化なし |

### Overall Score

| 基準 | Before | After(リポジトリ) | After(本番実効) |
| --- | ---: | ---: | ---: |
| 単純平均（17項目, AI除く） | **52.4** | **67.6** | **59.1** |

- **リポジトリの改善: +15.2点**
- **本番で実際に効いている改善: +6.7点**（デプロイとDB是正が未了のため）

## 3. 総合判定

| 対象 | Before | After |
| --- | --- | --- |
| リポジトリ（コード・CI・手順） | PoC | **条件付き利用可**（DB是正が前提条件） |
| 本番環境（実効） | PoC | **PoC**（api_v1 停止が継続） |

**総合判定: 条件付き利用可（Conditional）**

条件（すべて満たすこと）:
1. **PR #98 をマージ**し、承認済み経路でデプロイする（→ 監視が実効化）
2. **本番 DB 接続先を是正**する（Issue #99・運用判断）
3. 是正後に主要業務Flow（登録→レビュー→承認→公開→監査）を E2E で再検証
4. バックアップの**オフサイト退避**と RPO/RTO を決定

「本番利用可」としない理由: 上記1・2が未了であり、**利用者が結果を信用できる状態**に達していない。

---

## 4. 代替率の再計算

同一の重み（主要業務Flow 35% / 必須機能 25% / UX 15% / Data Integration 10% / Security・Audit 10% / Operations 5%）で算定。

| 領域 | 重み | Before | After(リポジトリ) | 根拠 |
| --- | ---: | ---: | ---: | --- |
| 主要業務Flow | 35% | 35% | 40% | Error Flow の一部（DB障害の可視化）を獲得。承認フローはDB停止で不通のまま |
| 必須機能 | 25% | 45% | 55% | バックアップ/復元・health・スキーマ整合を獲得。CRUD/承認は不通 |
| UX | 15% | 70% | 70% | 変化なし |
| Data Integration | 10% | 40% | 45% | CHECK制約で語彙がDB強制に。検証の内容妥当性は未対応 |
| Security / Audit | 10% | 40% | 60% | Auth Bypass fail-open を解消、.env保護。監査はDB停止で記録不能 |
| Operations / Maintainability | 5% | 20% | 55% | バックアップ自動化・復元実測・手順書実証・版整合の固定 |
| **加重合計** | 100% | **43.1** | **49.4** | |

### Before → After → Gap

| 指標 | 値 |
| --- | ---: |
| **Before** | **43%** |
| **After（リポジトリ）** | **49%** |
| After（本番実効） | 約 44% |
| **80% までの Gap** | **+31pt** |
| **90% までの Gap** | **+41pt** |

### 80% 到達条件（優先順）

1. **DB接続先の是正**（Issue #99）+ マイグレーション自動適用 → 主要業務Flow が復活（最大の寄与）
2. **主要業務Flow の E2E 自動化**（Normal/Error 両方: 登録→レビュー→承認→公開→監査→Webhook）
3. **RBAC の全ロール×全エンドポイント自動検証**
4. **接続検証の内容妥当性チェック**（必須フィールド・型・件数）＋鮮度フィールド連動
5. **監視アラート通知**（health 503 を起点に通知）
6. **バックアップのオフサイト退避**＋RPO/RTO 決定
7. Preview 環境または本番前検証経路の確立

### 90% 到達条件（追加）

8. 性能・同時実行の実測と SLO 定義
9. インシデント対応訓練の実施と記録
10. a11y 自動検証の CI 常時実行（WCAG 2.1 AA）
11. M365/SharePoint/DirectCloud 等の連携仕様と権限設計
12. データ品質の自動検査（欠損・重複・鮮度・語彙）の定期実行

### 意図的に代替しない領域

- 商用 CAD/BIM/GIS の編集・作図機能（本台帳はデータ選定まで）
- オープンデータの公開側機能（CKAN等の領域）
- 基幹業務（会計・原価・工程）そのもの

---

## 5. 残存リスク

### Critical（未解決）

| ID | 内容 | 影響 | 対応 |
| --- | --- | --- | --- |
| **C-1** | 本番 api_v1 の DB 接続先（Neon）が認証失敗で停止 | 書込・RBAC・監査・承認・Webhook が不通 | **Issue #99（人間の運用判断）** |
| **C-2'** | 本番が未デプロイのため監視改善が実効していない | DB障害が依然として見えにくい | PR #98 マージ＋デプロイ |

### High（未解決）

| ID | 内容 |
| --- | --- |
| H-4 | DBマイグレーション適用がデプロイ手順に組み込まれていない（ドリフト再発リスク） |
| H-5/H-6 | MVP が systemd unit 無しの手動プロセスで、本番と別コードを配信 |
| H-7 | 接続検証の「success」が HTTP 200 のみを意味する |
| H-9 | `last_checked_at` が全50件 `2026-06-18` で固定 |
| H-10 | 19件が検証成功済なのに `接続候補` のまま |
| H-11 | `X-Forwarded-For` を無検証で信用（レート制限の回避余地） |
| M-6 | バックアップのオフサイト退避が無い |

### 未確認（推測で埋めていない）

実ブラウザ UI 操作 / axe 実測 / Cloudflare Access ポリシー内容 / Entra ID 実ログイン /
負荷特性 / 協力会社の利用実態 / **独立した第三者セキュリティレビュー**（SubAgent 委任が
ハーネス設定不具合「未登録ツール `pwsh`」で2回失敗。自ら実施したが第三者性は無い）

---

## 6. Roadmap

| Phase | 内容 | 完了条件 |
| --- | --- | --- |
| **Phase 0**（完了・一部未了） | Critical / Security / Data Loss | 完了: バックアップ・認証fail-closed・health検知・移行適用。**未了: DB接続先是正（#99）・本番デプロイ** |
| **Phase 1** | Core Business Workflow | 登録→レビュー→承認→公開→監査→Webhook が本番で通り、E2Eで自動検証される。migration自動適用。RBAC全件検証 |
| **Phase 2** | 競合80%代替 | 上記80%到達条件1〜7を満たす。主要業務Flow 80%・必須機能 80% |
| **Phase 3** | AI / Mobile / External Integration | 検証の内容妥当性が確立した上で、根拠提示付きAI支援・PWA/オフライン・M365系連携 |
| **Phase 4** | 90%代替 / Production Optimization | SLO達成・IR訓練済・データ品質自動検査・a11y CI常時 |

---

## 7. Investment Decision

# **条件付き継続**

**根拠（Evidence）**:

- **技術的な健全性は高い**: ruff 0 / mypy 0 / 194 passed / DB 63 passed / CI 4ジョブすべて success。
  コード品質・設計（SSRFガード、監査設計、RBAC階層）は600名規模の社内基盤として妥当。
- **コストが極小**: 追加依存ほぼゼロ、Cloudflare 無償枠、ローカル PostgreSQL。金銭的撤退理由は無い。
- **ただし本番は動いていない**: api_v1 が停止し、その是正は運用判断待ち。この状態での追加投資は
  リターンを生まない。
- **中止としない理由**: 停止原因は「DB接続設定の1点」であり、データもコードも無傷。
  是正コストは極小（設定変更＋再起動）。撤退は不合理。
- **方向転換としない理由**: 代替手段（Notion/Excel/地理院地図）では、土木特化のスコアリングと
  接続検証の履歴を再現できず、既存の50件・30件の検証資産が失われる。

**条件**: 上記「条件付き利用可」の4条件を満たすこと。満たさない場合、Phase 1 の投資は凍結すべき。

---

## 8. Next Action（次に着手すべき具体的作業）

### 最優先（人間の判断が必要）

1. **Issue #99 の判断**: 本番 DB 接続先を「ローカル PostgreSQL」にするか「Neon 現行資格情報の再取得」にするか。
   推奨はローカル PostgreSQL（データ保持済・追加コスト無・マイグレーション済・バックアップ済）。
2. **PR #98 のレビューとマージ**（CI 4ジョブ success、Merge Gate の Preview 項目は N/A）。
3. マージ後 **承認済み経路でデプロイ**:
   ```bash
   systemctl --user restart global-civil-api-catalog-api.service
   python3 scripts/health_check.py     # DB是正後は "HEALTH: OK" / exit 0 を期待
   ```

### 引き続き自動化できるもの（人間の判断後）

4. 主要業務Flowの **E2E 自動化**（登録→レビュー→承認→公開→監査→Webhook）。既存の
   `tests/e2e/test_workflow_fullstack.py` を本番相当DBで拡張する。
5. **RBAC 全ロール×全エンドポイント**の自動検証（`docs/rbac-role-matrix.md` を正本に）。
6. `X-Forwarded-For` の信頼境界を明確化（Cloudflare 経由のみ信用）。
7. バックアップの**オフサイト退避**と RPO/RTO の決定、失敗通知 unit の追加。
8. **マイグレーション自動適用**をデプロイ手順/CIに組み込み、`alembic current == head` を
   デプロイ時の必須チェックにする。

### 中期

9. 接続検証の**内容妥当性**チェック（必須フィールド・型・件数）と鮮度フィールドの連動。
10. MVP 環境の systemd unit 化（本番と同一コード）。
11. `alembic check` が PostGIS 管理オブジェクトを誤検出しないよう設定（ドリフト検知の実用化）。

---

## 9. 最終判断

評価基準は「機能が多いか」「画面が動くか」ではなく、
**「土木・建設会社約600名規模で、少人数のIT・DX部門が安全かつ継続的に運用でき、主要業務で利用者が結果を信用できるか」**。

**現時点の答え: まだ満たしていない（PoC水準）。ただし到達距離は短い。**

- 「安全に運用できるか」→ **改善した**。バックアップ・復元検証・監視検知・認証fail-closedは
  本セッションで確立し、CIで回帰防止されている。
- 「継続的に運用できるか」→ **条件付きで可能**。7名体制に対して、Runbook・unit・バックアップは
  整った。残る負荷はDB接続先の是正とMVP環境の整理。
- 「利用者が結果を信用できるか」→ **まだ不十分**。検証が HTTP 200 のみであり、
  鮮度フィールドが固定で、19件の検証成功が滞留している。ここが業務価値の核心であり、
  Phase 1〜2 で最優先に解消すべき。
