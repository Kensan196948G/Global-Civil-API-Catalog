# Global Civil API Catalog — CTO総合評価（改善前 Baseline）

- 評価日: **2026-09-13**
- 評価者: Main Agent（CTO兼 実装・Release・運用責任者）
- 対象リビジョン: `origin/main` = `2856ad6`、作業ブランチ `fix/cto-p0-hardening-v2`
- 想定Organization: 従業員約600名 / IT・DX部門約7名 / 公共工事80%・民間20%
- 主要利用者: 現場・本社・経営層・協力会社

> **評価原則**: 確認できない事項を推測で補完しない。すべての点数に出典（コマンド出力・ファイル・実測値）を付す。
> 実測できなかったものは「未確認」と明記し、高得点を付けない。

---

## 1. Project概要

土木建設で使える国内外のAPI・公開データを台帳化し、接続検証・優先度評価・採用判断を行う**社内ナレッジ基盤**。

| 項目 | 内容 |
| --- | --- |
| 目的 | 「どの公開データが使えるか」を現場・本社・経営が迷わず判断する |
| 台帳データ | API 50件・接続検証 30件 |
| 主要機能 | 採用ダッシュボード / 適合度マップ / API台帳 / 地理空間ライブマップ / エクスポート / 採用候補比較 / OpenAPIインポート / マイタスク / Webhook通知 / 監査CSV / 印刷用帳票 |
| 構成 | `web/server.py`（stdlib Web UI + リバースプロキシ、:49231）＋ `web/api_v1.py`（FastAPI CRUD/RBAC/監査、:49232）＋ PostgreSQL/PostGIS |
| 公開 | Cloudflare Tunnel + Access（`api.mirai-dx-platform.com`） |
| 規模 | Python 約2,400行(web)＋2,500行(scripts)＋3,700行(tests)、静的アセット約3,100行 |
| CI | `validate`（ruff/mypy/pytest/pip-audit）・`e2e`（Playwright 2ジョブ）・`scheduled-verify`（週次） |

## 2. 想定User

| 利用者 | 主な用途 | 本評価での扱い |
| --- | --- | --- |
| 現場（施工管理・監督） | 気象・河川・防災・地図の確認 | **読取は動作**。DB停止のため「接続検証済」の鮮度保証なし |
| 本社（技術・設計） | 候補地評価・設計検討のデータ選定 | 読取可。ただし検証はHTTP 200のみ（§6 D-1） |
| 経営層 | 採用判断・投資判断 | エクスポート/帳票で可 |
| 協力会社 | データ参照 | **Cloudflare Access 保護のため未確認**（外向けUIは未検証） |
| IT・DX部門（7名） | 運用・データ更新・承認 | **書込層が停止**。運用負荷とRunbookに重大な穴（§6 O-1） |

## 3. 解決する課題 / Business Value

- **課題**: 公共データは省庁・自治体・海外機関に散在し、利用条件・更新頻度・接続可否が不明。後続システムの設計時に毎回調査が発生する。
- **Value**: 台帳＋検証＋スコアリングにより、データ選定の初動調査を標準化・再利用可能にする。
- **制約**: 台帳50件のうち**本格利用候補は3件のみ**（6%）。「探す」価値はあるが「これを使えばよい」という決定的な判断材料としてはまだ薄い。

## 4. 完成段階 / 運用段階

| 層 | 状態 | 根拠 |
| --- | --- | --- |
| 静的台帳＋Web UI 読取 | **稼働** | `curl http://127.0.0.1:49231/api/health` → 200 `{"status":"ok"}` |
| JSON/CSV/Markdown エクスポート | **稼働** | `python scripts/export_markdown.py` 成功 |
| DB＋CRUD＋RBAC＋監査（api_v1） | **停止** | `curl http://127.0.0.1:49232/api/v1/health` → `database: unavailable`（改善前）。`api.env` の接続先 Neon が認証失敗 |
| DBスキーマ | **ドリフト** | `alembic current` = `20260730_05`（head は `20260906_08`） |
| バックアップ | **不存在** | `backups/` 無し・unit 無し・timer 無し（実測） |
| 公開（本番） | **Access 保護で稼働** | `https://api.mirai-dx-platform.com/` → 302 → `cloudflareaccess.com` |
| 公開（MVP） | **稼働だが管理外** | systemd unit が無く、手動起動プロセス（PID 436081, `--port 18930`）が別コードを配信 |
| 入力側（書込）の業務利用 | **不可** | 上記 DB 停止により登録・更新・承認・監査が機能しない |

## 5. 各100点評価（改善前）

