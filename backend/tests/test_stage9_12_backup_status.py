"""Stage 9.12: a stopped or failing backup shows on the admin overview.
backup.sh records each run's outcome in BACKUP_DIR (last-success /
last-failure); the overview reads it and never calls a backup "healthy" --
only not configured, never run, failing, overdue or recent. (The backup and
restore themselves were rehearsed end to end against a non-production copy;
see docs/disaster-recovery.md.)"""
import json
from datetime import datetime, timedelta

from app.config import get_settings
from tests.test_stage8_15_review_moderation import _admin


def _write(directory, name, at, **extra):
    (directory / name).write_text(json.dumps({"at": at.strftime("%Y-%m-%dT%H:%M:%SZ"), **extra}))


def _backup(admin):
    bg = admin.get("/admin/overview").json()["background"]["data"]
    return bg["backup"], bg["last_backup_at"], bg["backup_failed_step"]


def test_backup_outcome_shows_on_the_overview(db, tmp_path, monkeypatch):
    admin = _admin(db)
    now = datetime.utcnow()
    with monkeypatch.context() as m:
        m.setattr(get_settings(), "backup_dir", None)
        assert _backup(admin) == ("not_configured", None, None)

        m.setattr(get_settings(), "backup_dir", str(tmp_path))
        assert _backup(admin) == ("never_run", None, None)

        _write(tmp_path, "last-success", now - timedelta(hours=3), run="r1", bytes=10)
        status, at, _ = _backup(admin)
        assert status == "recent" and at

        # A later failure wins over an older success, and names the step.
        _write(tmp_path, "last-failure", now - timedelta(hours=1), step="database dump")
        assert _backup(admin)[0::2] == ("failing", "database dump")

        # A success after the failure clears it (backup.sh also deletes the file).
        _write(tmp_path, "last-success", now - timedelta(minutes=5), run="r2", bytes=10)
        assert _backup(admin)[0] == "recent"

        # No success for over a day: the daily timer has stopped.
        (tmp_path / "last-failure").unlink()
        _write(tmp_path, "last-success", now - timedelta(hours=30), run="r0", bytes=10)
        assert _backup(admin)[0] == "overdue"

        # A garbled status file reads as "never run", not as a crash or a success.
        (tmp_path / "last-success").write_text("not json")
        assert _backup(admin)[0] == "never_run"
