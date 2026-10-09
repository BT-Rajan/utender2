"""Stage 3.10: the one place each participation rule is decided.

What providers are told (ProjectDetailOut.tender_rules) and what the server
enforces come from these functions and the existing ones they build on:

  offers close        Project.bid_deadline, tender_lifecycle.bidding_is_open
                      (submit, revise, withdraw, offer documents)
  offer visibility    Project.tender_type, tender_lifecycle.is_sealed_and_open
  questions           questions_allowed / questions_deadline, below. At the
                      cut-off the Q&A closes for both sides: no new questions
                      and no new answers.
  revise / withdraw   allowed while bidding is open (routers/offers.py)
  declarations        response_requirements (Stage 3.8)
"""
from datetime import datetime, timedelta

from app.models.project import Project
from app.services.tender_lifecycle import bidding_is_open


def questions_close_at(project: Project) -> datetime | None:
    """When questions stop being accepted; None if they aren't accepted at all."""
    if not project.questions_allowed:
        return None
    if project.questions_deadline and project.questions_deadline < project.bid_deadline:
        return project.questions_deadline
    return project.bid_deadline


def questions_open(project: Project) -> bool:
    close_at = questions_close_at(project)
    return close_at is not None and bidding_is_open(project) and datetime.utcnow() < close_at


def questions_closed_reason(project: Project) -> str:
    if not project.questions_allowed:
        return "This requirement doesn't accept questions."
    if project.questions_deadline and project.questions_deadline < project.bid_deadline:
        return "Questions for this requirement have closed."
    return "Questions can only be asked while offers are open."


# Batch B: an offer holds its price for the requirement's offer validity
# period (commercial conditions), counted from the close of offers -- or
# from when the provider last confirmed, after the close, that it still
# stands. After that the owner can't award it until the provider confirms
# again, and the provider may withdraw it.
def offer_valid_until(project: Project, offer) -> datetime | None:
    days = (project.commercial_conditions or {}).get("offer_validity_days")
    if not days or project.closed_at is None:
        return None
    start = max(project.closed_at, offer.validity_confirmed_at or project.closed_at)
    return start + timedelta(days=int(days))


def validity_lapsed(project: Project, offer) -> bool:
    until = offer_valid_until(project, offer)
    return until is not None and datetime.utcnow() > until


def answers_since(db, project: Project, offer) -> int:
    """Batch B: answers published to every provider after this offer was last
    put forward or confirmed -- they may change how it should be read."""
    from app.models.clarification import Clarification

    if offer.updated_at is None:
        return 0
    return (
        db.query(Clarification)
        .filter(
            Clarification.project_id == project.id, Clarification.offer_id.is_(None), Clarification.shared_with_all.is_(True),
            Clarification.answered_at.isnot(None), Clarification.answered_at >= offer.updated_at,  # same second counts (MySQL keeps whole seconds)
        )
        .count()
    )