| # | 評価項目 | 点 | 根拠（実測） |
| --- | ---: | ---: | --- |
| 1 | 業務適合性 | **62** | 現場/技術/研究/IT の4読者別ガイドと用途別分類あり。ただし接続検証済は6件(12%)・本格利用候補3件(6%)に留まり、書込層停止で現場からの知見還元ができない |
| 2 | 機能完成度 | **58** | 画面11種・API 20超・ワークフロー5状態・Webhook・監査CSV・OpenAPI取込を実装。ただし**api_v1 が停止**しており、CRUD/RBAC/監査/承認という中核機能群が実運用で機能しない |
| 3 | UI/UX | **64** | 日本語UI・読者別ガイド・Mermaid図・PWAアイコン・スキップリンク・レスポンシブ。a11yテスト(`test_accessibility.py`)あり。ただし実ブラウザでの目視確認は本評価では未実施（**未確認**） |
| 4 | Accessibility | **58** | `tests/e2e/test_accessibility.py` と axe-core vendor 同梱を確認。ただし**本セッションではE2E未実行**（CI依存）。実測なしのため高得点不可 |
| 5 | Data Quality | **46** | 必須項目欠損0・ID重複0（良好）。一方 (a)`last_checked_at`が全50件で`2026-06-18`固定、(b)検証"success"は**HTTP 200のみ**で内容妥当性を見ない、(c)19件が検証成功済なのに`接続候補`のまま、(d)`official_url`重複8件。詳細§6 |
| 6 | AI有効性 | **N/A** | 本リポジトリにAI機能は実装されていない（`grep`で推論・LLM呼出なし）。**該当なし**。点数化しない |
| 7 | Architecture | **70** | stdlib層とFastAPI層の責務分離、`data/`正本＋DB併走(expand-and-contract)、SSRFガード、監査append-only設計は妥当。ただし**接続先の正本が文書と実環境で不一致**、DB層が停止 |
| 8 | Code Quality | **78** | `ruff` 0件、`mypy` 0件（33ファイル）、型注釈・docstring・日本語コメントが丁寧。`grep -n "select count"`系の安全なORM使用を確認 |
| 9 | Performance / Scalability | **55** | `grep`でN+1等の明白な問題は未検出、healthは`SELECT 1`。ただし負荷試験・レスポンス計測は**未実施**。台帳50件規模では問題化しにくいが、スケール根拠なし |
| 10 | Security | **58** | 良好: scrypt+timing equalize、ロックアウト、RS256固定、nonce、state+Dual Cookie、Origin検査、レート制限、SSRFのper-hop pin、security headers。**重大**: 認証バイパスが fail-open（§6 C-2）。`X-Forwarded-For`を無検証で信用（レート制限回避の余地） |
| 11 | Availability / Backup | **22** | **DBバックアップが皆無**。Neon PITRも死んでいる。復旧手順は文書にあるが未自動化・未検証。SPOF: DB・ホスト・手動起動のMVP |
| 12 | Monitoring / Incident Response | **28** | `health_check.py`はあるが**DB障害時に200を返すため機能していなかった**。`docs/monitoring.md`はあるがアラート通知unit無し。インシデント手順は文書のみ |
| 13 | Testing | **72** | 非DB 147件＋DB 59件が green。DBテストをCIのPostgreSQLで実行する構成は良好。E2EもCIジョブあり。ただし検証ロジック自体が浅い(§6 D-1)、カバレッジ計測なし、E2Eは本評価で未実行 |
| 14 | CI/CD / Release | **60** | 3ワークフロー（validate/e2e/scheduled-verify）、Required Checks、週次でPR自動作成、pip-audit。ただし**DBマイグレーション適用がCI/デプロイに組み込まれておらず**、今回のドリフトを招いた。PRプレビュー環境なし |
| 15 | Operations / Maintainability | **42** | 運用文書は充実。しかし (a)DB停止が監視で検知不能だった、(b)バックアップ皆無、(c)MVPがunit無しの手動プロセス、(d)接続先の文書不一致。7名で安全に運用できる状態ではない |
| 16 | Documentation | **60** | 要件定義書・詳細仕様設計書・運用・監視・バックアップ・RBAC・a11y と量は十分。ただし**Neon前提の記述が実環境と矛盾**、`last_checked_at`等の実データ乖離 |
| 17 | Cost Effectiveness | **72** | 追加依存ほぼゼロ（stdlib中心）、Cloudflare無償枠、ローカルPostgreSQL。金銭コストは極小。ただし監視・バックアップ欠如による**機会損失/復旧不能リスク**がコストを相殺 |
| 18 | Competitive Substitutability | **50** | 単独の代替製品は存在しない（自社固有の台帳）。ただし汎用代替（Notion/Excel/Airtable＋GISサイト巡回）で**かなり代替可能**。詳細§7 |

### Overall Score（改善前）

- **単純平均（AI有効性を除く17項目）: 890 / 1700 = 52.4点**
- **重み付き（業務適合性・機能完成度・Security・Availability を重視した主観重み）: 約 50点**

## 6. 総合判定（改善前）

# **PoC**（本番利用不可）

**理由**: 中核の DB 層が停止し、書込・RBAC・監査・承認が機能していない。かつその停止を監視が検知できず、
バックアップも存在しない。画面は動くが「利用者が結果を信用できるか」を満たさない。

「条件付き利用可」としない根拠: 条件付き利用可は「明示的リスク受容の上で限定利用可」を意味するが、
**Data Loss リスクが未対策**（バックアップ皆無）であり、受容可能な水準にない。

---

## 7. 強み（15件以上）

