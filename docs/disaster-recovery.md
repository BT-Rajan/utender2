# U-Tender backup, restore and disaster recovery

This is the runbook for one U-Tender server deployed with `deploy.sh`
(systemd, MySQL, local file storage). It covers what is backed up, how to
restore it, and what you can honestly expect from that. It is not a
multi-region or high-availability design.

## What a working U-Tender needs

To rebuild U-Tender you need all three of these. With any one missing, the restore is incomplete.

| Part | Where it lives | Why it matters |
|---|---|---|
| Database | MySQL (`DATABASE_URL`) | Accounts, organisations, requirements, offers, awards, agreements, milestones, reviews, billing state and the audit trail |
| Uploaded files | `STORAGE_ROOT` (by default `backend/storage`) | Requirement drawings, offer and agreement documents, completion evidence and verification documents. The database only holds their keys. |
| Configuration | `backend/.env` | The database login, `JWT_SECRET`, `STORAGE_SIGNING_SECRET`, `CRON_SECRET`, Stripe and Resend keys, and the public URLs |

The code isn't in this table because it's in git. Each backup records the commit it was made from (`code-version`) and the migration it was at (`schema-version`).

## Backups

`./backup.sh` is run as root from the repo root. `deploy.sh` installs a systemd timer (`utender-backup.timer`) that runs it **daily at about 02:30**. It catches up after downtime because `Persistent=true` is set. Each run creates `$BACKUP_DIR/<UTC time>/` containing:

- `database.sql.gz` is a `mysqldump --single-transaction` snapshot. It's consistent across InnoDB tables and doesn't lock the app.
- `storage.tar.gz` is the whole file store.
- `backend.env` is the configuration, secrets included.
- `code-version` and `schema-version` record the commit and migration.

Settings are read from `backend/.env`:

- `BACKUP_DIR` defaults to `/var/backups/utender`.
- `BACKUP_KEEP_DAYS` defaults to 14.
- `BACKUP_ENCRYPTION_KEY_FILE` and `BACKUP_RSYNC_TARGET` are optional (see "Protecting the backups").

**Access.** Backups contain every customer's data and the production secrets, so they're treated as such:

- The directory is mode `0700` and files are `0600`, so only root can read them.
- Database credentials are passed to `mysqldump` through a private option file, never on the command line, where `ps` would show them.
- Nothing is written into the repository.

**Failures are visible.** Every run writes `$BACKUP_DIR/last-success` (time, run, size, whether it was encrypted or copied off-server) or `last-failure` (time and the step that failed). A run that fails before it is complete removes its partial directory, so a broken backup is never kept and mistaken for a good one. The admin **Overview → Background → Backups** line reads these files and shows one of:

- not configured;
- no backup recorded yet;
- **last run failed at: <step>**;
- **overdue**, when there's been no success for 26 hours, meaning the timer has stopped;
- last success <time>.

It never says "healthy": a recent backup is not proof that it restores. Only a restore test proves that. Also check `systemctl list-timers utender-backup` and `journalctl -u utender-backup`.

To run a backup now (for example before a risky change): `sudo ./backup.sh`.

### Protecting the backups

By default, backups sit on the **same disk** as the server. They protect against mistakes and corruption, but not against losing the server. For real disaster recovery, set both of these:

- **Encryption.** Set `BACKUP_ENCRYPTION_KEY_FILE` to a passphrase file:

  ```sh
  openssl rand -base64 48 > /root/utender-backup.key
  chmod 600 /root/utender-backup.key
  ```

  Every artefact is then encrypted (AES-256, PBKDF2) before it's kept or copied. **Store a copy of this key off the server**, in your password manager. Without the key, an encrypted backup can't be restored.
- **Off-server copy.** Set `BACKUP_RSYNC_TARGET` (for example `backup@other-host:/srv/utender`), using SSH key access for root. Each run is copied there. If the copy fails, the run is recorded as failed ("off-server copy"), but the complete local copy is kept.

The secrets in `backend.env` are protected the same way as the data. Don't put production secrets into git or this repository to make recovery easier. Their recovery path is the encrypted backup plus the off-server key.

## Restore

`restore.sh` **replaces** the target database and moves the current files aside to `storage.before-restore-<time>`. It requires `RESTORE_CONFIRM=yes`.

### Rehearse first, never on production

Point `ENV_FILE` at a copy of the configuration that names a scratch database and storage directory, then restore into that:

```sh
cp backend/.env /root/restore-test.env    # then edit it:
# DATABASE_URL=...the scratch database (e.g. utender_restore)...
# STORAGE_ROOT=/root/restore-test/storage
ENV_FILE=/root/restore-test.env BACKUP_ENCRYPTION_KEY_FILE=/root/utender-backup.key \
  RESTORE_CONFIRM=yes ./restore.sh /var/backups/utender/<run>
```

When `ENV_FILE` isn't the live `backend/.env`, the script doesn't stop or restart the live service.

