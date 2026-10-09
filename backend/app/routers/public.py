import logging
import time
from decimal import Decimal

import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.award_record import AwardRecord
from app.models.cms_content import CmsContent
from app.models.service_provider import ServiceProviderProfile
from app.models.document import DocumentRequirement
from app.models.enums import Language, ProjectStatus, SubscriptionStatus, UserRole, VerificationStatus
from app.models.project import Project
from app.schemas.cms import PublicPlanPriceOut, PublicPricingOut, PublicRequirementOut, PublicStatsOut
from app.services import stripe_service  # noqa: F401 -- sets stripe.api_key

router = APIRouter(prefix="/public", tags=["public"])
logger = logging.getLogger("public")

# Fallback marketing copy shown until an admin edits it via /admin/cms —
# this is default UI copy, not fabricated data (see /public/stats below for
# the real, DB-derived numbers spec §14 requires).
DEFAULT_CMS: dict[str, dict[str, str]] = {
    "hero_heading": {"en": "Post a project. Get real offers.", "ar": "انشر مشروعك واحصل على عروض حقيقية."},
    "hero_subheading": {
        "en": "U-Tender connects owners with verified service providers — drawings in, offers out.",
        "ar": "يربط U-Tender الملاك بمزوّدي خدمات موثقين — المخططات تدخل، والعروض تخرج.",
    },
    "how_it_works_title": {"en": "How it works", "ar": "كيف يعمل"},
    "how_it_works_body": {
        "en": "Owners post a project with drawings and a bid deadline. Verified, subscribed service providers submit offers. The owner picks a winner and rates the work when it's done.",
        "ar": "ينشر الملاك مشروعًا مع المخططات وموعد نهائي لتقديم العروض. يقدم مزوّدو الخدمات الموثقون والمشتركون عروضهم. يختار المالك الفائز ويقيّم العمل عند الانتهاء.",
    },
    # ---- "Which side are you on?" role section on the homepage, plus the
    # one-line role explanations on the signup form. Facts that change on
    # their own — the verification document checklist and subscription
    # prices — are deliberately NOT part of this copy: the homepage renders
    # them live from /public/requirements and /public/pricing underneath
    # the matching text, so editing a requirement or a Stripe price can
    # never leave stale numbers or document names in the marketing copy.
    "home_roles_heading": {"en": "Which side are you on?", "ar": "إلى أي جانب تنتمي؟"},
    "home_roles_intro": {
        "en": "U-Tender is a tender marketplace with two sides. Owners publish a requirement with drawings and a deadline; verified service providers compete by submitting offers. Each account is one or the other — pick the one that describes you.",
        "ar": "U-Tender سوق مناقصات له جانبان. ينشر الملاك متطلبًا مع المخططات وموعد نهائي، ويتنافس مزوّدو الخدمات الموثقون بتقديم عروضهم. كل حساب إما مالك أو مزوّد خدمة — اختر ما يصفك.",
    },
    "home_owner_title": {"en": "Owner", "ar": "مالك"},
    "home_owner_who": {
        "en": "You are a landowner, project owner, buyer or organization with work that needs doing, and you want service providers to send you offers.",
        "ar": "أنت مالك أرض أو صاحب مشروع أو مشترٍ أو جهة لديها عمل تريد تنفيذه، وتريد أن يرسل لك مزوّدو الخدمات عروضهم.",
    },
    "home_owner_step_1": {"en": "Create a requirement (drawings, scope, deadline)", "ar": "أنشئ متطلبًا (المخططات، نطاق العمل، الموعد النهائي)"},
    "home_owner_step_2": {"en": "Receive offers from verified service providers", "ar": "استلم العروض من مزوّدي خدمات موثقين"},
    "home_owner_step_3": {"en": "Evaluate and compare the offers", "ar": "قيّم العروض وقارن بينها"},
    "home_owner_step_4": {"en": "Select the service provider you want", "ar": "اختر مزوّد الخدمة الذي تريده"},
    "home_owner_after": {
        "en": "Upload the verification documents listed below. Our team reviews them; once approved you can publish requirements.",
        "ar": "ارفع مستندات التحقق المذكورة أدناه. يراجعها فريقنا، وبعد الموافقة يمكنك نشر المتطلبات.",
    },
    "home_owner_cost": {"en": "Free for owners — no subscription.", "ar": "مجاني للملاك — بدون اشتراك."},
    "home_owner_cta": {"en": "Sign up as an Owner", "ar": "سجّل كمالك"},
    "home_provider_title": {"en": "Service provider", "ar": "مزوّد خدمة"},
    "home_provider_who": {
        "en": "You are a contractor, company or other service provider looking for projects to price and win.",
        "ar": "أنت مقاول أو شركة أو أي مزوّد خدمة يبحث عن مشاريع لتسعيرها والفوز بها.",
    },
    "home_provider_step_1": {"en": "Discover open requirements", "ar": "اكتشف المتطلبات المفتوحة"},
    "home_provider_step_2": {"en": "Review the drawings and scope", "ar": "راجع المخططات ونطاق العمل"},
    "home_provider_step_3": {"en": "Submit your offer before the deadline", "ar": "قدّم عرضك قبل الموعد النهائي"},
    "home_provider_step_4": {"en": "Win the project", "ar": "افز بالمشروع"},
    "home_provider_after": {
        "en": "Upload the company verification documents listed below. Once our team approves them you can browse open requirements.",
        "ar": "ارفع مستندات التحقق الخاصة بشركتك المذكورة أدناه. بعد موافقة فريقنا يمكنك تصفح المتطلبات المفتوحة.",
    },
    "home_provider_cost": {
        "en": "Signing up and verification are free, but a paid subscription is required to open full drawings and submit offers. No commission on awarded work.",
        "ar": "التسجيل والتحقق مجانيان، لكن يلزم اشتراك مدفوع لفتح المخططات الكاملة وتقديم العروض. بلا عمولة على المشاريع المرساة.",
    },
    "home_provider_cta": {"en": "Sign up as a Service provider", "ar": "سجّل كمزوّد خدمة"},
    "signup_owner_hint": {
        "en": "You have a requirement and want to receive offers. Free — you'll upload your verification documents next.",
        "ar": "لديك متطلب وتريد استلام العروض. مجاني — سترفع مستندات التحقق في الخطوة التالية.",
    },
    "signup_provider_hint": {
        "en": "You want to find requirements and submit offers. Next you'll tell us whether you work as an individual or for a company, and verify it; submitting offers needs a paid subscription.",
        "ar": "تريد إيجاد المتطلبات وتقديم العروض. ستخبرنا بعد ذلك هل تعمل بصفتك الفردية أم لصالح شركة، ثم تتحقق من ذلك؛ تقديم العروض يتطلب اشتراكًا مدفوعًا.",
    },
    # Stage 9.13: how a customer reaches the U-Tender team (an email, phone or
    # WhatsApp number), shown wherever the app says "contact support" --
    # verification rejected, account suspended, billing unavailable or failing.
    # Empty until an admin sets it (Admin -> Content); never a made-up address.
    "support_contact": {"en": "", "ar": ""},
}


