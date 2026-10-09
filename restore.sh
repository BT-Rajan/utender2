#!/usr/bin/env bash
# Restore U-Tender from one backup run made by backup.sh -- database, then
# uploaded files, then (optionally) configuration, then migrations, restart and
# a health check. See docs/disaster-recovery.md for the whole procedure.
#
#   RESTORE_CONFIRM=yes ./restore.sh /var/backups/utender/20261008T020000Z
#
# Options (environment):
#   ENV_FILE        configuration to restore INTO (default backend/.env) --
#                   point it at a staging copy to rehearse a restore safely.
#   RESTORE_CONFIG=yes  also put the backed-up configuration (secrets
#                   included) in place -- for a fresh server with no .env yet.
#   BACKUP_ENCRYPTION_KEY_FILE  the passphrase file, if the backup is encrypted.
#
# It REPLACES the target database's contents and moves the current files aside
# (storage.before-restore-<time>), so it asks for RESTORE_CONFIRM=yes.
set -euo pipefail
alembic_bin() { [ -x "$1/backend/.venv/bin/alembic" ] && echo "$1/backend/.venv/bin/alembic" || command -v alembic; }

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
alembic="$(alembic_bin "$repo_root")"
run_dir="${1:-}"
[ -n "$run_dir" ] && [ -d "$run_dir" ] || { echo "Usage: RESTORE_CONFIRM=yes ./restore.sh <backup run directory>" >&2; exit 1; }
[ "${RESTORE_CONFIRM:-}" = "yes" ] || { echo "This replaces the target database and files. Re-run with RESTORE_CONFIRM=yes." >&2; exit 1; }
env_file="${ENV_FILE:-$repo_root/backend/.env}"
key_file="${BACKUP_ENCRYPTION_KEY_FILE:-}"
work="$(mktemp -d)"; chmod 700 "$work"; trap 'rm -rf "$work"' EXIT

artefact() {  # the decrypted path of artefact "$1" from the run, or empty if absent
    if [ -f "$run_dir/$1.enc" ]; then
        [ -n "$key_file" ] || { echo "$1 is encrypted: set BACKUP_ENCRYPTION_KEY_FILE." >&2; exit 1; }
        openssl enc -d -aes-256-cbc -pbkdf2 -in "$run_dir/$1.enc" -out "$work/$1" -pass "file:$key_file"
        echo "$work/$1"
    elif [ -f "$run_dir/$1" ]; then
        echo "$run_dir/$1"
    fi
}

if [ "${RESTORE_CONFIG:-}" = "yes" ]; then
    cfg="$(artefact backend.env)"
    [ -n "$cfg" ] || { echo "No configuration in this backup." >&2; exit 1; }
    install -m 600 "$cfg" "$env_file"
    echo "Configuration restored to $env_file."
fi
[ -f "$env_file" ] || { echo "$env_file not found: restore it (RESTORE_CONFIG=yes) or create it first." >&2; exit 1; }
get_env() { grep -m1 "^$1=" "$env_file" | cut -d= -f2- || true; }

command -v systemctl >/dev/null 2>&1 && [ -z "${ENV_FILE:-}" ] && systemctl stop utender-backend 2>/dev/null || true

# 1. Database: empty the target, then load the dump.
creds="$work/my.cnf"
db_name="$(python3 - "$(get_env DATABASE_URL)" "$creds" <<'PY'
import sys, urllib.parse
url = urllib.parse.urlparse(sys.argv[1].replace("mysql+pymysql://", "mysql://", 1))
if url.scheme != "mysql":
    sys.exit("DATABASE_URL isn't a MySQL URL")
with open(sys.argv[2], "w") as f:
    f.write(f"[client]\nuser={urllib.parse.unquote(url.username or '')}\npassword={urllib.parse.unquote(url.password or '')}\n"
            f"host={url.hostname or '127.0.0.1'}\nport={url.port or 3306}\n")
print(url.path.lstrip("/"))
PY
)"
dump="$(artefact database.sql.gz)"
[ -n "$dump" ] || { echo "No database dump in this backup." >&2; exit 1; }
tables="$(mysql --defaults-extra-file="$creds" -N -B -e "SELECT table_name FROM information_schema.tables WHERE table_schema = '$db_name'")"
if [ -n "$tables" ]; then
    { echo "SET FOREIGN_KEY_CHECKS=0;"; for t in $tables; do echo "DROP TABLE \`$t\`;"; done; echo "SET FOREIGN_KEY_CHECKS=1;"; } \
        | mysql --defaults-extra-file="$creds" "$db_name"
fi
gunzip -c "$dump" | mysql --defaults-extra-file="$creds" "$db_name"
echo "Database $db_name restored."

# 2. Uploaded files: the current ones are moved aside, never deleted.
files="$(artefact storage.tar.gz)"
storage_root="$(get_env STORAGE_ROOT)"; storage_root="${storage_root:-$repo_root/backend/storage}"
case "$storage_root" in /*) ;; *) storage_root="$repo_root/backend/${storage_root#./}" ;; esac  # relative to backend/, as the app reads it
if [ -n "$files" ]; then
    if [ -d "$storage_root" ]; then
        mv "$storage_root" "$storage_root.before-restore-$(date -u +%Y%m%dT%H%M%SZ)"
    fi
    mkdir -p "$storage_root"
    tar -xzf "$files" -C "$storage_root" --strip-components=1
    echo "Files restored to $storage_root."
else
    echo "WARNING: this backup has no file archive -- documents referenced by the database will be missing." >&2
fi

# 3. Schema: an older backup is brought up to this code's migrations (never down).
(cd "$repo_root/backend" && ENV_FILE="$env_file" DATABASE_URL="$(get_env DATABASE_URL)" "$alembic" upgrade head)
echo "Schema at: $(cd "$repo_root/backend" && DATABASE_URL="$(get_env DATABASE_URL)" "$alembic" current 2>/dev/null | tail -1)"
[ -f "$run_dir/code-version" ] && echo "Backup was taken from code version $(cat "$run_dir/code-version")."

# 4. Restart and check (only for the live configuration).
if command -v systemctl >/dev/null 2>&1 && [ -z "${ENV_FILE:-}" ]; then
    systemctl start utender-backend
    port="$(get_env PUBLIC_API_PORT)"
    for _ in $(seq 1 20); do curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null 2>&1 && break; sleep 1; done
    curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null && echo "Backend is up." || echo "Backend isn't up -- journalctl -u utender-backend -n 50" >&2
fi
echo "Restore complete. Now verify sign-in, a requirement, a document and billing (docs/disaster-recovery.md)."
