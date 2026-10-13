import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import event, text

import app.db as db_module
from app.models.email_change import EmailChangeRequest
from app.models.organization import Organization, OrganizationMembership
from app.models.user import User
from app.models.enums import UserRole
from app.auth.security import hash_password
from tests.test_organization_sharing import _account


def _run(fn, out, key):
    try:
        out[key] = fn()
    except Exception as e:  # noqa
        out[key] = repr(e)[:300]


def _mk_admin(db):
    a = User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="A", email_verified=True)
    db.add(a)
    db.commit()
    return a.id


def _setup_email_change(db):
    c, uid = _account("owner", "u@example.com")
    r = c.post("/auth/email-change/request", json={"new_email": "n1@example.com", "current_password": "password123"})
    assert r.status_code == 200, r.text
    # past the resend cooldown
    db.query(EmailChangeRequest).update({EmailChangeRequest.created_at: datetime.utcnow() - timedelta(minutes=5)})
    db.commit()
    return uid


def _race_with_request_change(other):
    from app.services import email_change as ec

    S = db_module.SessionLocal
    dbA, dbB = S(), S()
    out = {}
    hit = threading.Event()

    @event.listens_for(dbA, "after_bulk_update")
    def _pause(update_context):
        hit.set()
        time.sleep(1.5)  # let the other transaction take the user row and block on the request row

    uidA = dbA.query(User).filter(User.email == "u@example.com").one()

    def a():
        ec.request_change(dbA, uidA, "n2@example.com", "password123")
        return "ok"

    def b():
        hit.wait(5)
        time.sleep(0.2)
        r = other(dbB)
        dbB.commit()
        return r

    ta, tb = threading.Thread(target=_run, args=(a, out, "request_change")), threading.Thread(target=_run, args=(b, out, "other"))
    ta.start(); tb.start(); ta.join(20); tb.join(20)
    dbA.close(); dbB.close()
    return out


def test_confirm_vs_request_deadlock(db):
    from app.services import email_change as ec

    _setup_email_change(db)

    def other(dbB):
        u = dbB.query(User).filter(User.email == "u@example.com").one()
        ec.confirm_change(dbB, u, "000000")
        return "ok"

    out = _race_with_request_change(other)
    print("\nCONFIRM vs REQUEST:", out)


def test_admin_edit_vs_request_deadlock(db):
    from app.routers.admin import AccountDetailsPatch, edit_account_details

    uid = _setup_email_change(db)
    aid = _mk_admin(db)

    def other(dbB):
        admin = dbB.get(User, aid)
        edit_account_details(uid, AccountDetailsPatch(email="fixed@example.com"), admin=admin, db=dbB)
        return "ok"

    out = _race_with_request_change(other)
    print("\nADMIN EDIT vs REQUEST:", out)


def _two_orgs(db):
    a, a_id = _account("owner", "repa@example.com")
    assert a.put("/account/stakeholder", json={"type": "organization", "legal_name": "Org A", "authorized": True}).status_code == 200
    b, b_id = _account("owner", "repb@example.com")
    assert b.put("/account/stakeholder", json={"type": "organization", "legal_name": "Org B", "authorized": True}).status_code == 200
    org_a = db.query(OrganizationMembership).filter(OrganizationMembership.user_id == a_id).one().organization_id
    org_b = db.query(OrganizationMembership).filter(OrganizationMembership.user_id == b_id).one().organization_id
    return a, b, org_a, org_b


def test_admin_add_member_blocks_on_unrelated_user_row(db):
    from app.services import stakeholder as st

    _, _, org_a, _ = _two_orgs(db)
    _account("owner", "joiner@example.com")
    _account("owner", "zzz@example.com")
    aid = _mk_admin(db)
    print("\nEXPLAIN:", db.execute(text("EXPLAIN SELECT * FROM users WHERE lower(email)='joiner@example.com' FOR UPDATE")).mappings().all())
    db.rollback()
    S = db_module.SessionLocal
    dbZ, dbT = S(), S()
    # An unrelated person's row being updated (e.g. their own language/name change, login, etc.)
    dbZ.execute(text("UPDATE users SET full_name='Zed' WHERE email='zzz@example.com'"))
    dbT.execute(text("SET SESSION innodb_lock_wait_timeout=2"))
    t0 = time.time()
    try:
        st.admin_add_member(dbT, dbT.get(User, aid), org_a, "joiner@example.com", False, None, None)
        res = "added"
    except Exception as e:
        res = repr(e)[:200]
    print("ADMIN_ADD with unrelated row locked:", res, "after %.1fs" % (time.time() - t0))
    dbT.rollback(); dbZ.rollback(); dbT.close(); dbZ.close()


def test_double_join_admin_add_vs_accept(db):
    from app.services import stakeholder as st

    a, b, org_a, org_b = _two_orgs(db)
    u, u_id = _account("owner", "joiner@example.com")
    r = b.post("/account/organization/invitations", json={"email": "joiner@example.com"})
    token = r.json()["link"].rsplit("/", 1)[-1]
    aid = _mk_admin(db)
    S = db_module.SessionLocal
    dbT1, dbT2 = S(), S()
    st.admin_add_member(dbT1, dbT1.get(User, aid), org_a, "joiner@example.com", False, None, None)
    out = {}
    passed = threading.Event()
    orig = st._has_active_representative

    def spy(db_, oid):
        passed.set()
        return orig(db_, oid)

    st._has_active_representative = spy

    def acc():
        st.accept_invitation(dbT2.get(User, u_id), dbT2, token)
        dbT2.commit()
        return "accepted"

    t = threading.Thread(target=_run, args=(acc, out, "accept"))
    t.start(); print('\nPASSED-CHECK', passed.wait(10), dbT1.execute(text('SELECT @@transaction_isolation')).scalar()); time.sleep(0.5)
    dbT1.commit()
    st._has_active_representative = orig
    t.join(10)
    dbT1.close(); dbT2.close()
    db.expire_all()
    rows = db.query(OrganizationMembership.organization_id).filter(OrganizationMembership.user_id == u_id).all()
    print("\nDOUBLE JOIN:", out, "memberships:", len(rows))