1. **読者別ガイド**（非エンジニア/現場/技術者/研究者/IT運用）を README に用意し、各層の判断導線が明確。
2. **読取層は無停止**。`data/*.json` 正本により、DB が落ちても台帳閲覧・エクスポートは継続した（実際に今回の障害下で機能）。
3. **SSRFガードの実装品質が高い**（`scripts/url_guard.py`）。per-hop で resolve→validate→**TCP接続を検証済IPへピン留め**、DNS rebinding を封じ、userinfo・非http scheme・private/loopback/CGNAT を拒否。
4. **認証の基礎が堅い**（`web/auth.py`）: scrypt(N=2^14)・timing equalize用ダミーハッシュ・5回失敗15分ロック・JWT RS256固定・nonce検証・state＋専用Cookieで login-CSRF 対策。
5. **監査の設計が正しい**: append-only `audit_log`、変更理由(reason)必須、版スナップショット、復元はAdmin限定＋監査記録。
6. **RBAC/ABAC がロールマトリクスとして文書化**（`docs/rbac-role-matrix.md`）。
7. **ワークフローが実務的**: draft→submit→review_ok→approve→published と send_back、公開読取は published のみ。
8. **エクスポートが多形式**（Markdown/CSV/JSON/帳票HTML）で会議資料・監査資料に直結。
9. **静的解析がCIで強制**: ruff・mypy が 0 件を維持。
10. **DBテストをCIのPostgreSQL/PostGISで実行**する構成（`db-api` ジョブ）。PostGIS拡張有効化まで含む。
11. **E2Eを2層で用意**: 読取専用UI（demoデータ）とフルスタック（DB＋webhook echo）。CIで実行される。
12. **週次検証の自動PR化**（`scheduled-verify.yml`）＋failure時の自動Issue化。データ鮮度維持の仕組みがある。
13. **本番がCloudflare Accessで保護**（実測302→cloudflareaccess.com）。無認証で外に出ていない。
14. **依存が極小**（`dependencies = []`、DB層のみ optional extra）。攻撃面と運用負荷が小さい。
15. **文書量が豊富**: 要件定義書30KB・詳細仕様設計書29KB＋運用/監視/バックアップ/RBAC/a11y。
16. **マイグレーションが段階的で意味のある単位**（6本＋今回の2本）。rollback関数も実装。
17. **データに必須項目欠損が無い**（50件すべてで region/status/license/api_key_required/trust_rank/score が充足）。
18. **判断の根拠が説明可能**: `score_breakdown` に加点要因を文字列で保持（例:「提供元種別(government) +30」）。
19. **テストが日本語docstringで意図を説明**しており保守しやすい。

## 8. 弱み / Risk（15件以上・Severity分類）

### Critical

| ID | 症状 | 根拠 |
| --- | --- | --- |
| **C-1** | **本番DBが認証失敗で停止**。api_v1 の CRUD・RBAC・監査・承認が全滅 | `api.env` の接続先は Neon。実測 `password authentication failed for user 'neondb_owner'`。`/api/v1/health` → `database: unavailable` |
| **C-2** | **DB障害を監視が検知できない**（fail-open health） | 改善前 `/api/v1/health` が DB不可でも **200 + `status:ok`** を返却。`health_check.py`・監視・Runbook が全て成功と誤認 |
| **C-3** | **DBバックアップが一切存在しない**（Data Loss） | `backups/` 無し・systemd unit 無し・timer 無しを実測。Neon PITR も停止。復旧不能 |
| **C-4** | **スキーマドリフト**: 本番DBに2マイグレーション未適用 | `alembic current`=`20260730_05` に対し head=`20260906_08`。DB依存テストが35件失敗（`column catalog_entries.owner does not exist`） |
| **C-5** | **`CATALOG_ENV` が設定されていない**ため、認証バイパスの安全装置が機能しない | api.service に `CATALOG_ENV` なし。`CATALOG_AUTH_BYPASS=true` を設定すると**どの値でも認証が無効化**される（fail-open） |

### High

| ID | 症状 | 根拠 |
| --- | --- | --- |
| **H-1** | 認証バイパスが拒否リスト方式で fail-open | `web/auth.py`: `return os.environ.get("CATALOG_ENV","").strip().lower() != "production"`。未設定/`prod`/`Production`/空白/`stg` で有効化 |
| **H-2** | health probe が到達不能DBで**ハング**する | `connect_timeout` 未設定。実測: 60秒待っても応答なし（OS既定≒120秒/アドレス） |
| **H-3** | `.env`（実Credential）が `.gitignore` に入っていない | `git check-ignore .env` が exit 1。リポジトリ直下にDBパスワードを含む `.env` が存在（未追跡。履歴混入は無しと確認） |
| **H-4** | **DBマイグレーション適用がデプロイ手順に無い** | 手動運用。CIは`upgrade head`するが本番反映経路が無く、C-4 を招いた |
| **H-5** | MVP環境が **systemd unit 無しの手動起動プロセス** | PID 436081 `web/server.py --port 18930` が `127.0.0.1:18930` を listen。親PID=1（孤児）。自動再起動なし。再起動で消失 |
| **H-6** | MVPが本番と**別コード**を配信 | `auth/me`→404（本番は200/401系）。検証環境として本番と等価でない |
| **H-7** | 接続検証の「success」が**HTTP 200のみ**を意味する | `scripts/run_verification.py`。payload の妥当性・必須フィールド・件数を見ない。`record_count` は多くが null |
| **H-8** | 接続先の**正本が文書と実環境で矛盾** | README/`docs/operations.md` は Neon 前提。実環境はローカルPostgreSQL。`.env` はローカル、`api.env` は Neo |
| **H-9** | `last_checked_at` が全50件 `2026-06-18` で固定 | 検証実行と連動していない。利用者は「いつ確認したか」を誤認する |
| **H-10** | 19件が検証成功済なのに `接続候補` のまま | 検証(30件 success 29/warning 1) とステータスが連動していない。運用滞留 |
| **H-11** | `X-Forwarded-For` を無検証で信用しレート制限のキーに使用 | `web/api_v1.py:_client_ip()`。ヘッダ偽装でログイン試行のレート制限を回避可能（アカウントロックは残る） |

