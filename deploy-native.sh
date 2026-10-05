#!/usr/bin/env bash
# Native (no Docker) production deploy for U-Tender, for a server that
# already hosts other sites and doesn't have a domain pointed at it yet --
# e.g. a shared CloudPanel/Plesk-style box where 80/443/8000 are already
# taken and there's no CloudPanel "site" for this app.
#
# What this does:
#   1. Installs Python build prerequisites and Node.js if missing.
#   2. Creates a dedicated MySQL database + user for U-Tender on the
#      server's EXISTING MySQL instance (reusing it, not installing a
#      second one) -- needs the MySQL root/admin password once, passed in
#      as MYSQL_ROOT_PASSWORD, and only uses it to create that scoped
#      user; the generated password for that new user is what actually
#      ends up in backend/.env.
#   3. Picks two free ports (same "walk forward from a default until
#      something's free" logic as deploy.sh) for the API and the app.
#   4. Sets up a Python virtualenv for the backend, installs deps, runs
#      the Alembic migrations, and installs it as a systemd service.
#   5. Builds the frontend (VITE_API_URL baked in at build time, same as
#      the Docker path) and serves the static output with `serve`
#      (SPA-fallback aware) as a second systemd service.
#
# Safe to run again: it won't touch an existing backend/.env or an
# already-created database user, and both systemd services get restarted
# with whatever changed.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

step() { echo; echo -e "\033[36m==> $*\033[0m"; }
ok()   { echo -e "    \033[32m$*\033[0m"; }
warn() { echo -e "    \033[33m$*\033[0m"; }
fail() { echo; echo -e "\033[31mERROR: $*\033[0m"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Run this as root (or with sudo) -- it installs system packages and systemd services."

step "Checking prerequisites"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip build-essential libssl-dev >/dev/null
# A control panel like CloudPanel manages (and holds) its own MySQL client
# packages, so asking apt for a generic one here can trigger a dependency
# conflict on a server that already has one -- only bother installing it
# when nothing calling itself "mysql" is on PATH yet.
if ! command -v mysql >/dev/null 2>&1; then
    apt-get install -y -qq default-mysql-client >/dev/null \
        || apt-get install -y -qq mysql-client >/dev/null \
        || fail "Couldn't install a MySQL client automatically. Install one manually (matching whatever MySQL server this box already runs) and re-run."
fi
if ! command -v node >/dev/null 2>&1; then
    warn "Node.js isn't installed -- installing Node 20 via NodeSource."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
    apt-get install -y -qq nodejs >/dev/null
fi
ok "Python, Node, and MySQL client tools are available."

step "Detecting this server's public IP"
public_ip="$(curl -fsS --max-time 5 https://api.ipify.org || true)"
if [ -z "$public_ip" ]; then
    fail "Couldn't auto-detect the public IP. Re-run as: PUBLIC_IP=your.server.ip ./deploy-native.sh"
fi
if [ -n "${PUBLIC_IP:-}" ]; then
    public_ip="$PUBLIC_IP"
fi
ok "Using $public_ip"

step "Picking free ports"
port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[.:]${port}\$"
    else
        netstat -tln 2>/dev/null | awk '{print $4}' | grep -qE "[.:]${port}\$"
    fi
}
find_free_port() {
    local port="$1"
    while port_in_use "$port"; do
        port=$((port + 1))
    done
    echo "$port"
}
if [ -n "${PUBLIC_HTTP_PORT:-}" ]; then
    http_port="$PUBLIC_HTTP_PORT"
else
    http_port="$(find_free_port 8080)"
fi
if [ -n "${PUBLIC_API_PORT:-}" ]; then
    api_port="$PUBLIC_API_PORT"
else
    api_port="$(find_free_port $((http_port + 1)))"
fi
ok "App will be on port $http_port, API on port $api_port"

env_file="$repo_root/backend/.env"

step "Setting up the database"
db_host="${DB_HOST:-127.0.0.1}"
db_port="${DB_PORT:-3306}"
db_name="${DB_NAME:-utender}"
if [ -f "$env_file" ] && grep -q '^DATABASE_URL=' "$env_file" 2>/dev/null; then
    ok "backend/.env already has a DATABASE_URL -- leaving the database alone."
