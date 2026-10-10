from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.revoked_token import RevokedToken

PURGE_BATCH = 1000


def purge_expired_revoked_tokens(db: Session, batch: int = PURGE_BATCH, max_batches: int = 1) -> int:
    """Deletes revoked-refresh-token rows whose token has expired on its own.

    Once a token is past its `exp`, decode_token_payload rejects it before the
    revocation table is ever consulted, so its row can never matter again.
    Rows still inside their lifetime are never touched.

    Deleted in bounded batches (ids first, then delete by id -- MySQL doesn't
    allow LIMIT inside an IN subquery) so one call can't lock the table for
    long. Returns the number of rows removed.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    removed = 0
    for _ in range(max_batches):
        ids = [
            jti
            for (jti,) in db.query(RevokedToken.jti).filter(RevokedToken.expires_at < now).limit(batch).all()
        ]
        if not ids:
            break
        removed += db.query(RevokedToken).filter(RevokedToken.jti.in_(ids)).delete(synchronize_session=False)
        db.commit()
        if len(ids) < batch:
            break
    return removed