### Medium

| ID | 症状 | 根拠 |
| --- | --- | --- |
| M-1 | `alembic check` が常に失敗（PostGIS管理オブジェクトをモデルが持たない） | `spatial_ref_sys`/`geom` を「削除」と誤検出。ドリフト検知が使えない |
| M-2 | 期限切れセッションの定期掃除が起動時に限られる | `purge_expired_sessions` は lifespan で1回のみ。長期稼働でゴミが残る |
| M-3 | `official_url` が8件重複 | 同一ポータルに複数エントリ（例 `nlftp.mlit.go.jp/ksj/` に11件）。利用者の識別性が低い |
| M-4 | `api_key_required` が10件 `unknown` | 採用判断に必要な情報が未確定 |
| M-5 | license_note が曖昧なものが6件（「提供元の利用条件を確認する。」） | 公共工事での二次利用判断に使えない |
| M-6 | バックアップのオフサイト退避が無い | 改善後も同一ホスト内。ホスト障害で全損 |
| M-7 | バックアップ失敗の通知が無い | systemd failed と journal のみ |
| M-8 | E2Eが本評価で未実行 | CI依存。ローカルにはPlaywrightブラウザ未導入 |
| M-9 | `web/server.py` の `/api/health` はDBを見ない | WebUI層の監視は別系統。二重の真実 |
| M-10 | 週次検証が外部APIの可用性に依存し、失敗時の扱いが薄い | `result=failure` 時の通知・エスカレーション手順が未整備 |
| M-11 | 負荷・性能の実測が無い | 同時実行数・レスポンスタイムの根拠なし |
| M-12 | カバレッジ計測が無い | `.coverage` はあるがCIで閾値なし |
| M-13 | `not_required` 38件 / `required` 2件のみで、認証必要APIの検証が手薄 | `run_verification.py` は api_key 必要なら skip/warning |

### Low

| ID | 症状 |
| --- | --- |
| L-1 | ルートに17MBの `web/Global Civil API Catalog.html`（デザイン原本）が同居 |
| L-2 | `global_civil_api_catalog.egg-info/` が作業ツリーに残存 |
| L-3 | 週次PRブランチが蓄積（`chore/weekly-verification-*`） |
| L-4 | `scripts/backup_catalog.py` のdocstringが「Neon PITR」を前提とした旧記述 |
| L-5 | `.env` がリポジトリ直下にあり、正規の置き場所（`~/.config/.../api.env`）と二重 |
| L-6 | `docs/EntraID-info.txt` が gitignore されているがファイル自体は存在（情報の置き場として曖昧） |
| L-7 | 停止済み `cloudflared-backup.service` が failed のまま |
| L-8 | 未マージの古いブランチが20本以上 |
| L-9 | PRテンプレートが無い（本PRで記載形式を提示） |
| L-10 | `reports/agent-transcripts/` に作業ログが蓄積（ツール生成物） |

---

## 9. Risk Priority（最優先で潰すべきもの）

`Data Loss / 誤判定 / 計算Error / Permission逸脱 / Auth Bypass / 情報漏洩 / Audit不足 / Migration Failure / Backup不能 / Restore不能 / 運用停止 / SPOF / Critical Security / Major Workflow Failure`

| 優先 | 該当 | 状態 |
| --- | --- | --- |
| P0 | Data Loss（C-3）・Backup不能（C-3）・Restore不能（C-3） | **本セッションで修正・検証済み** |
| P0 | Auth Bypass（C-5/H-1） | **修正済み（fail-closed）** |
| P0 | 運用停止（C-1）・監視不能（C-2） | **検知は改善**。接続先の是正は**未解決（要判断）** |
| P0 | Migration Failure（C-4） | **適用済み（head到達・データ検査済み）** |
| P1 | Audit不足・Permission逸脱 | DB停止に起因。接続先是正後に再検証が必要 |
| P1 | SPOF（DB/ホスト/MVP手動プロセス） | **未解決** |
| P2 | 誤判定（H-7 検証が浅い／H-9 鮮度誤認） | **未解決** |

---

## 10. 競合 / OSS比較

