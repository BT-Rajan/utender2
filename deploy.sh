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
# HTTPS (Stage 9.13): terminate TLS in a reverse proxy (see
# docs/pilot-launch.md) and pass the public addresses once --
#   PUBLIC_APP_URL='https://utender.example.com' PUBLIC_API_URL='https://api.utender.example.com' ./deploy.sh
# They are remembered in backend/.env; an https address there is never
# replaced by a plain-http one on a later run.
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
# Stage 9.12: where backup.sh writes; the admin overview reads its outcome from here.
[ -n "$(get_env BACKUP_DIR)" ] || set_env BACKUP_DIR /var/backups/utender

# Ports: explicit APP_PORT/API_PORT, else what backend/.env remembers, else
# the first free port from 8080 up (only on the first run).
port_busy() { ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[.:]$1\$"; }
free_port() { local p="$1"; while port_busy "$p"; do p=$((p + 1)); done; echo "$p"; }
app_port="${APP_PORT:-$(get_env PUBLIC_HTTP_PORT)}"; app_port="${app_port:-$(free_port 8080)}"
api_port="${API_PORT:-$(get_env PUBLIC_API_PORT)}";  api_port="${api_port:-$(free_port $((app_port + 1)))}"
public_host="${PUBLIC_HOST:-$(curl -fsS --max-time 5 https://api.ipify.org || hostname -I | awk '{print $1}')}"
[ -n "$public_host" ] || fail "Couldn't detect the server address. Re-run with PUBLIC_HOST=your.server.ip"
# Public addresses: given now, else an https one already remembered, else plain http on the ports.
keep_https() { case "$1" in https://*) echo "$1" ;; esac; }
app_url="${PUBLIC_APP_URL:-$(keep_https "$(get_env APP_URL)")}"; app_url="${app_url:-http://${public_host}:${app_port}}"
api_url="${PUBLIC_API_URL:-$(keep_https "$(get_env API_URL)")}"; api_url="${api_url:-http://${public_host}:${api_port}}"
app_url="${app_url%/}"; api_url="${api_url%/}"
# Behind an HTTPS proxy the services listen on this machine only, so nobody
# reaches them over plain http around the proxy.
case "$app_url" in https://*) bind_host=127.0.0.1 ;; *) bind_host=0.0.0.0 ;; esac

set_env PUBLIC_HTTP_PORT "$app_port"
set_env PUBLIC_API_PORT "$api_port"
set_env APP_URL "$app_url"
set_env API_URL "$api_url"
set_env CORS_ORIGINS "$app_url"
ok "App $app_url, API $api_url"
case "$app_url" in https://*) ;; *) echo "    WARNING: plain http -- passwords and documents cross the network unencrypted. Put HTTPS in front before real customers (docs/pilot-launch.md)." ;; esac

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
VITE_API_URL="$api_url" npm run build --silent
ok "Built frontend/dist."

step "Starting services"
cat > /etc/systemd/system/utender-backend.service <<EOF
[Unit]
Description=U-Tender backend
After=network.target mariadb.service mysql.service

[Service]
WorkingDirectory=$repo_root/backend
ExecStart=$repo_root/backend/.venv/bin/uvicorn app.main:app --host $bind_host --port $api_port
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
ExecStart=$(command -v serve) -s dist -l tcp://$bind_host:$app_port
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Stage 9.12: a daily backup (database, uploaded files, configuration) -- see
# backup.sh and docs/disaster-recovery.md.
cat > /etc/systemd/system/utender-backup.service <<EOF
[Unit]
Description=U-Tender backup
After=mariadb.service mysql.service

[Service]
Type=oneshot
ExecStart=$repo_root/backup.sh
EOF

cat > /etc/systemd/system/utender-backup.timer <<EOF
[Unit]
Description=Daily U-Tender backup

[Timer]
OnCalendar=*-*-* 02:30:00
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --quiet utender-backend utender-frontend
systemctl enable --quiet --now utender-backup.timer
systemctl restart utender-backend utender-frontend

if [ "$bind_host" = 0.0.0.0 ] && command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
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
echo "  App:  $app_url"
echo "  API:  $api_url"
echo
echo "Logs:     journalctl -u utender-backend -f"
echo "Restart:  systemctl restart utender-backend utender-frontend"
echo "Update:   git pull && ./deploy.sh"
echo "Backup:   daily (systemctl list-timers utender-backup) -- run now: ./backup.sh; restore: see docs/disaster-recovery.md"
