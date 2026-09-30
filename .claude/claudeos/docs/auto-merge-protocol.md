# Auto Merge Protocol — 自律マージ

## 概要

PR は `gh pr merge --auto --squash` で自動マージを予約する。マージの条件は Required Checks の全成功と merge conflict がないことだけとし、人間の Y/N・選択・Approve を待たない。`--admin` による迂回は禁止する。Release・本番デプロイ・秘密情報の変更・不可逆な削除は、コードのマージとは別に Human Gate とする。（正本: 中央ポリシー `GITHUB_POLICY.md` v2）

main/default branch 宛を含むすべての PR が対象。Trust Level はマージ条件ではなく、運用品質の監視指標として扱う。

---

## 発動条件

| 条件 | 内容 |
|---|---|
| CI | Required Checks の全成功（`gh pr checks` 全て pass） |
| mergeability | merge conflict がない |

## マージとは別の Human Gate

- Release
- 本番デプロイ
- 秘密情報の登録・変更・削除
- 不可逆な削除

---

## CTO の実行手順

```bash
# 1. CI の状態を確認（未完了は --auto の予約で待つ）
gh pr checks <PR番号>

# 2. auto-merge を予約（--admin は使わない）
gh pr merge <PR番号> --auto --squash
echo "[AutoMerge] PR #<番号> に auto-merge を設定しました"
```

---

## PowerShell 版（Windows cron 環境）

```powershell
gh pr merge $prNumber --auto --squash
Write-Host "[AutoMerge] PR #$prNumber auto-merge 設定"
```

---

## 注意事項

- `--auto` フラグは「CI 通過後に自動マージ」を設定するもので、即時マージではない
- マージを止める必要がある場合は、ルールの迂回ではなく CI（Required Checks）で止める。予約の取り消しは:
  ```bash
  gh pr merge <PR番号> --disable-auto
  ```
- 週次で auto-merge の実績と Trust Level を確認し、問題があれば Required Checks を強化すること
