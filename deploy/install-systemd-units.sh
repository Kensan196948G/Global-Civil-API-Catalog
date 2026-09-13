#!/usr/bin/env bash
# Global Civil API Catalog の systemd user unit を登録・更新する。
#
# 使い方:
#   bash deploy/install-systemd-units.sh            # 登録/更新 + 有効化
#   bash deploy/install-systemd-units.sh --status   # 状態確認のみ（変更しない）
#   bash deploy/install-systemd-units.sh --remove   # 停止して削除
#
# 対象:
#   global-civil-api-catalog-web.service        WebUI (:49231)
#   global-civil-api-catalog-api.service        API v1 (:49232)
#   gc-api-catalog-cloudflared.service          Tunnel (api.mirai-dx-platform.com)
#   gc-api-catalog-mvp-cloudflared.service      Tunnel (MVP)
#   global-civil-api-catalog-db-backup.service  PostgreSQL 論理バックアップ
#   global-civil-api-catalog-db-backup.timer    上記の日次実行
#
# 注意:
#   * api.service は %h/.config/global-civil-api-catalog/api.env を参照する。
#     実値はコミットしない（deploy/api.env.example から作成）。
#   * 本スクリプトは unit ファイルの配置と enable のみを行う。sudo は不要。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="${ROOT}/deploy"
UNIT_DST="${HOME}/.config/systemd/user"

UNITS=(
  global-civil-api-catalog-web.service
  global-civil-api-catalog-api.service
  global-civil-api-catalog-db-backup.service
  global-civil-api-catalog-db-backup.timer
)

usage() { sed -n '2,20p' "${BASH_SOURCE[0]}"; }

status() {
  echo "== 配置済み unit =="
  for u in "${UNITS[@]}"; do
    if [[ -f "${UNIT_DST}/${u}" ]]; then
      echo "  [配置済] ${u}"
    else
      echo "  [未配置] ${u}"
    fi
  done
  echo
  echo "== 稼働状態 =="
  systemctl --user list-units --all --no-legend 2>/dev/null \
    | grep -E 'global-civil-api-catalog|gc-api-catalog' || echo "  (該当 unit なし)"
  echo
  echo "== タイマー =="
  systemctl --user list-timers --all --no-legend 2>/dev/null \
    | grep -E 'db-backup' || echo "  (バックアップタイマーなし)"
}

remove() {
  echo "停止して削除します..."
  for u in global-civil-api-catalog-db-backup.timer \
           global-civil-api-catalog-db-backup.service; do
    systemctl --user disable --now "${u}" 2>/dev/null || true
  done
  for u in "${UNITS[@]}"; do
    rm -f "${UNIT_DST}/${u}"
  done
  systemctl --user daemon-reload
  echo "完了。データ本体(/backups)は削除していません。"
}

install_units() {
  mkdir -p "${UNIT_DST}"
  for u in "${UNITS[@]}"; do
    if [[ ! -f "${UNIT_SRC}/${u}" ]]; then
      echo "ERROR: ${UNIT_SRC}/${u} がありません" >&2
      exit 1
    fi
    install -m 0644 "${UNIT_SRC}/${u}" "${UNIT_DST}/${u}"
    echo "配置: ${u}"
  done

  if [[ ! -f "${HOME}/.config/global-civil-api-catalog/api.env" ]]; then
    echo
    echo "警告: ~/.config/global-civil-api-catalog/api.env がありません。"
    echo "      deploy/api.env.example をコピーして CATALOG_DATABASE_URL を設定してください。"
    echo "      未設定の場合 api.service は起動直後に失敗します。"
  fi

  systemctl --user daemon-reload
  for u in "${UNITS[@]}"; do
    systemctl --user enable "${u}" >/dev/null 2>&1 || true
  done
  systemctl --user restart global-civil-api-catalog-api.service || true
  systemctl --user start global-civil-api-catalog-db-backup.timer
  echo
  echo "完了。状態:"
  status
}

case "${1:-}" in
  --status) status ;;
  --remove) remove ;;
  "") install_units ;;
  *) usage; exit 2 ;;
esac
