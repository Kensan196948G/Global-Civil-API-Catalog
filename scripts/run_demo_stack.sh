#!/usr/bin/env bash
# Start/stop the local MVP demo stack (PostgreSQL + api_v1 + WebUI + webhook
# echo). All data is fictional and lives in data/demo; nothing here touches
# the production database, the production data/ files, or the systemd units.
#
# Usage:
#   bash scripts/run_demo_stack.sh start
#   bash scripts/run_demo_stack.sh stop
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PORT="${CATALOG_DEMO_DB_PORT:-55435}"
WEB_PORT="${CATALOG_DEMO_WEB_PORT:-49331}"
API_PORT="${CATALOG_DEMO_API_PORT:-49332}"
ECHO_PORT="${CATALOG_DEMO_ECHO_PORT:-49339}"
DB_NAME="catalog_demo"
DB_USER="catalog_demo"
DB_PASSWORD="catalog_demo_pw"
DB_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@127.0.0.1:${DB_PORT}/${DB_NAME}"
CONTAINER="gc-api-catalog-demo-db"
LOG_DIR="${TMPDIR:-/tmp}/gc-api-catalog-demo"
mkdir -p "$LOG_DIR"

export CATALOG_DEMO_SEED=1
export CATALOG_ENV=development
export CATALOG_BASE_URL="http://127.0.0.1:${WEB_PORT}"

stop_stack() {
  for pidfile in "$LOG_DIR"/web.pid "$LOG_DIR"/api.pid "$LOG_DIR"/echo.pid; do
    if [ -f "$pidfile" ]; then
      pid="$(cat "$pidfile")"
      kill "$pid" 2>/dev/null || true
      rm -f "$pidfile"
    fi
  done
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  echo "Demo stack stopped (processes + container removed)."
}

if [ "${1:-}" = "stop" ]; then
  stop_stack
  exit 0
fi

if [ "${1:-}" != "start" ]; then
  echo "Usage: $0 start|stop" >&2
  exit 2
fi

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Demo DB container already running." >&2
  exit 1
fi

echo "Starting demo PostgreSQL (${DB_PORT})..."
docker run -d --name "$CONTAINER" \
  -e POSTGRES_USER="$DB_USER" \
  -e POSTGRES_PASSWORD="$DB_PASSWORD" \
  -e POSTGRES_DB="$DB_NAME" \
  -p "127.0.0.1:${DB_PORT}:5432" \
  postgis/postgis:14-3.4 >/dev/null

for i in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS postgis" >/dev/null

echo "Applying migrations..."
CATALOG_DATABASE_URL="$DB_URL" python -m alembic upgrade head

echo "Seeding fictional demo data..."
CATALOG_DATABASE_URL="$DB_URL" python scripts/seed_demo_data.py

echo "Generating demo export artifacts..."
CATALOG_DATA_DIR="data/demo" CATALOG_EXPORT_DIR="export-demo" python scripts/export_markdown.py

echo "Starting webhook echo server (${ECHO_PORT})..."
nohup python scripts/demo_webhook_echo.py --port "$ECHO_PORT" \
  >"$LOG_DIR/echo.log" 2>&1 &
echo $! >"$LOG_DIR/echo.pid"

echo "Starting api_v1 (${API_PORT})..."
CATALOG_DATABASE_URL="$DB_URL" \
CATALOG_AUTH_MODE=local \
CATALOG_BASE_URL="$CATALOG_BASE_URL" \
nohup python -m uvicorn web.api_v1:app --host 127.0.0.1 --port "$API_PORT" \
  >"$LOG_DIR/api.log" 2>&1 &
echo $! >"$LOG_DIR/api.pid"

echo "Starting WebUI (${WEB_PORT}, demo data)..."
CATALOG_PORT="$WEB_PORT" \
CATALOG_DATA_DIR="data/demo" \
CATALOG_EXPORT_DIR="export-demo" \
CATALOG_API_UPSTREAM="http://127.0.0.1:${API_PORT}" \
nohup python web/server.py --host 127.0.0.1 --port "$WEB_PORT" \
  >"$LOG_DIR/web.log" 2>&1 &
echo $! >"$LOG_DIR/web.pid"

sleep 2
echo ""
echo "Demo stack started:"
echo "  WebUI:      http://127.0.0.1:${WEB_PORT}  (ログイン: demo-admin / DemoPassw0rd!2026)"
echo "  API:        http://127.0.0.1:${API_PORT}/api/v1/health"
echo "  Webhook:    http://127.0.0.1:${ECHO_PORT}/webhook-echo"
echo "  Logs:       $LOG_DIR"
echo "  Webhook履歴: data/demo/webhook_deliveries.jsonl"
