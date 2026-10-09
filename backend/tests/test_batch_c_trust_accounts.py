"""Batch C: trust, notifications and accounts. Each test is one of the
business-logic faults found in the end-to-end review, now corrected:

- a new notice never writes over an unread one that says something else;
- reviews are double-blind: sealed from the other side (and from ratings)
  until both have reviewed or the sealed period has passed;
- repeat transactions between the same two parties count once in a rating;
- account notices reach everyone acting for an organisation, and the
  representative role can be handed over;
- "start similar" doesn't copy the old expected dates;
- an owner can invite a provider it completed work with."""
from datetime import datetime, timedelta

from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.project import Project
from app.models.review import Review
from app.models.service_provider import ServiceProviderProfile
from app.services.reviews import reveal_due
from tests.stage7_helpers import complete_transaction, put_in_force
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _d, _submitted, _tender


def _me(c):
    return c.get("/auth/me").json()["id"]


def _completed(db, owner, provider, title):
    pid = _tender(owner, title=title)
    _submitted(provider, pid)
    owner.post(f"/owner/projects/{pid}/close")
    assert owner.post(f"/owner/projects/{pid}/offers/{provider.get(f'/projects/{pid}/offers/mine').json()['id']}/approve").status_code == 200
    complete_transaction(owner, provider, pid)
    return pid


