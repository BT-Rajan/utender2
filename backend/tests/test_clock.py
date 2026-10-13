"""The app's clock is decided in one place (app.clock): times are stored in
UTC -- including database server defaults, whatever time zone the server is
set to -- and the calendar dates people work with are Kuwait dates."""
from datetime import date, datetime, timedelta

from sqlalchemy import text

import app.db as db_module
from app.clock import kuwait_date, kuwait_today
from app.db import engine_options
from app.models.user import User
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage4_9_participation import _account


def test_kuwait_dates_follow_utc_plus_three():
    # 21:30 UTC is already the next day in Kuwait; 20:59 is not.
    assert kuwait_date(datetime(2026, 10, 12, 21, 30)) == date(2026, 10, 13)
    assert kuwait_date(datetime(2026, 10, 12, 20, 59)) == date(2026, 10, 12)
    assert kuwait_today() == (datetime.utcnow() + timedelta(hours=3)).date()


def test_mysql_connections_run_in_utc():
    assert engine_options("mysql+pymysql://u:p@h/db")["connect_args"] == {"init_command": "SET time_zone = '+00:00'"}
    assert "connect_args" not in engine_options("sqlite:///:memory:")


@needs_mysql
def test_server_defaults_are_utc_on_a_kuwait_time_server(db):
    """However the MySQL server's own time zone is set (Kuwait servers run on
    Kuwait time), a row stamped by the database agrees with the app's UTC."""
    with db_module.engine.connect() as conn:
        assert conn.execute(text("SELECT @@session.time_zone")).scalar() == "+00:00"
    _account(db, "owner", "clock@example.com")
    stamped = db.query(User).filter(User.email == "clock@example.com").one().created_at
    assert abs(stamped - datetime.utcnow()) < timedelta(minutes=2)