### Recovery order after losing the server

1. **Infrastructure.** Set up a new server with MySQL. Create the database and its user (`CREATE DATABASE utender; CREATE USER ...; GRANT ALL ON utender.* ...`) using the same login as the backed-up `DATABASE_URL`, or change it afterwards.
2. **Code.** Run `git clone` into the **same path** as before, because the restored `STORAGE_ROOT` is absolute. Then `git checkout <code-version>` from the backup (or the current main branch if its migrations are newer, since the restore upgrades the schema).
3. **Backups.** Copy the latest run back from the off-server copy, and the key from your password manager.
4. **Configuration and secrets, database, files and migrations.** Run:

   ```sh
   RESTORE_CONFIG=yes BACKUP_ENCRYPTION_KEY_FILE=/root/utender-backup.key \
     RESTORE_CONFIRM=yes ./restore.sh <run>
   ```

   This puts the backed-up `.env` in place (mode 600) and loads the database. It then restores the files and runs `alembic upgrade head`. It prints the restored schema version and the code version the backup was made from. The secrets are restored unchanged, which matters for two reasons:
   - Existing sessions and signed file links stay valid.
   - Stripe and Resend keep working without new keys.
5. **Application.** Run `./deploy.sh`, adding `PUBLIC_HOST=<new address>` if the address changed. It installs the dependencies, builds the frontend for the new address, installs the services and the backup timer, and health-checks the backend. Because `.env` already exists, it keeps your secrets.
6. **Scheduled jobs.** Re-create whatever calls `/cron/deadline-reminders` hourly (with `Authorization: Bearer $CRON_SECRET`). `deploy.sh` doesn't schedule it. The admin overview shows "overdue" reminders if it isn't running.
7. **External services.**
   - **DNS / address:** point the domain (or users) at the new server.
   - **Stripe:** Stripe is authoritative for subscriptions. Update the webhook endpoint URL in the Stripe dashboard if the address changed. The signing secret is unchanged. Events Stripe sent while the server was down are retried by Stripe for up to 3 days. Out-of-order events are ignored (Stage 9.6). A subscription that changed during the outage is corrected by its next event.
   - **Resend:** this needs no change unless the sending domain changed.
8. **Verify.** Check that:
   - `/health` returns 200;
   - an admin can sign in and the Overview loads with every section available;
   - a known requirement, agreement and its documents open;
   - a non-member gets 404 on that agreement;
   - the Backups line shows the next run succeeding.

### Restore rehearsal (Stage 9.12)

The backup and restore were rehearsed on a non-production MySQL copy (the demo dataset plus a test account), with encryption on:

- **Data:** all 39 tables restored with identical row counts, and all stored files restored with identical SHA-256.
- **Schema:** the restored database was at migration `0064 (head)`.
- **Sign-in:** the app ran on the restored configuration. The test account signed in, and a wrong password got 401.
- **Records:** the completed agreement and its review were present.
- **Documents:** a private agreement document opened through its signed link, and a tampered link got 403.
- **Access control:**
  - an unauthenticated request got 401;
  - a signed-in owner of an unrelated organisation got 404 on both the agreement and its requirement.
- **Failure detection:** a run with a wrong database password recorded `last-failure` at "database dump", kept no partial run, and showed as failing. The next good run cleared it.

## What to expect (RPO / RTO)

- **RPO (data you can lose): up to about 24 hours.** Backups are daily. Anything created since the last good backup is lost: requirements, offers, messages, uploads, and agreement changes. Stripe keeps its own record of payments and subscriptions.
- **RTO (time to be back): about 1–2 hours, by hand.** That assumes an off-server copy and the key are at hand. It covers a new server, MySQL, clone, restore, deploy and DNS. Most of it is server setup. The restore itself took seconds on the demo data and grows with the database and file sizes.
- If the backups exist only on the lost server, **nothing can be restored**. Configure `BACKUP_RSYNC_TARGET`.

## Known limitations

- **Snapshot window.** The database snapshot and the file archive are taken one after the other, not at the same instant. A file uploaded in the seconds between them can be missing, or present without its database row. Uploads always create new keys, so restored records never point at a newer version of a file.
- **Same-disk by default.** Without `BACKUP_RSYNC_TARGET`, backups don't survive the loss of the server. Without `BACKUP_ENCRYPTION_KEY_FILE`, the copies are plain (but root-only).
- **S3 storage.** If `STORAGE_BACKEND=s3`, files aren't in `STORAGE_ROOT` and `backup.sh` doesn't copy them. Use bucket versioning or replication.
- **Restore granularity.** There's no point-in-time recovery: a restore takes you back to a whole backup run. Restoring a single record means restoring into a scratch database (as in the rehearsal) and copying it across by hand.
- **Deployment.** The deployment is plain HTTP on a single server (see Stage 9.11). There's no standby: recovery is the manual procedure above.