def test_a_different_notice_never_replaces_an_unread_one(db):
    owner = _account(db, "owner", "o-notice@example.com")
    sp = _account(db, "service_provider", "s-notice@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/offers/{sp.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    base = f"/projects/{pid}/agreement"

    def v(c):
        return {"If-Match": str(c.get(base).json()["version"])}

    for title in ("Panels", "Cabling"):
        assert owner.post(f"{base}/milestones", json={"title": title}, headers=v(owner)).status_code == 200
    put_in_force(owner, sp, pid)
    sp.post(f"{base}/start-work", json={}, headers=v(sp))
    ids = {m["title"]: (m["id"], m["version"]) for m in sp.get(base).json()["milestones"]}
    for title in ("Panels", "Cabling"):
        mid, ver = ids[title]
        assert sp.post(f"{base}/milestones/{mid}/deliver", json={}, headers={"If-Match": str(ver)}).status_code == 200
    milestones = {m["title"]: m for m in owner.get(base).json()["milestones"]}
    assert owner.post(f"{base}/milestones/{milestones['Panels']['id']}/return", json={"note": "Wrong rating."},
                      headers={"If-Match": str(milestones["Panels"]["version"])}).status_code == 200
    assert owner.post(f"{base}/milestones/{milestones['Cabling']['id']}/accept", json={},
                      headers={"If-Match": str(milestones["Cabling"]["version"])}).status_code == 200
    bodies = [n.body for n in db.query(Notification).filter(Notification.user_id == _me(sp), Notification.type == NotificationType.milestone_updated, Notification.is_read.is_(False))]
    assert any('"Panels"' in b and "returned" in b for b in bodies) and any('"Cabling"' in b and "accepted" in b for b in bodies)


def test_reviews_are_sealed_until_both_sides_review(db):
    owner = _account(db, "owner", "o-blind@example.com")
    sp = _account(db, "service_provider", "s-blind@example.com")
    pid = _completed(db, owner, sp, "Blind")
    mine = owner.post("/owner/reviews", json={"project_id": pid, "rating": 2, "comment": "Late."}).json()
    assert mine["revealed"] is False and mine["reveals_on"] is not None
    # The provider can't read it, and it doesn't move the rating yet.
    assert sp.get(f"/service-provider/projects/{pid}/review/received").json() is None
    assert db.get(ServiceProviderProfile, _me(sp)).review_count == 0
    # The provider reviews too: both are revealed together.
    assert sp.post("/service-provider/reviews", json={"project_id": pid, "rating": 4}).status_code == 200
    assert sp.get(f"/service-provider/projects/{pid}/review/received").json()["rating"] == 2
    assert owner.get(f"/owner/projects/{pid}/review/received").json()["rating"] == 4
    db.expire_all()
    assert db.get(ServiceProviderProfile, _me(sp)).review_count == 1


def test_a_sealed_review_is_revealed_after_the_period(db):
    owner = _account(db, "owner", "o-later@example.com")
    sp = _account(db, "service_provider", "s-later@example.com")
    pid = _completed(db, owner, sp, "Later")
    owner.post("/owner/reviews", json={"project_id": pid, "rating": 5})
    review = db.query(Review).filter(Review.project_id == pid).one()
    review.created_at = datetime.utcnow() - timedelta(days=15)
    db.commit()
    assert sp.get(f"/service-provider/projects/{pid}/review/received").json()["rating"] == 5
    assert reveal_due(db) == 1
    db.expire_all()
    assert db.get(ServiceProviderProfile, _me(sp)).review_count == 1


def test_repeat_deals_between_the_same_parties_count_once(db):
    owner = _account(db, "owner", "o-farm@example.com")
    sp = _account(db, "service_provider", "s-farm@example.com")
    for n in range(3):
        pid = _completed(db, owner, sp, f"Job {n}")
        owner.post("/owner/reviews", json={"project_id": pid, "rating": 5})
        sp.post("/service-provider/reviews", json={"project_id": pid, "rating": 5})
    db.expire_all()
    profile = db.get(ServiceProviderProfile, _me(sp))
    assert profile.review_count == 1
    rep = owner.get(f"/projects/{pid}/owner-reputation").json()
    assert rep["review_count"] == 1


def test_account_notices_reach_the_whole_organisation_and_the_role_can_be_handed_over(db):
    admin = _admin(db)
    rep, member, rep_id, member_id = _organization(db, "service_provider", "Gulf Shield W.L.L.", "rep@shield.example", "eng@shield.example")
    r = admin.post(f"/admin/service-providers/{rep_id}/payment-override", json={"reason": "Pilot access."})
    assert r.status_code == 200, r.text
    told = {n.user_id for n in db.query(Notification).filter(Notification.type == NotificationType.payment_override_granted)}
    assert told == {rep_id, member_id}
    # The representative hands over; the colleague now manages the members.
    roles = rep.post(f"/account/organization/representative/{member_id}").json()
    assert {m["user_id"]: m["role"] for m in roles} == {member_id: "admin", rep_id: "member"}
    assert rep.delete(f"/account/organization/members/{member_id}").status_code == 403
    assert member.get("/account/organization/members").status_code == 200


def test_start_similar_does_not_copy_the_old_dates(db):
    owner = _account(db, "owner", "o-again@example.com")
    pid = _tender(owner)
    owner.patch(f"/projects/{pid}", json={"expected_start_date": _d(30), "expected_duration_days": 20})
    owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "postponed"})
    again = owner.post(f"/owner/projects/{pid}/restart", json={}).json()
    copy = db.get(Project, again["id"])
    assert copy.expected_start_date is None and copy.expected_completion_date is None and copy.expected_duration_days == 20


def test_an_owner_invites_a_provider_it_worked_with(db):
    owner = _account(db, "owner", "o-invite@example.com")
    sp = _account(db, "service_provider", "s-invite@example.com")
    stranger = _account(db, "service_provider", "s-stranger@example.com")
    _completed(db, owner, sp, "First job")
    previous = owner.get("/owner/previous-providers").json()
    assert previous[0]["service_provider_id"] == _me(sp)
    pid = _tender(owner, title="Second job")
    assert owner.post(f"/owner/projects/{pid}/invitations/{_me(sp)}").status_code == 204
    notice = db.query(Notification).filter(Notification.user_id == _me(sp), Notification.type == NotificationType.requirement_invitation).one()
    assert notice.link == f"/service-provider/projects/{pid}/offer"
    # Only a provider it worked with; never once it has offered.
    assert owner.post(f"/owner/projects/{pid}/invitations/{_me(stranger)}").status_code == 404
    _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/invitations/{_me(sp)}").status_code == 409
