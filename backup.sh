#!/usr/bin/env bash
# Back up U-Tender: the database, the uploaded files and the configuration --
# all three are needed to restore a working U-Tender (see
# docs/disaster-recovery.md). Run as root from the repo root; deploy.sh
# installs a daily systemd timer that runs it.
#
#   ./backup.sh
#
# Settings are read from backend/.env:
#   DATABASE_URL, STORAGE_ROOT          what to back up
#   BACKUP_DIR        (default /var/backups/utender)  where; root-only (0700)
#   BACKUP_KEEP_DAYS  (default 14)                    retention
#   BACKUP_ENCRYPTION_KEY_FILE  (optional)  encrypt every artefact with this
#                     passphrase file (openssl AES-256, PBKDF2). Keep a copy
#                     of the key OFF this server -- without it nothing restores.
#   BACKUP_RSYNC_TARGET (optional)  e.g. backup@host:/srv/utender -- copied
#                     off-server after each run. A backup on the same disk
#                     doesn't survive the loss of the server.
#
# Every run records its outcome in $BACKUP_DIR/last-success or last-failure,
# which the admin overview reads, so a stopped or failing backup shows.
set -euo pipefail
alembic_bin() { [ -x "$1/backend/.venv/bin/alembic" ] && echo "$1/backend/.venv/bin/alembic" || command -v alembic; }

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
alembic="$(alembic_bin "$repo_root")"
env_file="${ENV_FILE:-$repo_root/backend/.env}"  # ENV_FILE: back up another configuration (e.g. a staging copy)
[ -f "$env_file" ] || { echo "backend/.env not found -- nothing to back up." >&2; exit 1; }
get_env() { grep -m1 "^$1=" "$env_file" | cut -d= -f2- || true; }

backup_dir="$(get_env BACKUP_DIR)"; backup_dir="${backup_dir:-/var/backups/utender}"
keep_days="$(get_env BACKUP_KEEP_DAYS)"; keep_days="${keep_days:-14}"
key_file="$(get_env BACKUP_ENCRYPTION_KEY_FILE)"
rsync_target="$(get_env BACKUP_RSYNC_TARGET)"
storage_root="$(get_env STORAGE_ROOT)"; storage_root="${storage_root:-$repo_root/backend/storage}"
case "$storage_root" in /*) ;; *) storage_root="$repo_root/backend/${storage_root#./}" ;; esac  # relative to backend/, as the app reads it
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_dir="$backup_dir/$stamp"

umask 077
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

failed_step="starting"
on_error() {
    printf '{"at": "%s", "step": "%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$failed_step" > "$backup_dir/last-failure"
    # A run that failed only at the off-server copy or retention is complete
    # locally: keep it. Anything earlier is partial: remove it.
    case "$failed_step" in "off-server copy"|retention) ;; *) rm -rf "$run_dir" ;; esac
    echo "BACKUP FAILED at: $failed_step" >&2
}
trap on_error ERR

# Database credentials from DATABASE_URL, into a private option file (never on
# the command line, where other users could read them from ps).
failed_step="reading DATABASE_URL"
creds="$(mktemp)"; trap 'rm -f "$creds"' EXIT
db_name="$(python3 - "$(get_env DATABASE_URL)" "$creds" <<'PY'
import sys, urllib.parse
url = urllib.parse.urlparse(sys.argv[1].replace("mysql+pymysql://", "mysql://", 1))
if url.scheme != "mysql":
    sys.exit("DATABASE_URL isn't a MySQL URL")
with open(sys.argv[2], "w") as f:
    f.write("[client]\n")
    f.write(f"user={urllib.parse.unquote(url.username or '')}\n")
    f.write(f"password={urllib.parse.unquote(url.password or '')}\n")
    f.write(f"host={url.hostname or '127.0.0.1'}\nport={url.port or 3306}\n")
print(url.path.lstrip("/"))
PY
)"

mkdir -p "$run_dir"
encrypt() {  # encrypt "$1" in place when a key file is configured
    [ -n "$key_file" ] || return 0
    openssl enc -aes-256-cbc -pbkdf2 -salt -in "$1" -out "$1.enc" -pass "file:$key_file"
    rm -f "$1"
}

# 1. The database: one consistent InnoDB snapshot, without locking the app.
failed_step="database dump"
mysqldump --defaults-extra-file="$creds" --single-transaction --quick --routines --triggers \
    --no-tablespaces "$db_name" | gzip > "$run_dir/database.sql.gz"
encrypt "$run_dir/database.sql.gz"

# 2. The uploaded files (requirement drawings, offer and agreement documents,
#    evidence, verification documents). Taken right after the dump: a file
#    replaced in the seconds between the two can be missing; see the runbook.
failed_step="file archive"
if [ -d "$storage_root" ]; then
    tar -czf "$run_dir/storage.tar.gz" -C "$(dirname "$storage_root")" "$(basename "$storage_root")"
    encrypt "$run_dir/storage.tar.gz"
fi

# 3. The configuration, secrets included -- kept as private as the server's own copy.
failed_step="configuration copy"
cp "$env_file" "$run_dir/backend.env"
encrypt "$run_dir/backend.env"
git -C "$repo_root" rev-parse HEAD > "$run_dir/code-version" 2>/dev/null || true
(cd "$repo_root/backend" && DATABASE_URL="$(get_env DATABASE_URL)" "$alembic" current 2>/dev/null | tail -1 > "$run_dir/schema-version") || true

# 4. Off-server copy, when configured.
if [ -n "$rsync_target" ]; then
    failed_step="off-server copy"
    rsync -a "$run_dir" "$rsync_target/"
fi

# 5. Retention: drop runs older than BACKUP_KEEP_DAYS (never the one just made).
failed_step="retention"
find "$backup_dir" -mindepth 1 -maxdepth 1 -type d -name '20*Z' -mtime "+$keep_days" ! -name "$stamp" -exec rm -rf {} +

size="$(du -sb "$run_dir" | cut -f1)"
printf '{"at": "%s", "run": "%s", "bytes": %s, "encrypted": %s, "off_server": %s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$stamp" "$size" \
    "$([ -n "$key_file" ] && echo true || echo false)" "$([ -n "$rsync_target" ] && echo true || echo false)" \
    > "$backup_dir/last-success"
rm -f "$backup_dir/last-failure"
echo "Backup complete: $run_dir"
