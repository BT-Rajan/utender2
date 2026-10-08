from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

# Stage 7.15: every state change is decided under a row lock (lock_project's
# SELECT ... FOR UPDATE) and then checked against the rows it governs. At
# MySQL's default REPEATABLE READ, a request that read anything before
# waiting for that lock (its user, say) would go on reading those other rows
# from its earlier snapshot -- judging "already accepted?", "already
# completed?" on state another request has since committed. READ COMMITTED
# gives every statement the latest committed data, so a check made under the
# lock sees what the lock holder wrote. (The MySQL tests already run this way.)
def engine_options(database_url: str) -> dict:
    options = {"pool_pre_ping": True}
    if database_url.startswith("mysql"):
        options["isolation_level"] = "READ COMMITTED"
    return options


engine = create_engine(settings.database_url, **engine_options(settings.database_url))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
