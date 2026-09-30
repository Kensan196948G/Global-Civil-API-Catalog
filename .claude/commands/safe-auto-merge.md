# /safe-auto-merge

GitHub Token を利用して open PR を安全に処理するコマンドです。

このコマンドを選んだら、次の方針で進めてください。

- マージ規定: PR は `gh pr merge --auto --squash` で自動マージを予約する。マージの条件は Required Checks の全成功と merge conflict がないことだけとし、人間の Y/N・選択・Approve を待たない。`--admin` による迂回は禁止する。Release・本番デプロイ・秘密情報の変更・不可逆な削除は、コードのマージとは別に Human Gate とする。（正本: 中央ポリシー `GITHUB_POLICY.md` v2）
- main/default branch 宛を含むすべての PR を同じ gate で扱う。
- `GITHUB_TOKEN` / `GH_TOKEN` は `gh` CLI にだけ使い、値を表示・保存しない。
- force push、history rewrite、直接 push、`--admin` による迂回はしない。

実行手順:

1. `gh auth status` と `gh repo view --json defaultBranchRef` を確認する。
2. `gh pr list --state open` で対象 PR を列挙する。
3. 各 PR の `baseRefName`, `isDraft`, `mergeable`, `mergeStateStatus`, `statusCheckRollup` を確認する。
4. 次をすべて満たす PR に `gh pr merge <number> --auto --squash` を実行し、自動マージを予約する（Required Checks の成功で GitHub がマージする）。

自動マージ gate:

- `isDraft=false`
- `mergeable=MERGEABLE`（merge conflict がない）
- Required Checks に失敗・取消がない（未完了は `--auto` の予約で待つ）

Release・本番 deploy・secrets の登録/変更/削除・不可逆な削除・branch protection / ruleset の変更は、PR のマージとは別の Human Gate として扱い、このコマンドでは実行しない。

最後に `merged`, `auto-merge enabled`, `skipped`（Draft・conflict・CI 失敗）に分類して報告してください。