| 比較対象 | 種別 | 主機能 | 対象利用者 | 配備 | 連携 | AI | Security | UX | Cost | 運用 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **本Project** | 自社台帳 | API台帳＋接続検証＋スコア＋承認WF＋監査 | 現場/本社/経営/協力会社 | 自社Linux＋Cloudflare | REST/Webhook | なし | Cloudflare Access＋RBAC | 日本語UI | 極小 | 7名（要改善） |
| **CKAN** | OSS | オープンデータポータル（データセット公開・検索・API） | 自治体・組織のデータ公開側 | 自前ホスト/K8s | 豊富なAPI拡張 | 一部 | プラグイン依存 | 汎用・英語中心 | 中（運用要員） | 専任要 |
| **DKAN** | OSS | CKAN系（Drupal基盤） | 政府・自治体 | 自前ホスト | Drupal連携 | なし | Drupal準拠 | 汎用 | 中 | 専任要 |
| **data.go.jp / e-Gov データポータル** | 公的 | 政府オープンデータカタログ | 国民・事業者 | 公的クラウド | 検索API | なし | 公的基準 | 汎用 | 無償 | 公的運用 |
| **地理院地図 / ハザードマップポータル** | 公的 | 地図・ハザード閲覧 | 国民・技術者 | 公的 | タイル | なし | 公的基準 | 用途特化 | 無償 | 公的運用 |
| **Notion / Airtable / Excel＋SharePoint** | 商用 | 表・DB・ワークフロー | 全社 | SaaS | 豊富 | あり | ベンダ依存 | 高 | 月額 | 不要 |

### 可替可能範囲 / 代替不可能範囲

- **可替**: 台帳の一覧・検索・分類・エクスポート・簡易な承認フロー → Notion/Airtable/SharePoint リストで**十分代替可能**。
- **可替**: 地図・ハザード情報の閲覧 → 地理院地図・ハザードマップポータルで**より高品質に代替可能**。
- **代替困難**: **土木業務に特化したスコアリング（business_fit / integration / trust / priority の4軸と加点根拠）**、および**接続検証の実行と履歴**。汎用ツールでは作れない（作るなら結局同じ開発）。
- **代替困難**: 自社の利用条件判断（公共工事での二次利用可否）を台帳に紐付ける運用。

### 本Project独自優位性

1. 土木・公共工事の文脈に合わせた4軸スコアと加点理由の明示。
2. 接続検証（実HTTP）を台帳に統合し、放置された候補を炙り出せる。
3. 日本語の読者別ガイドと、公共工事の利用条件記載。

---

## 11. 代替率（改善前）

重み: 主要業務Flow 35% / 必須機能 25% / UX 15% / Data Integration 10% / Security・Audit 10% / Operations 5%

「機能が存在するだけでは covered としない」。**Normal Flow・Error Flow・Tests・RBAC・Audit Log・Backup/Recovery・Operation Procedure が揃って初めて完全カバー**とする。

| 領域 | 重み | 達成度 | 加重 | 判定根拠 |
| --- | ---: | ---: | ---: | --- |
| 主要業務Flow | 35% | 35% | 12.3 | 「探す→見る→出力する」は稼働。**「登録→レビュー→承認→公開」がDB停止で不通**。Error Flow 未検証 |
| 必須機能 | 25% | 45% | 11.3 | 一覧・検索・分類・出力・地図は可。CRUD・承認・監査・Webhook は停止 |
| UX | 15% | 70% | 10.5 | 日本語UI・読者別導線・PWA・a11y配慮。実ブラウザ検証は未実施 |
| Data Integration | 10% | 40% | 4.0 | 検証はHTTP 200のみ。`record_count` 欠落多数。鮮度フィールドが固定。OpenAPI取込は実装済 |
| Security / Audit | 10% | 40% | 4.0 | 設計は良好だが **Auth Bypass fail-open**（修正済）と**監査がDB停止で記録不能** |
| Operations / Maintainability | 5% | 20% | 1.0 | Documentation は厚いが、バックアップ皆無・監視不能・MVP管理外 |
| **合計** | 100% | — | **43.1** | |

### 現在代替率（改善前）: **43%**

### 80% 到達条件

1. DB層の復旧（接続先是正）＋ マイグレーション自動適用（C-1/C-4）
2. バックアップ＋**復元実測**＋オフサイト退避（C-3）
3. 監視・アラートの実働（health 503化＋通知）（C-2）
4. 主要業務Flow（登録→レビュー→承認→公開→監査）の **E2E自動テスト**（Normal/Error 両方）
5. RBAC の全ロール×全エンドポイント検証の自動化
6. 接続検証を「内容妥当性」まで拡張（H-7）＋鮮度フィールドの連動（H-9）
7. 運用手順（Runbook）の実測化と訓練

### 90% 到達条件

上記に加え:
8. 性能・同時実行の実測とSLO定義
9. インシデント対応（検知→通知→切り分け→復旧）の訓練実施と記録
10. a11y の自動検証をCIで常時実行（WCAG 2.1 AA）
11. 外部システム連携（SharePoint/Teams/DirectCloud 等）の正式な接続仕様と監視
12. データ品質の自動検査（欠損・重複・鮮度・語彙）を定期実行し、劣化を検知

### 意図的に代替しない領域

- 商用GIS/CAD/BIM製品（AutoCAD Civil 3D, ArcGIS 等）の**編集・作図機能**。本台帳は「データソースの選定」までが責務。
- CKAN 等が担う**オープンデータの公開側**機能（本件は消費側）。
- 基幹業務システム（会計・原価・工程）そのもの。

---

## 12. 改善計画（分類と優先度）

