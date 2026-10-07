"""Stage 3.10: the one place each participation rule is decided.

What providers are told (ProjectDetailOut.tender_rules) and what the server
enforces come from these functions and the existing ones they build on:

  offers close        Project.bid_deadline, tender_lifecycle.bidding_is_open
                      (submit, revise, withdraw, offer documents)
  offer visibility    Project.tender_type, tender_lifecycle.is_sealed_and_open
  questions           questions_allowed / questions_deadline, below
  revise / withdraw   allowed while bidding is open (routers/offers.py)
  declarations        response_requirements (Stage 3.8)
"""
from datetime import datetime

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
