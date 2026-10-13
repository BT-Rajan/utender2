"""The one place the app's clock is decided.

Times are kept in UTC everywhere: the application stamps datetime.utcnow(),
and every database connection runs in UTC (db.engine_options), so a
server-side NOW() / CURRENT_TIMESTAMP default is UTC too -- whatever time
zone the server itself is set to. Kuwait servers run on Kuwait time; nothing
has to be configured per server for the stored times to agree.

Calendar dates people work with (agreement dates, document expiry, "today")
are Kuwait dates: UTC+3, no daylight saving."""
from datetime import date, datetime, timedelta

KUWAIT_OFFSET = timedelta(hours=3)


def kuwait_date(moment: datetime) -> date:
    """The Kuwait calendar date of a stored (UTC) moment."""
    return (moment + KUWAIT_OFFSET).date()


def kuwait_today() -> date:
    """Today's calendar date in Kuwait."""
    return kuwait_date(datetime.utcnow())