| 分類 | # | Problem | Target | Benefit | 難易度 | Effort | Priority | Dependency | Risk | Completion Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **今すぐ** | 1 | 認証バイパス fail-open (C-5/H-1) | IT運用 | 認証の意図せぬ無効化を防止 | 低 | 小 | **P0** | なし | デモ環境の設定漏れで閲覧不可 | 許可リスト化＋境界テスト ✅**完了** |
| 今すぐ | 2 | health の fail-open (C-2) | IT運用 | DB障害の可視化 | 低 | 小 | **P0** | なし | 監視が503を異常扱いするか要確認 | 503+degraded＋実測 ✅**完了** |
| 今すぐ | 3 | connect_timeout 欠落 (H-2) | IT運用 | 監視のハング解消 | 低 | 小 | **P0** | #2 | 遅いWAN接続で誤検知 | 5秒でfail-fast ✅**完了** |
| 今すぐ | 4 | DBバックアップ皆無 (C-3) | IT運用 | Data Loss回避 | 中 | 中 | **P0** | なし | ディスク消費 | 日次＋復元実測 ✅**完了** |
| 今すぐ | 5 | `.env` が gitignore 外 (H-3) | 全員 | Credential漏洩防止 | 低 | 小 | **P0** | なし | なし | ignore追加 ✅**完了** |
| 今すぐ | 6 | マイグレーション未適用 (C-4) | IT運用 | 中核機能の復旧 | 中 | 小 | **P0** | DB接続先 | 破壊的DDL | head到達＋データ検査 ✅**完了** |
| **今すぐ（残）** | 7 | **DB接続先が停止 (C-1)** | 全員 | api_v1復旧 | 低 | 小 | **P0** | **人間の運用判断** | 接続先の誤選択 | ローカルPGかNeon現行Credの選択 |
| 今すぐ（残） | 8 | MVPが管理外プロセス (H-5/H-6) | IT運用 | 検証環境の安定 | 中 | 中 | **P1** | なし | 本番との差分 | systemd unit化＋本番と同一コード |
| 3か月以内 | 9 | 検証がHTTP 200のみ (H-7) | 技術者 | 結果の信頼性 | 中 | 中 | **P1** | なし | 誤検知で候補を除外 | 必須フィールド・件数・スキーマ検証 |
| 3か月以内 | 10 | 鮮度フィールド固定 (H-9) | 全員 | 誤認防止 | 低 | 小 | **P1** | #9 | なし | 検証実行と連動 |
| 3か月以内 | 11 | ステータス連動なし (H-10) | 本社 | 運用滞留の解消 | 低 | 小 | **P2** | #9 | 誤昇格 | 自動昇格ルール＋レビュー |
| 3か月以内 | 12 | 監視・アラート通知なし (M-7) | IT運用 | 一次検知 | 中 | 中 | **P1** | #2 | 通知疲れ | 通知unit＋閾値 |
| 3か月以内 | 13 | `X-Forwarded-For` 無検証 (H-11) | IT運用 | レート制限の実効性 | 低 | 小 | **P1** | なし | プロキシ構成依存 | 信頼プロキシのみ信用 |
| 3か月以内 | 14 | マイグレーションが手動 (H-4) | IT運用 | ドリフト防止 | 中 | 中 | **P1** | #7 | 自動適用の失敗 | デプロイ手順に組込＋検証 |
| 3か月以内 | 15 | オフサイト退避なし (M-6) | IT運用 | ホスト障害耐性 | 中 | 中 | **P1** | #4 | コスト | 外部退避＋RPO/RTO決定 |
| 3か月以内 | 16 | E2Eが本評価で未実行 (M-8) | QA | 回帰検知 | 低 | 小 | **P2** | なし | フレーク | ローカル実行手順確立 |
| 3か月以内 | 17 | `alembic check` 不能 (M-1) | 開発 | ドリフト検知 | 中 | 中 | **P2** | なし | 誤検知 | PostGIS除外設定 |
| 6〜12か月 | 18 | 性能・SLO未定義 (M-11) | IT運用 | 容量計画 | 中 | 中 | **P2** | #7 | なし | 負荷試験＋SLO文書 |
| 6〜12か月 | 19 | カバレッジ閾値なし (M-12) | 開発 | 品質維持 | 低 | 小 | **P3** | なし | 形骸化 | CI閾値設定 |
| 6〜12か月 | 20 | データ品質の自動検査なし (M-3/4/5) | Data Quality | 判断の信頼性 | 中 | 中 | **P2** | #9 | 誤警告 | 定期検査＋レポート |
| 6〜12か月 | 21 | 外部連携（M365/SharePoint/DirectCloud）未実装 | 全社 | 業務組込 | 高 | 大 | **P3** | #7 | 権限設計 | 連携仕様＋RBAC |
| 6〜12か月 | 22 | a11y CI常時実行なし (M-8関連) | 全員 | 法令・公平性 | 低 | 小 | **P2** | なし | フレーク | axe をCIに組込 |
| 将来 | 23 | 承認フローの協力会社連携 | 協力会社 | サプライチェーン | 高 | 大 | **P3** | #21 | 権限逸脱 | 外部主体RBAC設計 |
| 将来 | 24 | AIによるデータ推薦・要約 | 全員 | 探索効率 | 中 | 中 | **P3** | #9 | 誤情報・幻覚 | Eval＋根拠提示＋Kill switch |
| 将来 | 25 | オフライン/PWA強化 | 現場 | 現場利用 | 中 | 中 | **P3** | なし | データ整合 | オフライン設計＋同期 |

