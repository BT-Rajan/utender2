#!/usr/bin/env bash
# Deploy U-Tender on a Linux server (no Docker), using a MySQL/MariaDB
# database that already exists. Run as root from the repo root:
#
#   First time:
#     DB_USER='app_user' DB_PASSWORD='secret' DB_NAME='utender' ./deploy.sh
#
#   After a git pull (credentials and ports are remembered in backend/.env):
#     ./deploy.sh
#
# Optional: DB_HOST (127.0.0.1), DB_PORT (3306), APP_PORT (8080),
# API_PORT (8081), PUBLIC_HOST (auto-detected public IP, or a domain).
# Passing DB_* or *_PORT again later updates backend/.env with the new values.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_file="$repo_root/backend/.env"

step() { echo; echo -e "\033[36m==> $*\033[0m"; }
ok()   { echo -e "    \033[32m$*\033[0m"; }
fail() { echo; echo -e "\033[31mERROR: $*\033[0m"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Run as root (or with sudo) -- this installs systemd services."

# Reads KEY from backend/.env (empty if missing).
get_env() { [ -f "$env_file" ] && grep -m1 "^$1=" "$env_file" | cut -d= -f2- || true; }
# Sets KEY=VALUE in backend/.env, replacing an existing line or appending.
set_env() {
    python3 - "$env_file" "$1" "$2" <<'PY'
import sys, re
path, key, value = sys.argv[1:]
lines = open(path).read().splitlines()
for i, line in enumerate(lines):
    if line.startswith(key + "="):
        lines[i] = f"{key}={value}"
        break
else:
    lines.append(f"{key}={value}")
open(path, "w").write("\n".join(lines) + "\n")
PY
}
urlenc() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
secret() { openssl rand -hex 32; }

step "Installing prerequisites"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip curl openssl >/dev/null
if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
    apt-get install -y -qq nodejs >/dev/null
fi
command -v serve >/dev/null 2>&1 || npm install -g --silent serve
ok "Python, Node and serve are ready."

step "Configuring backend/.env"
if [ ! -f "$env_file" ]; then
    [ -n "${DB_USER:-}" ] && [ -n "${DB_PASSWORD:-}" ] \
        || fail "First run needs the database login: DB_USER='app_user' DB_PASSWORD='secret' DB_NAME='utender' ./deploy.sh"
    cp "$repo_root/backend/.env.example" "$env_file"
    chmod 600 "$env_file"
    set_env ENVIRONMENT production
    set_env JWT_SECRET "$(secret)"
    set_env STORAGE_SIGNING_SECRET "$(secret)"
    set_env CRON_SECRET "$(secret)"
    set_env STORAGE_ROOT "$repo_root/backend/storage"
    ok "Created backend/.env with fresh secrets."
fi

if [ -n "${DB_USER:-}" ]; then
    [ -n "${DB_PASSWORD:-}" ] || fail "DB_PASSWORD is required together with DB_USER."
    set_env DATABASE_URL "mysql+pymysql://$(urlenc "$DB_USER"):$(urlenc "$DB_PASSWORD")@${DB_HOST:-127.0.0.1}:${DB_PORT:-3306}/${DB_NAME:-utender}"
    ok "Database: ${DB_USER}@${DB_HOST:-127.0.0.1}:${DB_PORT:-3306}/${DB_NAME:-utender}"
fi

# Ports: explicit APP_PORT/API_PORT, else what backend/.env remembers, else
# the first free port from 8080 up (only on the first run).
port_busy() { ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[.:]$1\$"; }
free_port() { local p="$1"; while port_busy "$p"; do p=$((p + 1)); done; echo "$p"; }
app_port="${APP_PORT:-$(get_env PUBLIC_HTTP_PORT)}"; app_port="${app_port:-$(free_port 8080)}"
api_port="${API_PORT:-$(get_env PUBLIC_API_PORT)}";  api_port="${api_port:-$(free_port $((app_port + 1)))}"
public_host="${PUBLIC_HOST:-$(curl -fsS --max-time 5 https://api.ipify.org || hostname -I | awk '{print $1}')}"
[ -n "$public_host" ] || fail "Couldn't detect the server address. Re-run with PUBLIC_HOST=your.server.ip"

set_env PUBLIC_HTTP_PORT "$app_port"
set_env PUBLIC_API_PORT "$api_port"
set_env APP_URL "http://${public_host}:${app_port}"
set_env API_URL "http://${public_host}:${api_port}"
set_env CORS_ORIGINS "http://${public_host}:${app_port}"
ok "App http://${public_host}:${app_port}, API http://${public_host}:${api_port}"

step "Backend: dependencies and migrations"
cd "$repo_root/backend"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
mkdir -p storage
.venv/bin/alembic upgrade head
ok "Database schema is up to date."

step "Frontend: build"
cd "$repo_root/frontend"
npm ci --silent
VITE_API_URL="http://${public_host}:${api_port}" npm run build --silent
ok "Built frontend/dist."

step "Starting services"
cat > /etc/systemd/system/utender-backend.service <<EOF
[Unit]
Description=U-Tender backend
After=network.target mariadb.service mysql.service

[Service]
WorkingDirectory=$repo_root/backend
ExecStart=$repo_root/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $api_port
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/utender-frontend.service <<EOF
[Unit]
Description=U-Tender frontend
After=network.target

[Service]
WorkingDirectory=$repo_root/frontend
ExecStart=$(command -v serve) -s dist -l $app_port
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --quiet utender-backend utender-frontend
systemctl restart utender-backend utender-frontend

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw allow "${app_port}/tcp" >/dev/null
    ufw allow "${api_port}/tcp" >/dev/null
fi

for _ in $(seq 1 20); do
    curl -fsS --max-time 2 "http://127.0.0.1:${api_port}/health" >/dev/null 2>&1 && break
    sleep 1
done
if curl -fsS --max-time 2 "http://127.0.0.1:${api_port}/health" >/dev/null 2>&1; then
    ok "Backend is healthy."
else
    echo "    Backend isn't responding yet -- check: journalctl -u utender-backend -n 50 --no-pager"
fi

echo
echo -e "\033[36mU-Tender is running:\033[0m"
echo "  App:  http://${public_host}:${app_port}"
echo "  API:  http://${public_host}:${api_port}"
echo
echo "Logs:     journalctl -u utender-backend -f"
echo "Restart:  systemctl restart utender-backend utender-frontend"
echo "Update:   git pull && ./deploy.sh"
