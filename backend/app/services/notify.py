from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.enums import Language, NotificationType
from app.models.notification import Notification
from app.models.user import User

# Rendered server-side, once, in the recipient's language AT THE TIME OF
# CREATION (spec §2.10) — never re-translated on read, so a later language
# change never rewrites notification history. Each entry is
# (title_template, body_template); both are .format()-ed with whatever
# kwargs the call site passes.
_TEMPLATES: dict[NotificationType, dict[Language, tuple[str, str]]] = {
    NotificationType.bid_submitted: {
        Language.en: ("New offer on {project_title}", "{service_provider_name} submitted an offer on {project_title}."),
        Language.ar: ("عرض جديد على {project_title}", "قدم {service_provider_name} عرضًا على {project_title}."),
    },
    # Stage 5.11: a provider revised an offer already submitted.
    NotificationType.bid_revised: {
        Language.en: ("Offer revised on {project_title}", "{service_provider_name} revised their offer on {project_title}."),
        Language.ar: ("تعديل عرض على {project_title}", "عدّل {service_provider_name} عرضه على {project_title}."),
    },
    # A provider withdrew an offer (anonymous while the tender is sealed).
    NotificationType.bid_withdrawn: {
        Language.en: ("Offer withdrawn on {project_title}", "{service_provider_name} withdrew their offer on {project_title}."),
        Language.ar: ("سحب عرض على {project_title}", "سحب {service_provider_name} عرضه على {project_title}."),
    },
    NotificationType.award_won: {
        Language.en: ("You won {project_title}", "Your offer on {project_title} was accepted."),
        Language.ar: ("لقد فزت بـ {project_title}", "تم قبول عرضك على {project_title}."),
    },
    NotificationType.award_lost: {
        Language.en: ("Update on {project_title}", "The owner of {project_title} went with another offer."),
        Language.ar: ("تحديث بخصوص {project_title}", "اختار مالك {project_title} عرضًا آخر."),
    },
    NotificationType.clarification_asked: {
        Language.en: ("New question on {project_title}", "A service provider asked a question about {project_title}."),
        Language.ar: ("سؤال جديد على {project_title}", "طرح أحد مزوّدي الخدمات سؤالاً حول {project_title}."),
    },
    NotificationType.clarification_shared: {
        Language.en: ("New clarification on {project_title}", "The owner of {project_title} answered a question for every provider. Read it before you price."),
        Language.ar: ("توضيح جديد على {project_title}", "أجاب مالك {project_title} عن سؤال لجميع مقدّمي الخدمة. اطّلع عليه قبل التسعير."),
    },
    NotificationType.clarification_answered: {
        Language.en: ("Your question was answered", "The owner of {project_title} answered your question."),
        Language.ar: ("تمت الإجابة على سؤالك", "أجاب مالك {project_title} على سؤالك."),
    },
    NotificationType.new_requirement: {
        Language.en: ("New opportunity: {project_title}", "A new {trade} requirement in {area} is open for offers until {deadline}. You meet its conditions."),
        Language.ar: ("فرصة جديدة: {project_title}", "طلب جديد لأعمال {trade} في {area} مفتوح للعروض حتى {deadline}. أنت تستوفي شروطه."),
    },
    NotificationType.tender_paused: {
        Language.en: ("{project_title} is paused", "The owner paused this requirement: {reason} No offers or changes are accepted until it resumes. Your offer is kept."),
        Language.ar: ("تم إيقاف {project_title} مؤقتًا", "أوقف المالك هذا الطلب مؤقتًا: {reason} لا تُقبل عروض أو تعديلات حتى يُستأنف. عرضك محفوظ."),
    },
    NotificationType.tender_resumed: {
        Language.en: ("{project_title} is open again", "The owner resumed this requirement. Offers are open until {deadline}."),
        Language.ar: ("{project_title} مفتوح مجددًا", "استأنف المالك هذا الطلب. العروض مفتوحة حتى {deadline}."),
    },
    NotificationType.tender_closed: {
        Language.en: ("{project_title} closed for offers", "The owner closed this requirement early. No more offers are accepted; your offer is kept as submitted."),
        Language.ar: ("أُغلق {project_title} أمام العروض", "أغلق المالك هذا الطلب مبكرًا. لا تُقبل عروض أخرى؛ عرضك محفوظ كما قُدّم."),
    },
    NotificationType.tender_amendment: {
        Language.en: ("{project_title} was updated", "{summary}"),
        Language.ar: ("تم تحديث {project_title}", "{summary}"),
    },
    NotificationType.document_approved: {
        Language.en: ("Document approved", "Your {requirement_name} document was approved."),
        Language.ar: ("تمت الموافقة على المستند", "تمت الموافقة على مستند {requirement_name} الخاص بك."),
    },
    NotificationType.document_rejected: {
        Language.en: ("Document needs correction", "Your {requirement_name} document needs correction: {note} Please upload a corrected version."),
        Language.ar: ("المستند يحتاج إلى تصحيح", "مستند {requirement_name} الخاص بك يحتاج إلى تصحيح: {note} يرجى رفع نسخة مصححة."),
    },
    NotificationType.verification_activated: {
        Language.en: ("You're verified", "Your service provider account has been approved."),
        Language.ar: ("تم التحقق من حسابك", "تمت الموافقة على حساب مزوّد الخدمة الخاص بك."),
    },
    NotificationType.payment_override_granted: {
        Language.en: ("Marketplace access activated", "An administrator activated full marketplace access on your account."),
        Language.ar: ("تم تفعيل الوصول إلى السوق", "قام أحد المسؤولين بتفعيل الوصول الكامل إلى السوق لحسابك."),
    },
    NotificationType.payment_override_revoked: {
        Language.en: ("Marketplace access changed", "Your admin-granted marketplace access was revoked."),
        Language.ar: ("تغيّر الوصول إلى السوق", "تم إلغاء الوصول إلى السوق الذي منحه المسؤول لحسابك."),
    },
    NotificationType.service_provider_suspended: {
        Language.en: ("Account suspended", "Your account has been suspended by a site admin."),
        Language.ar: ("تم تعليق الحساب", "تم تعليق حسابك من قبل مسؤول الموقع."),
    },
    NotificationType.service_provider_reactivated: {
        Language.en: ("Account reactivated", "Your account has been reactivated."),
        Language.ar: ("تم إعادة تفعيل الحساب", "تمت إعادة تفعيل حسابك."),
    },
    NotificationType.verification_changes_requested: {
        Language.en: ("Verification needs changes", "Your verification needs changes before it can be approved. {note}"),
        Language.ar: ("التحقق يحتاج إلى تعديلات", "يحتاج طلب التحقق الخاص بك إلى تعديلات قبل اعتماده. {note}"),
    },
    NotificationType.verification_rejected: {
        Language.en: ("Verification rejected", "Your verification was rejected. Reason: {note}"),
        Language.ar: ("تم رفض التحقق", "تم رفض طلب التحقق الخاص بك. السبب: {note}"),
    },
    NotificationType.tender_no_award: {
        Language.en: ("No award on {project_title}", "The owner closed {project_title} without awarding it through U-Tender. Your offer is kept on record."),
        Language.ar: ("لم يتم الترسية على {project_title}", "أغلق المالك {project_title} دون ترسيته عبر U-Tender. يبقى عرضك محفوظًا في السجل."),
    },
    NotificationType.tender_cancelled: {
        Language.en: ("{project_title} was canceled", "The owner canceled this project. It won't go ahead in its current form; your offer is kept on record."),
        Language.ar: ("تم إلغاء {project_title}", "قام المالك بإلغاء هذا المشروع. لن يمضي بصيغته الحالية؛ يبقى عرضك محفوظًا في السجل."),
    },
    NotificationType.requirement_ended: {
        Language.en: ("{project_title} has ended", "The owner ended {project_title} before its deadline. It is no longer open for offers."),
        Language.ar: ("انتهى {project_title}", "أنهى المالك {project_title} قبل موعده النهائي. لم يعد مفتوحًا لتلقي العروض."),
    },
    NotificationType.deadline_approaching: {
        Language.en: ("Bidding closes soon — {project_title}", "{project_title} stops accepting offers within 24 hours."),
        Language.ar: ("يغلق التقديم قريبًا — {project_title}", "سيتوقف {project_title} عن قبول العروض خلال 24 ساعة."),
    },
    NotificationType.owner_verification_activated: {
        Language.en: ("You're verified", "Your owner account has been approved."),
        Language.ar: ("تم التحقق من حسابك", "تمت الموافقة على حساب المالك الخاص بك."),
    },
    NotificationType.owner_document_approved: {
        Language.en: ("Document approved", "Your {requirement_name} document was approved."),
        Language.ar: ("تمت الموافقة على المستند", "تمت الموافقة على مستند {requirement_name} الخاص بك."),
    },
    NotificationType.owner_document_rejected: {
        Language.en: ("Document needs correction", "Your {requirement_name} document needs correction: {note} Please upload a corrected version."),
        Language.ar: ("المستند يحتاج إلى تصحيح", "مستند {requirement_name} الخاص بك يحتاج إلى تصحيح: {note} يرجى رفع نسخة مصححة."),
    },
    NotificationType.owner_suspended: {
        Language.en: ("Account suspended", "Your account has been suspended by a site admin."),
        Language.ar: ("تم تعليق الحساب", "تم تعليق حسابك من قبل مسؤول الموقع."),
    },
    NotificationType.owner_reactivated: {
        Language.en: ("Account reactivated", "Your account has been reactivated."),
        Language.ar: ("تم إعادة تفعيل الحساب", "تمت إعادة تفعيل حسابك."),
    },
    NotificationType.project_suspended: {
        Language.en: ("{project_title} was suspended", "A site admin suspended this project — it's hidden from service providers until reactivated."),
        Language.ar: ("تم تعليق {project_title}", "قام مسؤول الموقع بتعليق هذا المشروع — أصبح مخفيًا عن مزوّدي الخدمات حتى تتم إعادة تفعيله."),
    },
    NotificationType.project_reactivated: {
        Language.en: ("{project_title} was reactivated", "A site admin reactivated this project."),
        Language.ar: ("تمت إعادة تفعيل {project_title}", "قام مسؤول الموقع بإعادة تفعيل هذا المشروع."),
    },
    NotificationType.offer_suspended: {
        Language.en: ("Your offer on {project_title} was suspended", "A site admin suspended your offer — it's hidden from the owner until reactivated."),
        Language.ar: ("تم تعليق عرضك على {project_title}", "قام مسؤول الموقع بتعليق عرضك — أصبح مخفيًا عن المالك حتى تتم إعادة تفعيله."),
    },
    NotificationType.offer_reactivated: {
        Language.en: ("Your offer on {project_title} was reactivated", "A site admin reactivated your offer."),
        Language.ar: ("تمت إعادة تفعيل عرضك على {project_title}", "قام مسؤول الموقع بإعادة تفعيل عرضك."),
    },
}