---

## 13. 追加機能候補（20件以上）

| # | 分類 | 候補 | Benefit | Target | 難易度 | Priority | Differentiation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Data Quality | 検証の内容妥当性チェック（必須フィールド・型・件数・単位） | 「使える」の定義を実質化 | 技術者 | 中 | **高** | 高（他に無い） |
| 2 | Data Quality | データ品質ダッシュボード（欠損/重複/鮮度/語彙逸脱） | 劣化の一次検知 | IT/本社 | 中 | 高 | 中 |
| 3 | Data Quality | 出典・ライセンス・商用可否の構造化（SPDX/利用約款リンク） | 公共工事での二次利用判断 | 本社 | 中 | 高 | 高 |
| 4 | Business | 業務シナリオ別バンドル（例: 河川工事に必要なデータ一式） | 現場の即時利用 | 現場 | 中 | 高 | 高 |
| 5 | Business | 採用判断の記録（なぜ採用/不採用か）と検索 | 属人化防止 | 本社 | 低 | 中 | 中 |
| 6 | Map/GIS | 台帳APIの地図上プレビュー（範囲選択で利用可能データを提示） | 候補地評価の高速化 | 技術者 | 高 | 中 | 高 |
| 7 | Map/GIS | ハザード重ね合わせのプリセット（洪水/土砂/津波） | リスク判定 | 現場/技術 | 中 | 高 | 高 |
| 8 | Search | 自然文検索（「盛土の品質管理に使えるデータ」） | 探索効率 | 全員 | 中 | 中 | 中（AI要） |
| 9 | Search | 類義語・表記揺れ辞書（河川/水系、標高/DEM） | 検索漏れ削減 | 全員 | 低 | 中 | 低 |
| 10 | Visualization | カテゴリ×案件種別のヒートマップ | 採用傾向の把握 | 経営 | 低 | 低 | 低 |
| 11 | Visualization | 検証結果の時系列推移（成功率・応答時間） | 品質監視 | IT | 中 | 中 | 中 |
| 12 | PWA | インストール可能化＋オフライン台帳 | 現場の電波不良対応 | 現場 | 中 | 中 | 中 |
| 13 | Offline | Service Worker キャッシュと同期 | 同上 | 現場 | 中 | 中 | 中 |
| 14 | Notification | 検証失敗・鮮度切れのメール/Teams通知 | 一次検知 | IT | 低 | **高** | 低 |
| 15 | Notification | 承認待ちの滞留アラート | 滞留解消 | 本社 | 低 | 中 | 低 |
| 16 | PDF | 帳票のサーバサイドPDF生成（ブラウザ印刷依存の解消） | 安定した配布 | 全員 | 中 | 中 | 低 |
| 17 | Excel | 条件付き書式付きExcel出力（スコア可視化） | 現場での加工 | 現場 | 低 | 中 | 低 |
| 18 | API | 公開APIのレート制限・APIキー発行 | 後続システム連携 | IT | 中 | 中 | 中 |
| 19 | API | OpenAPI仕様の自動生成・公開 | 連携開発の効率 | IT | 低 | 中 | 中 |
| 20 | RBAC | プロジェクト別のアクセス制御（案件単位） | 公共工事の情報統制 | 本社 | 高 | 中 | 高 |
| 21 | Audit | 監査ログの改竄検知（ハッシュチェーン） | 内部統制 | 経営/監査 | 中 | 中 | 高 |
| 22 | Audit | 監査ログの長期保管・外部転送 | 法令対応 | IT | 中 | 中 | 中 |
| 23 | Administration | 管理画面（ユーザー・ロール・Webhook管理のUI化） | 運用負荷削減 | IT | 中 | 中 | 低 |
| 24 | Administration | セルフサービス・パスワードリセット | 問合せ削減 | 全員 | 低 | 中 | 低 |
| 25 | Operations | バックアップ・復元の自動検証（月次） | Restore保証 | IT | 中 | **高** | 中 |
| 26 | Operations | Terraform/Ansibleによる構成管理 | 再現性 | IT | 高 | 低 | 低 |
| 27 | Civil Engineering | 出来形・品質管理基準との紐付け | 公共工事の実務直結 | 現場 | 高 | 中 | 高 |
| 28 | Civil Engineering | 数量計算・積算に使えるデータの識別 | 積算支援 | 本社 | 高 | 中 | 高 |
| 29 | Construction | 施工計画（4D工程）への接続 | 工程検討 | 技術 | 高 | 低 | 中 |
| 30 | AI | 利用条件の要約＋根拠引用（ライセンス読解支援） | 判断支援 | 本社 | 中 | 中 | 高 |
| 31 | AI | 類似データ推薦（採用済みとの類似） | 探索効率 | 全員 | 中 | 中 | 中 |
| 32 | AI | 変更検知サマリ（規約・エンドポイント変更の要約） | 保守の省力化 | IT | 中 | 中 | 中 |

### MVP / Production Risk / ROI による実装対象の絞り込み