elif [ -n "${DB_USER:-}" ]; then
    # An existing MySQL user (e.g. one created in CloudPanel) -- use it as
    # the app's own credentials instead of creating a new one.
    : "${DB_PASSWORD:?Set DB_PASSWORD together with DB_USER}"
    db_user="$DB_USER"
    db_password="$DB_PASSWORD"
    export MYSQL_PWD="$db_password"  # keeps the password off the process list
    mysql -h"$db_host" -P"$db_port" -u"$db_user" \
        -e "CREATE DATABASE IF NOT EXISTS \`${db_name}\` CHARACTER SET utf8mb4;" 2>/dev/null || true
    mysql -h"$db_host" -P"$db_port" -u"$db_user" -e "USE \`${db_name}\`;" \
        || fail "MySQL user '${db_user}' can't log in or can't use database '${db_name}'. Check DB_USER/DB_PASSWORD, or set DB_NAME to a database that user has access to."
    unset MYSQL_PWD
    ok "Using existing MySQL user '${db_user}' on database '${db_name}'."
else
    # A stray apostrophe in this message (e.g. "the server's password")
    # would break bash's own parsing of ${VAR:?message} -- it needs its
    # quotes balanced even though the whole thing sits inside double
    # quotes -- so this stays contraction-free on purpose.
    : "${MYSQL_ROOT_PASSWORD:?Set MYSQL_ROOT_PASSWORD to the MySQL root or admin password for this server first, example: MYSQL_ROOT_PASSWORD=xxx ./deploy-native.sh -- get it with: clpctl db:show:master-credentials. Or reuse an existing MySQL user: DB_USER=xxx DB_PASSWORD=xxx DB_NAME=xxx ./deploy-native.sh}"
    db_user="utender"
    db_password="$(openssl rand -hex 16)"
    export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
    mysql -h"$db_host" -P"$db_port" -u"${MYSQL_ROOT_USER:-root}" -e "
        CREATE DATABASE IF NOT EXISTS \`${db_name}\` CHARACTER SET utf8mb4;
        CREATE USER IF NOT EXISTS '${db_user}'@'${db_host}' IDENTIFIED BY '${db_password}';
        GRANT ALL PRIVILEGES ON \`${db_name}\`.* TO '${db_user}'@'${db_host}';
        FLUSH PRIVILEGES;
    "
    unset MYSQL_PWD
    ok "Created database '${db_name}' and a scoped user for it (the master password above was only used for this one step)."
fi

step "Setting up backend/.env"
env_example="$repo_root/backend/.env.example"
new_secret() { openssl rand -hex 32; }

if [ -f "$env_file" ]; then
    ok "backend/.env already exists -- leaving it as-is."
else
    [ -f "$env_example" ] || fail "Can't find backend/.env.example -- make sure deploy-native.sh is sitting in the repo root."
    cp "$env_example" "$env_file"

    # Credentials go into a URL, so characters like # @ : / % & | must be
    # percent-encoded (this also keeps them from breaking the sed below).
    urlenc() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
    db_user_enc="$(urlenc "$db_user")"
    db_password_enc="$(urlenc "$db_password")"

    sed -i \
        -e "s|^DATABASE_URL=.*|DATABASE_URL=mysql+pymysql://${db_user_enc}:${db_password_enc}@${db_host}:${db_port}/${db_name}|" \
        -e "s|^ENVIRONMENT=.*|ENVIRONMENT=production|" \
        -e "s|^JWT_SECRET=.*|JWT_SECRET=$(new_secret)|" \
        -e "s|^STORAGE_SIGNING_SECRET=.*|STORAGE_SIGNING_SECRET=$(new_secret)|" \
        -e "s|^CRON_SECRET=.*|CRON_SECRET=$(new_secret)|" \
        -e "s|^STORAGE_ROOT=.*|STORAGE_ROOT=${repo_root}/backend/storage|" \
        -e "s|^APP_URL=.*|APP_URL=http://${public_ip}:${http_port}|" \
        -e "s|^API_URL=.*|API_URL=http://${public_ip}:${api_port}|" \
        -e "s|^CORS_ORIGINS=.*|CORS_ORIGINS=http://${public_ip}:${http_port}|" \
        "$env_file"

    {
        echo ""
        echo "# --- Ports this deploy is published on (set by deploy-native.sh) ---"
        echo "PUBLIC_HTTP_PORT=${http_port}"
        echo "PUBLIC_API_PORT=${api_port}"
    } >> "$env_file"

    ok "Created backend/.env with a fresh database password and generated secrets."
    warn "Stripe and email are left blank -- the app runs fine without them (billing checkout and emails just no-op). Fill them in later in backend/.env if you need them."
fi

# On a re-run, use whatever ports the existing .env actually has, not
# whatever was just freshly detected above.
http_port="$(grep -m1 '^PUBLIC_HTTP_PORT=' "$env_file" | cut -d= -f2)"
api_port="$(grep -m1 '^PUBLIC_API_PORT=' "$env_file" | cut -d= -f2)"
mkdir -p "$repo_root/backend/storage"

# A server that already hosts other sites often has ufw locked down to a
# specific allowlist of ports rather than wide open -- confirmed on the
# real target server this script was built against, where the app was
# unreachable from outside until these two were opened by hand. Doing it
# here means a fresh deploy (or a re-run that lands on new ports) doesn't
# need that manual step. `ufw allow` is idempotent -- safe to repeat.
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "^Status: active"; then
    step "Opening the app's ports in ufw"
    ufw allow "${http_port}/tcp" >/dev/null
    ufw allow "${api_port}/tcp" >/dev/null
    ok "Allowed ${http_port}/tcp and ${api_port}/tcp through the firewall."
fi

step "Setting up the backend (Python virtualenv, migrations)"
cd "$repo_root/backend"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
# app/config.py reads backend/.env itself (pydantic-settings' env_file
# support, resolved relative to the current working directory) -- no need
# to export its values into this shell first.
.venv/bin/alembic upgrade head
ok "Backend dependencies installed and migrations applied."

step "Installing the backend systemd service"
cat > /etc/systemd/system/utender-backend.service << SERVICEEOF
[Unit]
Description=U-Tender backend (FastAPI/uvicorn)
After=network.target mysql.service

[Service]
Type=simple
WorkingDirectory=${repo_root}/backend
EnvironmentFile=${repo_root}/backend/.env
ExecStart=${repo_root}/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${api_port}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICEEOF
systemctl daemon-reload
systemctl enable --quiet utender-backend
systemctl restart utender-backend
ok "utender-backend is running as a systemd service (survives reboots)."

step "Building and serving the frontend"
cd "$repo_root/frontend"
npm install --silent
VITE_API_URL="http://${public_ip}:${api_port}" npm run build --silent
if ! npm list -g serve >/dev/null 2>&1; then
    npm install -g --silent serve
fi
serve_bin="$(command -v serve)"

cat > /etc/systemd/system/utender-frontend.service << SERVICEEOF
[Unit]
Description=U-Tender frontend (static build via serve)
After=network.target

[Service]
Type=simple
WorkingDirectory=${repo_root}/frontend
ExecStart=${serve_bin} -s dist -l ${http_port}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICEEOF
systemctl daemon-reload
systemctl enable --quiet utender-frontend
systemctl restart utender-frontend
ok "utender-frontend is running as a systemd service (survives reboots)."

step "Waiting for the backend to come up"
ready=false
for _ in $(seq 1 30); do
    if curl -fsS --max-time 2 "http://localhost:${api_port}/docs" >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 2
done
if [ "$ready" = true ]; then
    ok "Backend is up."
else
    warn "Backend didn't respond yet. Check what's happening with: journalctl -u utender-backend -n 50 --no-pager"
fi

echo
echo -e "\033[36mU-Tender is running:\033[0m"
echo "  App:  http://${public_ip}:${http_port}"
echo "  API:  http://${public_ip}:${api_port}"
echo
echo -e "\033[36mFirst time here? Sign up through the app (as an owner or contractor),\033[0m"
echo "then make that account an admin:"
echo "  mysql -h127.0.0.1 -P3306 -uutender -p'<the password in backend/.env's DATABASE_URL>' utender -e \"UPDATE users SET role='admin' WHERE email='YOUR-EMAIL-HERE';\""
echo
echo "Useful commands:"
echo "  journalctl -u utender-backend -f      (watch backend logs)"
echo "  journalctl -u utender-frontend -f     (watch frontend logs)"
echo "  systemctl restart utender-backend     (restart the backend)"
echo "  systemctl restart utender-frontend    (restart the frontend)"
echo "  ./deploy-native.sh                     (re-run after a git pull to rebuild/redeploy)"