# Dedup policy (spec §2.10 "deduplicated"): if the recipient already has an
# UNREAD notification of the same type pointing at the same link, a new
# trigger of the same underlying event (e.g. a service provider revising their
# bid five times before the owner ever opens their inbox) doesn't pile up
# a fresh row each time — the existing one already says "you have
# something to check here." A new one is created only once that one has
# been read, or there was none to begin with.
def notify(db: Session, user: User, notification_type: NotificationType, link: str | None = None, **kwargs) -> Notification | None:
    template = _TEMPLATES.get(notification_type)
    if not template:
        return None
    title_fmt, body_fmt = template.get(user.language) or template[Language.en]
    title = title_fmt.format(**kwargs)
    body = body_fmt.format(**kwargs)

    existing = (
        db.query(Notification)
        .filter(
            Notification.user_id == user.id,
            Notification.type == notification_type,
            Notification.link == link,
            Notification.is_read.is_(False),
        )
        .first()
    )
    if existing:
        # Still one unread notice for this place -- but it says what the
        # latest event says (e.g. a scope change after a title fix), never a
        # stale earlier message.
        existing.title, existing.body = title, body
        existing.created_at = datetime.utcnow()
        db.commit()
        return existing

    row = Notification(user_id=user.id, type=notification_type, title=title, body=body, link=link)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row



def notify_team(
    db: Session, user: User | None, notification_type: NotificationType, link: str | None = None, organization_id: str | None = None, **kwargs
) -> None:
    """A tender notification for work done for an organization goes to every
    current member (services.team); for an individual's, to them."""
    from app.services.team import side_users

    for member in side_users(db, organization_id, user.id if user else None):
        notify(db, member, notification_type, link=link, **kwargs)