**20件すべてを即実装しない。** 判断基準:

- 実装する（P0/P1）: **#1, #2, #14, #25**（信頼性・Data Loss・一次検知に直結）
- 次点（P2, 3か月）: #3, #4, #7, #11, #21, #23
- 保留（P3）: AI系（#8, #30, #31, #32）は **#1の検証基盤が整うまで着手しない**。
  AIチャットの追加自体を目的化しない。根拠提示・Eval・Kill switch の設計が先。
- 保留: #6, #20, #26, #27, #28, #29 は既存の CAD/BIM/GIS プロジェクトとの重複が懸念されるため、
  全体アーキテクチャの整理後に判断。

---

## 14. AI評価

**本リポジトリにAI機能は実装されていない**（`grep` でLLM・推論・埋め込みの呼出を検出せず）。
したがって AI有効性 は点数化しない（N/A）。

Rule / DB Search で十分な領域（**AIを使うべきでない**）:
- 一覧・絞込・カテゴリ分類・スコア計算・ライセンス有無の表示 → 既に決定論的で説明可能。AI化は退行。

AIが価値を持つ可能性がある領域（**導入するなら設計条件付き**）:
- 利用規約・約款の要点抽出（根拠条文の引用必須）
- エンドポイント変更の差分要約
- 自然文からの候補推薦（**推薦理由と出典の提示必須**）

AI設計確認（導入する場合に必須）:
RAG / Extraction / Classification / Prediction / Anomaly Detection / **Evidence・Citation** /
**Confidence** / **Human Approval** / Authorization / Prompt Injection 対策 /
Confidential Data の扱い / **Input・Output Audit** / Model Audit / 責任分界 /
**Usage Limit** / **Kill Switch**

→ 現時点では**未実装・未設計**。導入は Phase 3 以降、上記が揃ってから。

---

## 15. 停止 / Escalation 事項（人間の判断が必要）

| 項目 | Reason | Impact | Completed Work | Required Action | Required Approval | Recommended Approach | Resume Procedure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **本番DB接続先の是正（C-1）** | 正本がREADME(Neon)と実環境(ローカルPG)で矛盾。どちらを正とするかは業務判断 | api_v1（書込/RBAC/監査）が停止継続 | 検知改善・バックアップ・マイグレーション適用は完了 | ローカルPG採用かNeon資格情報再取得の決定 | **運用責任者** | ローカルPG（データ保持済・追加コスト無）を正とし、README/operations を更新 | `api.env` 更新 → `systemctl --user restart global-civil-api-catalog-api` → `health_check.py` でOK確認 |
| MVP環境の unit 化（H-5/H-6） | 手動起動プロセスの停止・再作成は現行MVP視聴者に影響 | MVP一時停止 | 現状把握・PID特定 | 停止可否の判断 | 運用責任者 | systemd unit 化して本番と同一コードを配信 | unit 作成 → 旧プロセス停止 → 起動確認 |
| オフサイト退避・RPO/RTO（M-6） | 保存先・予算・保持期間は組織判断 | ホスト障害で全損 | 日次バックアップ実装済 | 保存先と目標の決定 | **IT/DX 責任者** | 既存の他プロジェクトと同じ運用に合わせる | `CATALOG_BACKUP_DIR` 変更＋timer再登録 |
| Production Data 削除 | 破壊的操作 | 復旧困難 | — | 明示承認 | 運用責任者 | 実施しない | — |

---

## 16. 未確認事項（推測で埋めていない）

| # | 未確認 | 理由 |
| --- | --- | --- |
| 1 | 実ブラウザでのUI目視・操作 | Playwrightブラウザが本環境に無く、E2EはCI依存。**本セッション未実行** |
| 2 | Accessibility の実測スコア（axe実行結果） | 同上 |
| 3 | Cloudflare Access のポリシー内容（誰が入れるか） | ダッシュボード未確認。302リダイレクトのみ実測 |
| 4 | Entra ID OIDC の実ログイン | 実テナント資格情報が必要。`CATALOG_AUTH_MODE=local` のため未使用 |
| 5 | 負荷・性能特性 | 負荷試験未実施 |
| 6 | CI の実行結果（PR #98） | 作成直後のため実行中 |
| 7 | 協力会社向けの利用実態 | 利用者不在 |
| 8 | 独立したセキュリティレビュー | SubAgent委任がハーネス設定不具合で2回失敗（未登録ツール `pwsh` 参照）。**自ら実施したが第三者レビューは未完了** |

---

## 付録: 本評価で実行した検証コマンド（抜粋）

```
ruff check .                      -> All checks passed
mypy web scripts db               -> Success: no issues found in 33 source files
python -m pytest                  -> 147 passed, 5 skipped, 6 deselected  (改善前)
python -m pytest <DB 6ファイル>    -> 35 failed, 24 passed                  (改善前)
alembic current                   -> 20260730_05（head は 20260906_08）
curl :49231/api/health            -> 200 {"status":"ok"}
curl :49232/api/v1/health         -> 200 {"status":"ok","database":"unavailable"}
curl https://api.mirai-dx-platform.com/ -> 302 cloudflareaccess.com
ls backups/ ; systemctl --user list-timers | grep backup -> 存在せず
```
