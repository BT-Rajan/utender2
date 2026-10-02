"""Shared pytest fixtures for the backend test suite.

Every test gets a fresh, fully isolated in-memory SQLite database and a
fresh local-file storage root, even though `app.main` (and every router
module it pulls in) is only ever imported once for the whole pytest
session. This works because `app.db.get_db()` and
`app.services.storage.get_storage()` both resolve their session
factory / settings from their *module's current global* at call time
(not at import time), so reassigning `app.db.engine`/`SessionLocal` and
`app.services.storage.settings.storage_root` before each test takes
effect on every request that test makes.

Required settings (JWT_SECRET, STORAGE_SIGNING_SECRET, ...) are given
safe test defaults here, before anything under `app` is imported, so
`Settings()` never has to fall back to its `mysql://`-pointing
production default for `database_url` — not that it matters, since
every test replaces the engine directly regardless of what
`DATABASE_URL` resolved to at import time.

Two database targets
--------------------
* Default (no env var): per-test in-memory SQLite, schema from
  `Base.metadata.create_all` — fast, needs nothing running.
* `TEST_DATABASE_URL=mysql+pymysql://...`: a real MySQL server. At session
  start every table in that database is dropped and the schema is rebuilt by
  running `alembic upgrade head` (so the migrations themselves are what the
  tests run against, not the ORM's idea of the schema); between tests every
  table is truncated, which gives each test the same empty starting state
  SQLite's `create_all` gives. The target database's name must contain
  "test" — the session reset is destructive and refuses to run otherwise.
"""
import os
import shutil
import subprocess
import sys
import tempfile

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or None
USE_MYSQL = TEST_DATABASE_URL is not None
if USE_MYSQL:
    if not TEST_DATABASE_URL.startswith("mysql"):
        raise RuntimeError("TEST_DATABASE_URL must be a mysql+pymysql:// URL (leave it unset to use SQLite).")
    # app.db builds its engine from this at import time.
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
else:
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("STORAGE_SIGNING_SECRET", "test-signing-secret")
os.environ.setdefault("STORAGE_ROOT", tempfile.mkdtemp(prefix="utender-test-storage-"))
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("S3_REGION", "us-east-1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import close_all_sessions, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db as db_module
import app.models  # noqa: F401  registers every ORM model on Base.metadata
import app.services.storage as storage_module

from fastapi.testclient import TestClient
from app.main import app as fastapi_app  # imported once for the whole session


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mysql_table_names(conn) -> list[str]:
    return list(conn.execute(text("SHOW TABLES")).scalars().all())


@pytest.fixture(scope="session")
def mysql_engine():
    """Session-wide engine for the MySQL target (None under SQLite).

    Drops everything in the test database, then rebuilds it with the real
    Alembic migration chain so every run exercises 0001 -> head on a
    pristine server."""
    if not USE_MYSQL:
        yield None
        return

    db_name = make_url(TEST_DATABASE_URL).database or ""
    if "test" not in db_name.lower():
        pytest.exit(
            f"Refusing to wipe database {db_name!r}: TEST_DATABASE_URL must point at a database whose "
            "name contains 'test' (the MySQL test session drops every table in it).",
            returncode=2,
        )

    # READ COMMITTED, not MySQL's default REPEATABLE READ: many tests keep one
    # long-lived `db` session and re-read through it after API calls commit on
    # other connections. SQLite's single shared connection always showed those
    # commits; under REPEATABLE READ the session's first read pins a snapshot
    # and later reads return stale rows (false failures in pass5/6/13/21).
    # Application request sessions are short-lived, so this only changes what
    # the tests' own sessions can see; no test assertion depends on it.
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True, isolation_level="READ COMMITTED")
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for name in _mysql_table_names(conn):
            conn.execute(text(f"DROP TABLE IF EXISTS `{name}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
    )

    yield engine
    engine.dispose()


def _truncate_all_mysql_tables(engine) -> None:
    """Back to the empty state SQLite's create_all starts every test in. This
    also clears rows the migrations seed (e.g. default document
    requirements), which the SQLite path never has."""
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for name in _mysql_table_names(conn):
            if name != "alembic_version":
                conn.execute(text(f"TRUNCATE TABLE `{name}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


@pytest.fixture(autouse=True)
def isolated_backend(tmp_path, mysql_engine):
    """Runs before/after every test: fresh DB, fresh storage root."""
    from app.services.login_throttle import login_throttle

    login_throttle.reset()  # process-global; every TestClient shares one "client ip"
    if USE_MYSQL:
        engine = mysql_engine
        _truncate_all_mysql_tables(engine)
    else:
        engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    if not USE_MYSQL:
        db_module.Base.metadata.create_all(bind=engine)

    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    storage_module.settings.storage_root = str(storage_root)
    storage_module.settings.storage_backend = "local"
    storage_module._storage_instance = None

    yield

    if USE_MYSQL:
        # Many tests open `db_module.SessionLocal()` directly and never close
        # it. SQLite's single shared connection hides that; on MySQL the
        # leaked session's open transaction holds a metadata lock that blocks
        # the next test's TRUNCATE forever. Release them all here.
        close_all_sessions()
    else:
        engine.dispose()


@pytest.fixture
def client():
    """A single anonymous TestClient. Most tests create their own
    per-actor clients directly (`TestClient(app)`) since each actor
    needs its own cookie jar — this fixture covers the simple cases."""
    return TestClient(fastapi_app)


@pytest.fixture
def db():
    """A raw DB session for setup/assertions that bypass the API
    (e.g. flipping a document straight to approved, or reading an
    AuditLog row the API doesn't expose)."""
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def approve_owner(db_session, owner_id: str) -> None:
    """Test-only shortcut mirroring how Alembic migration 0005 grandfathers
    every pre-existing owner in as approved: most tests just need "an
    owner who can post a project" and don't care about the document-upload
    path itself (that path has its own dedicated coverage in
    test_owner_verification_and_admin.py) — this avoids repeating the
    upload/submit/admin-approve dance in every test file that only needs
    a working owner as a precondition for something else."""
    from app.models.enums import VerificationStatus
    from app.models.owner import OwnerProfile

    profile = db_session.get(OwnerProfile, owner_id)
    profile.verification_status = VerificationStatus.approved
    db_session.commit()