@router.get("/cms")
def public_cms(language: Language = Language.en, db: Session = Depends(get_db)) -> dict[str, str]:
    rows = db.query(CmsContent).filter(CmsContent.language == language).all()
    content = {k: v[language.value] for k, v in DEFAULT_CMS.items()}
    for row in rows:
        content[row.key] = row.value
    return content


@router.get("/stats", response_model=PublicStatsOut)
def public_stats(db: Session = Depends(get_db)) -> PublicStatsOut:
    open_tenders = db.query(Project).filter(Project.status == ProjectStatus.open).count()

    # Mirrors ServiceProviderProfile.is_verified_active exactly — the single
    # source of truth for marketplace activation (spec P0 rule) — so this
    # count can never drift from what "verified_active" actually means
    # elsewhere in the app.
    verified_service_providers = (
        db.query(ServiceProviderProfile)
        .filter(
            ServiceProviderProfile.is_suspended.is_(False),
            ServiceProviderProfile.verification_status == VerificationStatus.approved,
            or_(
                ServiceProviderProfile.subscription_status.in_([SubscriptionStatus.active, SubscriptionStatus.trialing]),
                ServiceProviderProfile.payment_override_active.is_(True),
            ),
        )
        .count()
    )

    awarded_projects = db.query(AwardRecord).count()
    total_awarded_value = db.query(func.coalesce(func.sum(AwardRecord.amount), 0)).scalar()

    return PublicStatsOut(
        open_tenders=open_tenders,
        verified_service_providers=verified_service_providers,
        awarded_projects=awarded_projects,
        total_awarded_value=total_awarded_value,
    )


@router.get("/requirements", response_model=list[PublicRequirementOut])
def public_requirements(role: UserRole, db: Session = Depends(get_db)) -> list[DocumentRequirement]:
    """The live verification checklist for a self-registering role — the same
    active rows /owner/requirements and /service-provider/requirements hand an
    account after signup, so the homepage can tell a visitor exactly what
    they'll be asked for before they register."""
    if role == UserRole.admin:
        raise HTTPException(status_code=400, detail="Only owner or service provider checklists are public.")
    return (
        db.query(DocumentRequirement)
        .filter(DocumentRequirement.is_active.is_(True), DocumentRequirement.applies_to == role)
        .order_by(DocumentRequirement.created_at.asc())
        .all()
    )


# Stripe amounts are in the currency's minor unit; most currencies have two
# decimals, but not all (https://docs.stripe.com/currencies#zero-decimal).
_ZERO_DECIMAL = {"bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf"}
_THREE_DECIMAL = {"bhd", "jod", "kwd", "omr", "tnd"}

_PRICING_TTL_SECONDS = 600
_PRICING_FAILURE_TTL_SECONDS = 60
_pricing_cache: tuple[float, PublicPricingOut] | None = None


def _plan_price(plan: str, price_id: str) -> PublicPlanPriceOut:
    price = stripe.Price.retrieve(price_id)
    currency = price["currency"].lower()
    decimals = 0 if currency in _ZERO_DECIMAL else 3 if currency in _THREE_DECIMAL else 2
    recurring = price.get("recurring") or {}
    return PublicPlanPriceOut(
        plan=plan,
        amount=Decimal(price["unit_amount"]) / (Decimal(10) ** decimals),
        currency=currency,
        interval=recurring.get("interval") or ("year" if plan == "annual" else "month"),
        interval_count=recurring.get("interval_count") or 1,
    )


def _load_pricing() -> PublicPricingOut:
    settings = get_settings()
    configured = [
        (plan, price_id)
        for plan, price_id in (("monthly", settings.stripe_price_id_monthly), ("annual", settings.stripe_price_id_annual))
        if price_id
    ]
    if not settings.stripe_secret_key or not configured:
        return PublicPricingOut(plans=[])
    return PublicPricingOut(plans=[_plan_price(plan, price_id) for plan, price_id in configured])


@router.get("/pricing", response_model=PublicPricingOut)
def public_pricing() -> PublicPricingOut:
    """The service-provider subscription packages, read from the same Stripe
    prices checkout charges (STRIPE_PRICE_ID_MONTHLY / _ANNUAL) — the single
    source of truth for every price shown in the app. Cached briefly so a
    busy homepage doesn't call Stripe on every view. An empty `plans` list
    means billing isn't configured or Stripe couldn't be reached."""
    global _pricing_cache
    now = time.monotonic()
    if _pricing_cache and _pricing_cache[0] > now:
        return _pricing_cache[1]
    try:
        pricing = _load_pricing()
        ttl = _PRICING_TTL_SECONDS
    except Exception:
        logger.exception("could not load subscription prices from Stripe")
        pricing = PublicPricingOut(plans=[])
        ttl = _PRICING_FAILURE_TTL_SECONDS
    _pricing_cache = (now + ttl, pricing)
    return pricing
