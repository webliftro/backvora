"""Safe operational action registry for BackVora's in-app agent."""

from __future__ import annotations

from dataclasses import dataclass
from inspect import isawaitable
import re
from typing import Any, Awaitable, Callable, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import (
    AnchorText,
    Campaign,
    CampaignDomainExclusion,
    CampaignTarget,
    Contact,
    ContactForm,
    Domain,
    DomainStatus,
    LinkPrice,
    Order,
    OrderLink,
    TargetSite,
    TargetURL,
    User,
)
from ..services import adult_classifier
from .domain_filters import apply_domain_concept_filters

Permission = Literal["read", "mutate", "high_risk"]

FORBIDDEN_ACTION_TOKENS = (
    "shell", "exec", "eval", "python", "javascript", "sql", "deploy",
    "migration", "migrate", "systemd", "git", "file", "env", "secret",
)


class ActionExecutionError(Exception):
    """Raised when a registered action cannot complete."""


def _normalize_literal(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    return value


class DomainSearchArgs(BaseModel):
    query: str | None = Field(None, max_length=255)
    status: str | None = Field(None, max_length=50)
    adult: Literal["adult", "non_adult", "unknown"] | None = None
    min_dr: int | None = Field(None, ge=0)
    max_dr: int | None = Field(None, ge=0)
    min_traffic: int | None = Field(None, ge=0)
    max_traffic: int | None = Field(None, ge=0)
    limit: int = Field(20, ge=1, le=100)


class DomainIdArgs(BaseModel):
    domain_id: str | None = None
    domain: str | None = Field(None, max_length=255)


class DomainUpdateArgs(DomainIdArgs):
    status: str | None = Field(None, max_length=50)
    category: str | None = Field(None, max_length=100)
    tags: str | None = Field(None, max_length=500)
    notes: str | None = None
    is_adult: bool | None = None


class ContactUpsertArgs(BaseModel):
    domain_id: str | None = None
    domain: str | None = Field(None, max_length=255)
    contact_id: str | None = None
    email: str = Field(..., max_length=255)
    name: str | None = Field(None, max_length=255)
    role: str | None = Field(None, max_length=100)
    notes: str | None = None
    is_primary: bool | None = None


class LinkPriceUpsertArgs(BaseModel):
    domain_id: str | None = None
    domain: str | None = Field(None, max_length=255)
    price_id: str | None = None
    link_type: str = Field(..., min_length=1, max_length=100)
    price: float | None = None
    currency: str = Field("USD", max_length=3)
    duration_months: int | None = Field(None, ge=1, le=12)
    is_permanent: bool = False
    notes: str | None = None


class SummaryArgs(BaseModel):
    id: str | None = None
    query: str | None = Field(None, max_length=255)


class CampaignResearchArgs(BaseModel):
    target_site_query: str = Field(..., min_length=1, max_length=255)
    filter_niche_tags: str | None = Field(None, max_length=500)
    filter_link_type: str | None = Field(None, max_length=100)
    min_dr: int | None = Field(None, ge=0)
    min_traffic: int | None = Field(None, ge=0)
    limit_domains: int = Field(10, ge=1, le=50)
    limit_urls: int = Field(5, ge=1, le=20)


class CampaignCreateArgs(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    target_site: str | None = Field(None, max_length=255)
    target_site_id: str | None = None
    status: Literal["active", "paused", "completed"] = "active"
    budget: float | None = Field(None, ge=0)
    notes: str | None = None
    mode: Literal["manual", "auto"] = "manual"
    filter_traffic_min: int | None = Field(None, ge=0)
    filter_traffic_max: int | None = Field(None, ge=0)
    filter_dr_min: int | None = Field(None, ge=0)
    filter_dr_max: int | None = Field(None, ge=0)
    filter_price_min: float | None = Field(None, ge=0)
    filter_price_max: float | None = Field(None, ge=0)
    filter_niche_tags: str | None = Field(None, max_length=500)
    filter_link_type: str | None = Field(None, max_length=100)
    velocity_count: int | None = Field(None, ge=1)
    velocity_period_days: int | None = Field(None, ge=1)
    budget_total: float | None = Field(None, ge=0)
    schedule_enabled: bool | None = None
    schedule_interval_hours: int | None = Field(None, ge=1)

    @field_validator("status", "mode", mode="before")
    @classmethod
    def normalize_status_and_mode(cls, value: Any) -> Any:
        return _normalize_literal(value)


class CampaignUpdateArgs(BaseModel):
    campaign_id: str
    name: str | None = Field(None, min_length=1, max_length=255)
    target_site: str | None = Field(None, max_length=255)
    target_site_id: str | None = None
    status: Literal["active", "paused", "completed"] | None = None
    budget: float | None = Field(None, ge=0)
    notes: str | None = None
    mode: Literal["manual", "auto"] | None = None
    filter_traffic_min: int | None = Field(None, ge=0)
    filter_traffic_max: int | None = Field(None, ge=0)
    filter_dr_min: int | None = Field(None, ge=0)
    filter_dr_max: int | None = Field(None, ge=0)
    filter_price_min: float | None = Field(None, ge=0)
    filter_price_max: float | None = Field(None, ge=0)
    filter_niche_tags: str | None = Field(None, max_length=500)
    filter_link_type: str | None = Field(None, max_length=100)
    velocity_count: int | None = Field(None, ge=1)
    velocity_period_days: int | None = Field(None, ge=1)
    budget_total: float | None = Field(None, ge=0)
    schedule_enabled: bool | None = None
    schedule_interval_hours: int | None = Field(None, ge=1)

    @field_validator("status", "mode", mode="before")
    @classmethod
    def normalize_status_and_mode(cls, value: Any) -> Any:
        return _normalize_literal(value)


class CampaignCreateFromResearchArgs(BaseModel):
    target_site_query: str = Field(..., min_length=1, max_length=255)
    name: str | None = Field(None, max_length=255)
    status: Literal["active", "paused", "completed"] = "active"
    budget: float | None = Field(None, ge=0)
    notes: str | None = None
    mode: Literal["manual", "auto"] = "manual"
    filter_traffic_min: int | None = Field(None, ge=0)
    filter_traffic_max: int | None = Field(None, ge=0)
    filter_dr_min: int | None = Field(None, ge=0)
    filter_dr_max: int | None = Field(None, ge=0)
    filter_price_min: float | None = Field(None, ge=0)
    filter_price_max: float | None = Field(None, ge=0)
    filter_niche_tags: str | None = Field(None, max_length=500)
    filter_link_type: str | None = Field(None, max_length=100)
    velocity_count: int | None = Field(None, ge=1)
    velocity_period_days: int | None = Field(None, ge=1)
    budget_total: float | None = Field(None, ge=0)
    limit_target_urls: int = Field(5, ge=1, le=20)

    @field_validator("status", "mode", mode="before")
    @classmethod
    def normalize_status_and_mode(cls, value: Any) -> Any:
        return _normalize_literal(value)


class CampaignTargetCreateArgs(BaseModel):
    campaign_id: str
    url: str = Field(..., max_length=2000)
    brand_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=500)
    priority: int = Field(1, ge=1)


class OrderCreateArgs(BaseModel):
    campaign_id: str
    domain_id: str | None = None
    domain: str | None = Field(None, max_length=255)
    link_type: str = Field(..., min_length=1, max_length=100)
    price: float | None = Field(None, ge=0)
    currency: str = Field("USD", min_length=3, max_length=3)
    contact_id: str | None = None
    target_url: str | None = Field(None, max_length=2000)
    anchor_text: str | None = Field(None, max_length=500)
    anchor_type: str | None = Field(None, max_length=50)
    anchor_text_id: str | None = None
    article_content: str | None = None
    article_topic: str | None = Field(None, max_length=500)
    nofollow_target: bool | None = None
    nofollow_resources: bool | None = None
    skip_resource_links: bool | None = None
    max_words: int | None = Field(None, ge=300, le=5000)
    resource_links_count: int | None = Field(None, ge=0, le=20)
    brand_mentions_scope: str | None = Field(None, max_length=20)
    brand_mentions_brands: str | None = None
    brand_mentions_in_title: bool | None = None
    brand_mentions_body_count: int | None = Field(None, ge=0, le=20)


class OrderLinkCreateArgs(BaseModel):
    order_id: str
    target_url: str = Field(..., max_length=2000)
    anchor_text: str = Field(..., min_length=1, max_length=500)
    anchor_type: str | None = Field(None, max_length=50)
    anchor_text_id: str | None = None
    article_topic: str | None = Field(None, max_length=500)


class OrderIdArgs(BaseModel):
    order_id: str


class ArticleGenerationArgs(OrderIdArgs):
    skip_images: bool = False


class ArticleApprovalArgs(OrderIdArgs):
    modified: bool = False
    article_content: str | None = None


class VerifyOrderArgs(OrderIdArgs):
    url: str = Field(..., max_length=2000)
    deep: bool = False


class PaymentActionArgs(OrderIdArgs):
    notes: str | None = None


class ContactGrabArgs(DomainIdArgs):
    use_browser: bool = False


class ContactGrabMissingArgs(BaseModel):
    campaign_id: str | None = None
    campaign_query: str | None = Field(None, max_length=255)
    adult: bool = True
    missing_only: bool = True
    limit: int = Field(25, ge=1, le=100)
    use_browser: bool = False


class ContactFormSubmitArgs(DomainIdArgs):
    form_id: str | None = None
    template_id: str | None = None
    force_browser: bool = False


class ActionResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    message: str
    data: dict[str, Any] = Field(default_factory=dict)


ActionHandler = Callable[[Session, User, BaseModel], ActionResult | Awaitable[ActionResult]]


@dataclass(frozen=True)
class AgentAction:
    name: str
    description: str
    permission: Permission
    args_model: type[BaseModel]
    handler: ActionHandler
    requires_confirmation: bool = False

    def validate_args(self, raw_args: dict[str, Any]) -> BaseModel:
        try:
            return self.args_model.model_validate(raw_args)
        except ValidationError as exc:
            raise ActionExecutionError(str(exc)) from exc


class ActionRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, AgentAction] = {}

    def register(self, action: AgentAction) -> None:
        lowered = action.name.lower()
        if any(token in lowered for token in FORBIDDEN_ACTION_TOKENS):
            raise ValueError(f"Forbidden action name: {action.name}")
        if action.name in self._actions:
            raise ValueError(f"Duplicate action: {action.name}")
        self._actions[action.name] = action

    def get(self, name: str) -> AgentAction:
        try:
            return self._actions[name]
        except KeyError as exc:
            raise ActionExecutionError(f"Unknown action: {name}") from exc

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": action.name,
                "description": action.description,
                "permission": action.permission,
                "requires_confirmation": action.requires_confirmation,
            }
            for action in self._actions.values()
        ]


def _domain_payload(domain: Domain) -> dict[str, Any]:
    return {
        "id": domain.id,
        "domain": domain.domain,
        "status": domain.status.value if hasattr(domain.status, "value") else domain.status,
        "domain_rating": domain.domain_rating,
        "organic_traffic": domain.organic_traffic,
        "domain_niche": domain.domain_niche,
        "is_adult": domain.is_adult,
        "category": domain.category,
        "tags": domain.tags,
        "notes": domain.notes,
    }


def _resolve_domain(
    db: Session,
    args: DomainIdArgs | ContactUpsertArgs | LinkPriceUpsertArgs | OrderCreateArgs | ContactGrabArgs | ContactFormSubmitArgs,
) -> Domain:
    query = db.query(Domain).filter(Domain.deleted_at.is_(None))
    if getattr(args, "domain_id", None):
        domain = query.filter(Domain.id == args.domain_id).first()
    elif getattr(args, "domain", None):
        domain = query.filter(Domain.domain == args.domain.strip().lower()).first()
    else:
        raise ActionExecutionError("domain_id or domain is required")
    if not domain:
        raise ActionExecutionError("Domain not found")
    return domain


def _resolve_campaign(db: Session, campaign_id: str) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.deleted_at.is_(None)).first()
    if not campaign:
        raise ActionExecutionError("Campaign not found")
    return campaign


def _find_campaign(db: Session, campaign_id: str | None = None, query: str | None = None) -> Campaign | None:
    campaigns = db.query(Campaign).filter(Campaign.deleted_at.is_(None))
    if campaign_id:
        return campaigns.filter(Campaign.id == campaign_id).first()
    if query:
        return campaigns.filter(Campaign.name.ilike(f"%{query.strip()}%")).order_by(Campaign.created_at.desc()).first()
    return None


def _resolve_order(db: Session, order_id: str) -> Order:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ActionExecutionError("Order not found")
    return order


def _normalize_site_query(value: str) -> str:
    text = value.strip().lower()
    text = text.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return text.split("/", 1)[0].strip()


def _alias_matches_text(alias: str, text: str) -> bool:
    normalized = alias.strip().lower()
    if not normalized:
        return False
    if "." not in normalized and " " not in normalized and len(normalized) < 4:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text) is not None


def _resolve_target_site(db: Session, query: str) -> TargetSite:
    normalized = _normalize_site_query(query)
    candidates = db.query(TargetSite).filter(TargetSite.deleted_at.is_(None)).order_by(TargetSite.name.asc()).all()
    exact_matches = []
    for site in candidates:
        domain = _normalize_site_query(site.domain)
        names = [
            site.name.lower(),
            domain,
            domain.split(".", 1)[0],
            *(v.strip().lower() for v in (site.brand_variations or "").split(",") if v.strip()),
        ]
        if normalized in names or any(normalized and normalized == _normalize_site_query(name) for name in names):
            exact_matches.append(site)
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise ActionExecutionError(f"Target site is ambiguous for {query}")

    text_matches = []
    query_text = query.lower()
    for site in candidates:
        haystack = " ".join(
            part for part in (site.name, site.domain, site.brand_variations or "") if part
        ).lower()
        aliases = [
            site.name.lower(),
            _normalize_site_query(site.domain),
            _normalize_site_query(site.domain).split(".", 1)[0],
            *(v.strip().lower() for v in (site.brand_variations or "").split(",") if v.strip()),
        ]
        if any(_alias_matches_text(alias, query_text) for alias in aliases) or (
            normalized and _alias_matches_text(normalized, haystack)
        ):
            text_matches.append(site)
    if len(text_matches) == 1:
        return text_matches[0]
    if len(text_matches) > 1:
        raise ActionExecutionError(f"Target site is ambiguous for {query}")
    raise ActionExecutionError(f"Target site not found for {query}")


def _target_site_url_payload(db: Session, site: TargetSite, limit: int) -> list[dict[str, Any]]:
    urls = db.query(TargetURL).filter(
        TargetURL.site_id == site.id,
        TargetURL.deleted_at.is_(None),
    ).order_by(TargetURL.priority.desc()).limit(limit).all()
    items: list[dict[str, Any]] = []
    for url in urls:
        anchors = db.query(AnchorText).filter(
            AnchorText.target_url_id == url.id,
            AnchorText.deleted_at.is_(None),
        ).order_by(AnchorText.times_used.asc()).limit(10).all()
        items.append({
            "id": url.id,
            "url": url.url,
            "description": url.description,
            "priority": url.priority,
            "anchors": [
                {
                    "id": anchor.id,
                    "text": anchor.text,
                    "anchor_type": anchor.anchor_type,
                    "times_used": anchor.times_used,
                }
                for anchor in anchors
            ],
        })
    return items


def _candidate_domains_for_campaign(
    db: Session,
    args: CampaignResearchArgs | CampaignCreateFromResearchArgs,
) -> list[Domain]:
    query = db.query(Domain).filter(Domain.deleted_at.is_(None))
    query = apply_domain_concept_filters(query, args.filter_niche_tags)
    if args.filter_link_type:
        query = query.join(LinkPrice, LinkPrice.domain_id == Domain.id).filter(
            LinkPrice.deleted_at.is_(None),
            LinkPrice.link_type.ilike(f"%{args.filter_link_type}%"),
        ).distinct()
    min_dr = getattr(args, "min_dr", None)
    if min_dr is None:
        min_dr = getattr(args, "filter_dr_min", None)
    if min_dr is not None:
        query = query.filter(Domain.domain_rating >= min_dr)
    min_traffic = getattr(args, "min_traffic", None)
    if min_traffic is None:
        min_traffic = getattr(args, "filter_traffic_min", None)
    if min_traffic is not None:
        query = query.filter(Domain.organic_traffic >= min_traffic)
    limit = getattr(args, "limit_domains", 10)
    return query.order_by(Domain.organic_traffic.desc().nullslast()).limit(limit).all()


def _http_exc_to_action_error(exc: HTTPException) -> ActionExecutionError:
    return ActionExecutionError(str(exc.detail))


def _require_success(result: Any, action_label: str) -> None:
    if isinstance(result, dict) and result.get("success") is False:
        reason = result.get("error") or result.get("reason") or result.get("message") or "operation failed"
        raise ActionExecutionError(f"{action_label} failed: {reason}")


def search_domains(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = args if isinstance(args, DomainSearchArgs) else DomainSearchArgs.model_validate(args)
    query = db.query(Domain).filter(Domain.deleted_at.is_(None))
    if data.query:
        term = f"%{data.query.strip()}%"
        query = query.filter(or_(Domain.domain.ilike(term), Domain.notes.ilike(term), Domain.tags.ilike(term)))
    if data.status:
        try:
            query = query.filter(Domain.status == DomainStatus(data.status))
        except ValueError as exc:
            raise ActionExecutionError(f"Invalid status: {data.status}") from exc
    if data.adult:
        query = query.filter(Domain.domain_niche == data.adult)
    if data.min_dr is not None:
        query = query.filter(Domain.domain_rating >= data.min_dr)
    if data.max_dr is not None:
        query = query.filter(Domain.domain_rating <= data.max_dr)
    if data.min_traffic is not None:
        query = query.filter(Domain.organic_traffic >= data.min_traffic)
    if data.max_traffic is not None:
        query = query.filter(Domain.organic_traffic <= data.max_traffic)
    items = query.order_by(Domain.organic_traffic.desc().nullslast()).limit(data.limit).all()
    return ActionResult(
        message=f"Found {len(items)} domain(s).",
        data={"items": [_domain_payload(domain) for domain in items]},
    )


def get_domain_detail(db: Session, _user: User, args: BaseModel) -> ActionResult:
    domain = _resolve_domain(db, DomainIdArgs.model_validate(args.model_dump()))
    return ActionResult(
        message=f"Loaded {domain.domain}.",
        data={
            "domain": _domain_payload(domain),
            "contacts": [
                {"id": c.id, "email": c.email, "name": c.name, "role": c.role, "is_primary": c.is_primary}
                for c in domain.contacts if c.deleted_at is None
            ],
            "link_prices": [
                {
                    "id": p.id, "link_type": p.link_type, "price": p.price,
                    "currency": p.currency, "duration_months": p.duration_months,
                    "is_permanent": p.is_permanent,
                }
                for p in domain.link_prices if p.deleted_at is None
            ],
        },
    )


def update_domain(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = DomainUpdateArgs.model_validate(args.model_dump())
    domain = _resolve_domain(db, data)
    if data.status is not None:
        try:
            domain.status = DomainStatus(data.status)
        except ValueError as exc:
            raise ActionExecutionError(f"Invalid status: {data.status}") from exc
    for field in ("category", "tags", "notes", "is_adult"):
        value = getattr(data, field)
        if value is not None:
            setattr(domain, field, value)
    if data.is_adult is not None:
        domain.domain_niche = adult_classifier.NICHE_ADULT if data.is_adult else adult_classifier.NICHE_NON_ADULT
        domain.adult_method = "agent"
    db.flush()
    return ActionResult(message=f"Updated {domain.domain}.", data={"domain": _domain_payload(domain)})


def upsert_contact(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = ContactUpsertArgs.model_validate(args.model_dump())
    domain = _resolve_domain(db, data)
    contact = None
    if data.contact_id:
        contact = db.query(Contact).filter(Contact.id == data.contact_id, Contact.deleted_at.is_(None)).first()
    if contact is None:
        contact = db.query(Contact).filter(
            Contact.domain_id == domain.id,
            Contact.email == data.email,
            Contact.deleted_at.is_(None),
        ).first()
    created = contact is None
    if contact is None:
        contact = Contact(domain_id=domain.id, email=data.email)
        db.add(contact)
    for field in ("name", "role", "notes", "is_primary"):
        value = getattr(data, field)
        if value is not None:
            setattr(contact, field, value)
    db.flush()
    return ActionResult(
        message=("Created" if created else "Updated") + f" contact for {domain.domain}.",
        data={"contact": {"id": contact.id, "domain_id": contact.domain_id, "email": contact.email}},
    )


def upsert_link_price(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = LinkPriceUpsertArgs.model_validate(args.model_dump())
    domain = _resolve_domain(db, data)
    price = None
    if data.price_id:
        price = db.query(LinkPrice).filter(LinkPrice.id == data.price_id, LinkPrice.deleted_at.is_(None)).first()
    if price is None:
        price = db.query(LinkPrice).filter(
            LinkPrice.domain_id == domain.id,
            LinkPrice.link_type == data.link_type,
            LinkPrice.deleted_at.is_(None),
        ).first()
    created = price is None
    if price is None:
        price = LinkPrice(domain_id=domain.id, link_type=data.link_type)
        db.add(price)
    price.price = data.price
    price.currency = data.currency.upper()
    price.is_permanent = data.is_permanent
    price.duration_months = None if data.is_permanent else data.duration_months
    price.notes = data.notes
    db.flush()
    return ActionResult(
        message=("Created" if created else "Updated") + f" {price.link_type} price for {domain.domain}.",
        data={"link_price": {"id": price.id, "domain_id": price.domain_id, "price": price.price}},
    )


def classify_domain(db: Session, _user: User, args: BaseModel) -> ActionResult:
    domain = _resolve_domain(db, DomainIdArgs.model_validate(args.model_dump()))
    verdict = adult_classifier.classify_signals(domain.domain)
    adult_classifier.apply_verdict_to_domain(domain, verdict)
    db.flush()
    return ActionResult(message=f"Classified {domain.domain} as {domain.domain_niche}.", data={"domain": _domain_payload(domain)})


def research_campaign(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = CampaignResearchArgs.model_validate(args.model_dump())
    site = _resolve_target_site(db, data.target_site_query)
    urls = _target_site_url_payload(db, site, data.limit_urls)
    domains = _candidate_domains_for_campaign(db, data)
    return ActionResult(
        message=(
            f"Researched {site.name} ({site.domain}): "
            f"{len(urls)} target URL(s), {len(domains)} candidate domain(s)."
        ),
        data={
            "target_site": {
                "id": site.id,
                "domain": site.domain,
                "name": site.name,
                "brand_variations": site.brand_variations,
                "anchor_distribution": {
                    "brand": site.anchor_brand_pct,
                    "generic": site.anchor_generic_pct,
                    "topical": site.anchor_topical_pct,
                    "exact": site.anchor_exact_pct,
                    "url": site.anchor_url_pct,
                },
            },
            "target_urls": urls,
            "candidate_domains": [_domain_payload(domain) for domain in domains],
            "recommended_campaign_args": {
                "target_site_query": site.name,
                "filter_niche_tags": data.filter_niche_tags,
                "filter_link_type": data.filter_link_type,
                "limit_target_urls": data.limit_urls,
            },
        },
    )


def create_campaign(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = CampaignCreateArgs.model_validate(args.model_dump())
    target_site = data.target_site
    target_site_obj = None
    if data.target_site_id:
        target_site_obj = db.query(TargetSite).filter(TargetSite.id == data.target_site_id).first()
        if not target_site_obj:
            raise ActionExecutionError("Target site not found")
        target_site = target_site or target_site_obj.domain
    if not target_site:
        raise ActionExecutionError("target_site or target_site_id is required")

    campaign = Campaign(
        name=data.name,
        target_site=target_site,
        target_site_id=data.target_site_id,
        status=data.status,
        budget=data.budget,
        notes=data.notes,
        mode=data.mode,
        filter_traffic_min=data.filter_traffic_min,
        filter_traffic_max=data.filter_traffic_max,
        filter_dr_min=data.filter_dr_min,
        filter_dr_max=data.filter_dr_max,
        filter_price_min=data.filter_price_min,
        filter_price_max=data.filter_price_max,
        filter_niche_tags=data.filter_niche_tags,
        filter_link_type=data.filter_link_type,
        budget_total=data.budget_total,
    )
    if data.velocity_count is not None:
        campaign.velocity_count = data.velocity_count
    if data.velocity_period_days is not None:
        campaign.velocity_period_days = data.velocity_period_days
    if data.schedule_enabled is not None:
        campaign.schedule_enabled = data.schedule_enabled
    if data.schedule_interval_hours is not None:
        campaign.schedule_interval_hours = data.schedule_interval_hours
    if target_site_obj:
        campaign.anchor_brand_pct = target_site_obj.anchor_brand_pct
        campaign.anchor_generic_pct = target_site_obj.anchor_generic_pct
        campaign.anchor_topical_pct = target_site_obj.anchor_topical_pct
        campaign.anchor_exact_pct = target_site_obj.anchor_exact_pct

    db.add(campaign)
    db.flush()
    return ActionResult(
        message=f"Created campaign {campaign.name}.",
        data={"campaign": {"id": campaign.id, "name": campaign.name, "target_site": campaign.target_site}},
    )


def update_campaign(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = args if isinstance(args, CampaignUpdateArgs) else CampaignUpdateArgs.model_validate(args.model_dump())
    campaign = _resolve_campaign(db, data.campaign_id)
    updates = data.model_dump(exclude_unset=True, exclude={"campaign_id"})
    if not updates:
        raise ActionExecutionError("No campaign fields provided to update")

    if data.target_site_id:
        target_site = db.query(TargetSite).filter(TargetSite.id == data.target_site_id).first()
        if not target_site:
            raise ActionExecutionError("Target site not found")
        updates.setdefault("target_site", target_site.domain)
        campaign.anchor_brand_pct = target_site.anchor_brand_pct
        campaign.anchor_generic_pct = target_site.anchor_generic_pct
        campaign.anchor_topical_pct = target_site.anchor_topical_pct
        campaign.anchor_exact_pct = target_site.anchor_exact_pct

    for field, value in updates.items():
        setattr(campaign, field, value)

    db.flush()

    from ..services.scheduler import add_campaign_job, remove_campaign_job
    if campaign.mode == "auto" and campaign.schedule_enabled and campaign.status == "active":
        add_campaign_job(campaign.id, campaign.schedule_interval_hours or 6)
    else:
        remove_campaign_job(campaign.id)

    return ActionResult(
        message=f"Updated campaign {campaign.name}.",
        data={
            "campaign": {
                "id": campaign.id,
                "name": campaign.name,
                "target_site": campaign.target_site,
                "target_site_id": campaign.target_site_id,
                "status": campaign.status,
                "mode": campaign.mode,
                "filter_niche_tags": campaign.filter_niche_tags,
                "filter_link_type": campaign.filter_link_type,
                "filter_dr_min": campaign.filter_dr_min,
                "filter_traffic_min": campaign.filter_traffic_min,
            }
        },
    )


def create_campaign_from_research(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = CampaignCreateFromResearchArgs.model_validate(args.model_dump())
    site = _resolve_target_site(db, data.target_site_query)
    urls = _target_site_url_payload(db, site, data.limit_target_urls)
    campaign = Campaign(
        name=data.name or f"{site.name} Link Building",
        target_site=site.domain,
        target_site_id=site.id,
        status=data.status,
        budget=data.budget,
        notes=data.notes,
        mode=data.mode,
        filter_traffic_min=data.filter_traffic_min,
        filter_traffic_max=data.filter_traffic_max,
        filter_dr_min=data.filter_dr_min,
        filter_dr_max=data.filter_dr_max,
        filter_price_min=data.filter_price_min,
        filter_price_max=data.filter_price_max,
        filter_niche_tags=data.filter_niche_tags,
        filter_link_type=data.filter_link_type,
        budget_total=data.budget_total,
        anchor_brand_pct=site.anchor_brand_pct,
        anchor_generic_pct=site.anchor_generic_pct,
        anchor_topical_pct=site.anchor_topical_pct,
        anchor_exact_pct=site.anchor_exact_pct,
    )
    if data.velocity_count is not None:
        campaign.velocity_count = data.velocity_count
    if data.velocity_period_days is not None:
        campaign.velocity_period_days = data.velocity_period_days
    db.add(campaign)
    db.flush()

    targets = []
    for item in urls:
        target = CampaignTarget(
            campaign_id=campaign.id,
            url=item["url"],
            brand_name=site.name,
            description=item.get("description"),
            priority=item.get("priority") or 1,
        )
        db.add(target)
        db.flush()
        targets.append({
            "id": target.id,
            "url": target.url,
            "brand_name": target.brand_name,
            "description": target.description,
            "priority": target.priority,
        })

    domains = _candidate_domains_for_campaign(db, data)
    return ActionResult(
        message=(
            f"Created campaign {campaign.name} for {site.domain} "
            f"with {len(targets)} researched target URL(s)."
        ),
        data={
            "campaign": {
                "id": campaign.id,
                "name": campaign.name,
                "target_site": campaign.target_site,
                "target_site_id": campaign.target_site_id,
                "mode": campaign.mode,
                "filter_niche_tags": campaign.filter_niche_tags,
                "filter_link_type": campaign.filter_link_type,
            },
            "targets": targets,
            "candidate_domains": [_domain_payload(domain) for domain in domains],
        },
    )


def create_campaign_target(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = CampaignTargetCreateArgs.model_validate(args.model_dump())
    campaign = _resolve_campaign(db, data.campaign_id)
    target = CampaignTarget(
        campaign_id=campaign.id,
        url=data.url,
        brand_name=data.brand_name,
        description=data.description,
        priority=data.priority,
    )
    db.add(target)
    db.flush()
    return ActionResult(
        message=f"Added {target.brand_name} target to {campaign.name}.",
        data={"target": {"id": target.id, "campaign_id": campaign.id, "url": target.url, "brand_name": target.brand_name}},
    )


def _classify_order_anchor(db: Session, campaign: Campaign, target_url: str | None, anchor_text: str | None) -> str | None:
    if not anchor_text:
        return None
    try:
        from ..routers.target_sites import classify_anchor
    except Exception:
        return None
    brand_name = ""
    site_domain = campaign.target_site or ""
    brand_variations: list[str] = []
    if campaign.target_site_id:
        site = db.query(TargetSite).filter(TargetSite.id == campaign.target_site_id).first()
        if site:
            brand_name = site.name
            site_domain = site.domain
            brand_variations = [v.strip() for v in (site.brand_variations or "").split(",") if v.strip()]
    return classify_anchor(anchor_text, brand_name, site_domain, target_url or "", brand_variations)


def create_order(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = OrderCreateArgs.model_validate(args.model_dump())
    campaign = _resolve_campaign(db, data.campaign_id)
    domain = _resolve_domain(db, data)

    contact_id = data.contact_id
    if contact_id:
        contact = db.query(Contact).filter(
            Contact.id == contact_id,
            Contact.domain_id == domain.id,
            Contact.deleted_at.is_(None),
        ).first()
        if not contact:
            raise ActionExecutionError("Contact not found for domain")

    anchor_text = data.anchor_text
    anchor_type = data.anchor_type
    target_url = data.target_url
    if data.anchor_text_id:
        pool_anchor = db.query(AnchorText).filter(AnchorText.id == data.anchor_text_id).first()
        if not pool_anchor:
            raise ActionExecutionError("Anchor text not found")
        anchor_text = anchor_text or pool_anchor.text
        anchor_type = anchor_type or pool_anchor.anchor_type
        if not target_url:
            target = db.query(TargetURL).filter(TargetURL.id == pool_anchor.target_url_id).first()
            target_url = target.url if target else None
        pool_anchor.times_used = (pool_anchor.times_used or 0) + 1
    if not anchor_type:
        anchor_type = _classify_order_anchor(db, campaign, target_url, anchor_text)

    order = Order(
        campaign_id=campaign.id,
        domain_id=domain.id,
        contact_id=contact_id,
        link_type=data.link_type,
        price=data.price,
        currency=data.currency.upper(),
        target_url=target_url,
        anchor_text=anchor_text,
        anchor_type=anchor_type,
        anchor_text_id=data.anchor_text_id,
        article_content=data.article_content,
        article_topic=data.article_topic,
    )
    for field in (
        "nofollow_target",
        "nofollow_resources",
        "skip_resource_links",
        "max_words",
        "resource_links_count",
        "brand_mentions_scope",
        "brand_mentions_brands",
        "brand_mentions_in_title",
        "brand_mentions_body_count",
    ):
        value = getattr(data, field)
        if value is not None:
            setattr(order, field, value)
    db.add(order)
    if data.price:
        campaign.spent = (campaign.spent or 0) + data.price
    db.flush()
    return ActionResult(
        message=f"Created {order.link_type} order for {domain.domain}.",
        data={"order": {"id": order.id, "campaign_id": campaign.id, "domain_id": domain.id, "status": order.status}},
    )


def create_order_link(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = OrderLinkCreateArgs.model_validate(args.model_dump())
    order = _resolve_order(db, data.order_id)
    if data.anchor_text_id:
        pool_anchor = db.query(AnchorText).filter(AnchorText.id == data.anchor_text_id).first()
        if not pool_anchor:
            raise ActionExecutionError("Anchor text not found")
        pool_anchor.times_used = (pool_anchor.times_used or 0) + 1
    anchor_type = data.anchor_type
    if not anchor_type:
        campaign = _resolve_campaign(db, order.campaign_id)
        anchor_type = _classify_order_anchor(db, campaign, data.target_url, data.anchor_text)
    if data.article_topic is not None:
        order.article_topic = data.article_topic
    max_slot = max((link.slot or 0) for link in order.links) if order.links else 0
    link = OrderLink(
        order_id=order.id,
        target_url=data.target_url,
        anchor_text=data.anchor_text,
        anchor_type=anchor_type,
        anchor_text_id=data.anchor_text_id,
        slot=max_slot + 1,
    )
    db.add(link)
    db.flush()
    return ActionResult(
        message=f"Added link slot {link.slot} to order {order.id}.",
        data={"link": {"id": link.id, "order_id": order.id, "slot": link.slot}},
    )


async def grab_contacts_for_domain(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = ContactGrabArgs.model_validate(args.model_dump())
    domain = _resolve_domain(db, data)
    from ..services.scraper import ContactsGrabber

    try:
        result = await ContactsGrabber().grab_all(domain.domain, use_browser=data.use_browser)
    except Exception as exc:
        raise ActionExecutionError(str(exc)) from exc

    saved = _save_contact_grab_result(db, domain, result)
    db.flush()
    return ActionResult(
        message=f"Grabbed contacts for {domain.domain}: saved {saved['contacts_added']} contact(s).",
        data={"domain_id": domain.id, "saved": saved, "result": result},
    )


def _save_contact_grab_result(db: Session, domain: Domain, result: dict[str, Any]) -> dict[str, Any]:
    contacts_added = 0
    contacts_seen = 0
    forms_detected = 0
    socials = result.get("socials") or {}
    names = result.get("names") or []
    has_primary_contact = db.query(Contact.id).filter(
        Contact.domain_id == domain.id,
        Contact.deleted_at.is_(None),
        Contact.is_primary.is_(True),
    ).first() is not None

    for email_info in result.get("emails") or []:
        email = (email_info.get("email") or "").strip().lower()
        if not email:
            continue
        contacts_seen += 1
        contact = db.query(Contact).filter(
            Contact.domain_id == domain.id,
            Contact.email == email,
        ).first()
        if contact is None:
            contact = Contact(
                domain_id=domain.id,
                email=email,
                source_page=email_info.get("source_url"),
                source_type=email_info.get("source_type"),
                is_primary=not has_primary_contact,
            )
            has_primary_contact = True
            if names:
                contact.name = names[0].get("name")
                contact.role = names[0].get("role")
            db.add(contact)
            contacts_added += 1
        elif contact.deleted_at is not None:
            contact.deleted_at = None
            contact.is_primary = not has_primary_contact
            has_primary_contact = has_primary_contact or bool(contact.is_primary)
            contacts_added += 1
        if names and not contact.name:
            contact.name = names[0].get("name")
        if names and not contact.role:
            contact.role = names[0].get("role")
        if socials.get("twitter") and not contact.social_twitter:
            contact.social_twitter = socials["twitter"][0]
        if socials.get("linkedin") and not contact.social_linkedin:
            contact.social_linkedin = socials["linkedin"][0]
        if socials.get("telegram") and not contact.social_telegram:
            contact.social_telegram = socials["telegram"][0]
        if not domain.email:
            domain.email = email
        if names and not domain.owner:
            domain.owner = names[0].get("name")

    for form_info in result.get("forms") or []:
        existing = db.query(ContactForm).filter(
            ContactForm.domain_id == domain.id,
            ContactForm.form_url == form_info.get("form_url"),
            ContactForm.form_action == form_info.get("form_action"),
        ).first()
        if existing:
            continue
        db.add(ContactForm(
            domain_id=domain.id,
            form_url=form_info.get("form_url"),
            form_action=form_info.get("form_action"),
            form_method=form_info.get("form_method") or "post",
            fields_json=form_info.get("fields") or [],
            has_captcha=form_info.get("has_captcha", False),
            captcha_type=form_info.get("captcha_type", "none"),
            captcha_site_key=form_info.get("captcha_site_key"),
        ))
        forms_detected += 1

    return {
        "contacts_seen": contacts_seen,
        "contacts_added": contacts_added,
        "forms_detected": forms_detected,
    }


async def grab_missing_contacts(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = ContactGrabMissingArgs.model_validate(args.model_dump())
    campaign = _find_campaign(db, data.campaign_id, data.campaign_query)
    if (data.campaign_id or data.campaign_query) and not campaign:
        raise ActionExecutionError("Campaign not found")

    query = db.query(Domain).filter(Domain.deleted_at.is_(None))
    if data.adult:
        query = query.filter(Domain.domain_niche == "adult")
    if campaign:
        query = apply_domain_concept_filters(query, campaign.filter_niche_tags)
        ordered_domain_ids = db.query(Order.domain_id).filter(
            Order.campaign_id == campaign.id,
            Order.domain_id.isnot(None),
            Order.deleted_at.is_(None),
        ).distinct()
        excluded_domain_ids = db.query(CampaignDomainExclusion.domain_id).filter(
            CampaignDomainExclusion.campaign_id == campaign.id,
            CampaignDomainExclusion.deleted_at.is_(None),
        ).distinct()
        query = query.filter(
            Domain.id.notin_(ordered_domain_ids),
            Domain.id.notin_(excluded_domain_ids),
        )
        if campaign.filter_traffic_min is not None:
            query = query.filter(Domain.organic_traffic >= campaign.filter_traffic_min)
        if campaign.filter_traffic_max is not None:
            query = query.filter(Domain.organic_traffic <= campaign.filter_traffic_max)
        if campaign.filter_dr_min is not None:
            query = query.filter(Domain.domain_rating >= campaign.filter_dr_min)
        if campaign.filter_dr_max is not None:
            query = query.filter(Domain.domain_rating <= campaign.filter_dr_max)

    if data.missing_only:
        domains_with_contacts = db.query(Contact.domain_id).filter(Contact.deleted_at.is_(None)).distinct()
        query = query.filter(
            Domain.id.notin_(domains_with_contacts),
            or_(Domain.email.is_(None), Domain.email == ""),
        )

    domains = query.order_by(Domain.organic_traffic.desc().nullslast()).limit(data.limit).all()
    if not domains:
        return ActionResult(
            message="No matching domains are missing contacts.",
            data={"processed": 0, "contacts_added": 0, "forms_detected": 0, "results": []},
        )

    from ..services.scraper import ContactsGrabber

    grabber = ContactsGrabber()
    results: list[dict[str, Any]] = []
    total_contacts = 0
    total_forms = 0
    for domain in domains:
        try:
            result = await grabber.grab_all(domain.domain, use_browser=data.use_browser)
        except Exception as exc:
            results.append({
                "domain_id": domain.id,
                "domain": domain.domain,
                "success": False,
                "error": str(exc),
            })
            continue
        saved = _save_contact_grab_result(db, domain, result)
        total_contacts += saved["contacts_added"]
        total_forms += saved["forms_detected"]
        results.append({
            "domain_id": domain.id,
            "domain": domain.domain,
            "success": True,
            **saved,
        })

    return ActionResult(
        message=f"Processed {len(domains)} domain(s), saved {total_contacts} contact(s).",
        data={
            "campaign": {"id": campaign.id, "name": campaign.name} if campaign else None,
            "processed": len(domains),
            "contacts_added": total_contacts,
            "forms_detected": total_forms,
            "results": results,
        },
    )


async def grab_publisher_rules_for_domain(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = DomainIdArgs.model_validate(args.model_dump())
    domain = _resolve_domain(db, data)
    from ..routers.campaigns import grab_publisher_rules
    try:
        result = await grab_publisher_rules(domain.id, db=db)
    except HTTPException as exc:
        raise _http_exc_to_action_error(exc) from exc
    return ActionResult(
        message=f"Grabbed publisher rules for {domain.domain}.",
        data={"domain_id": domain.id, "result": result},
    )


async def submit_contact_form_for_domain(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = ContactFormSubmitArgs.model_validate(args.model_dump())
    domain = _resolve_domain(db, data)
    from ..routers.contacts import submit_form
    try:
        result = await submit_form(
            domain.id,
            form_id=data.form_id,
            template_id=data.template_id,
            force_browser=data.force_browser,
            db=db,
        )
    except HTTPException as exc:
        raise _http_exc_to_action_error(exc) from exc
    _require_success(result, "Contact form submission")
    return ActionResult(
        message=f"Submitted contact form for {domain.domain}.",
        data={"domain_id": domain.id, "result": result},
    )


async def generate_order_article(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = ArticleGenerationArgs.model_validate(args.model_dump())
    _resolve_order(db, data.order_id)
    from ..services.article_writer import generate_article
    try:
        result = await generate_article(data.order_id, db, skip_images=data.skip_images)
    except ValueError as exc:
        raise ActionExecutionError(str(exc)) from exc
    return ActionResult(
        message=f"Generated article for order {data.order_id}.",
        data={"order_id": data.order_id, "result": result},
    )


async def approve_order_article(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = ArticleApprovalArgs.model_validate(args.model_dump())
    order = _resolve_order(db, data.order_id)
    if data.article_content is not None:
        order.article_content = data.article_content
        db.flush()
    from ..services.campaign_autopilot import handle_article_approval
    result = await handle_article_approval(data.order_id, approved=True, modified=data.modified, db=db)
    _require_success(result, "Article approval")
    return ActionResult(
        message=f"Approved article for order {data.order_id}.",
        data={"order_id": data.order_id, "result": result},
    )


async def reject_order_article(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = OrderIdArgs.model_validate(args.model_dump())
    _resolve_order(db, data.order_id)
    from ..services.campaign_autopilot import handle_article_approval
    result = await handle_article_approval(data.order_id, approved=False, modified=False, db=db)
    _require_success(result, "Article rejection")
    return ActionResult(
        message=f"Rejected article for order {data.order_id}.",
        data={"order_id": data.order_id, "result": result},
    )


async def send_order_email(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = OrderIdArgs.model_validate(args.model_dump())
    _resolve_order(db, data.order_id)
    from ..services.order_sender import send_order
    try:
        result = await send_order(data.order_id, db)
    except ValueError as exc:
        raise ActionExecutionError(str(exc)) from exc
    _require_success(result, "Order send")
    return ActionResult(
        message=f"Sent order {data.order_id} to publisher.",
        data={"order_id": data.order_id, "result": result},
    )


async def verify_order_live_url(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = VerifyOrderArgs.model_validate(args.model_dump())
    _resolve_order(db, data.order_id)
    from ..services.link_monitor import deep_verify_live_url, verify_live_url
    try:
        result = await (
            deep_verify_live_url(data.order_id, data.url, db)
            if data.deep
            else verify_live_url(data.order_id, data.url, db)
        )
    except ValueError as exc:
        raise ActionExecutionError(str(exc)) from exc
    return ActionResult(
        message=f"Verified order {data.order_id}.",
        data={"order_id": data.order_id, "result": result},
    )


async def mark_order_payment_sent(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = PaymentActionArgs.model_validate(args.model_dump())
    from ..routers.orders import MarkPaymentSentRequest, mark_payment_sent
    try:
        result = await mark_payment_sent(data.order_id, MarkPaymentSentRequest(notes=data.notes), db=db)
    except HTTPException as exc:
        raise _http_exc_to_action_error(exc) from exc
    _require_success(result, "Mark payment sent")
    return ActionResult(
        message=f"Marked payment sent for order {data.order_id}.",
        data={"order_id": data.order_id, "result": result},
    )


async def confirm_order_payment(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = PaymentActionArgs.model_validate(args.model_dump())
    from ..routers.orders import ConfirmPaymentRequest, confirm_payment
    try:
        result = await confirm_payment(data.order_id, ConfirmPaymentRequest(notes=data.notes), db=db)
    except HTTPException as exc:
        raise _http_exc_to_action_error(exc) from exc
    _require_success(result, "Payment confirmation")
    return ActionResult(
        message=f"Confirmed payment for order {data.order_id}.",
        data={"order_id": data.order_id, "result": result},
    )


def summarize_campaign(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = SummaryArgs.model_validate(args.model_dump())
    query = db.query(Campaign).filter(Campaign.deleted_at.is_(None))
    campaign = query.filter(Campaign.id == data.id).first() if data.id else None
    if campaign is None and data.query:
        campaign = query.filter(Campaign.name.ilike(f"%{data.query}%")).first()
    if not campaign:
        raise ActionExecutionError("Campaign not found")
    return ActionResult(
        message=f"{campaign.name}: {campaign.status}, spent {campaign.spent or campaign.budget_spent or 0}.",
        data={
            "campaign": {
                "id": campaign.id, "name": campaign.name, "status": campaign.status,
                "target_site": campaign.target_site, "budget": campaign.budget,
                "orders": len(campaign.orders),
            }
        },
    )


def summarize_order(db: Session, _user: User, args: BaseModel) -> ActionResult:
    data = SummaryArgs.model_validate(args.model_dump())
    order = db.query(Order).filter(Order.id == data.id).first() if data.id else None
    if not order:
        raise ActionExecutionError("Order not found")
    return ActionResult(
        message=f"Order {order.id}: {order.status} {order.link_type} on {order.domain.domain if order.domain else order.domain_id}.",
        data={
            "order": {
                "id": order.id, "status": order.status, "link_type": order.link_type,
                "price": order.price, "currency": order.currency,
                "domain": order.domain.domain if order.domain else None,
                "target_url": order.target_url,
            }
        },
    )


registry = ActionRegistry()
registry.register(AgentAction("domain.search", "Search/list domains", "read", DomainSearchArgs, search_domains))
registry.register(AgentAction("domain.detail", "Get domain details", "read", DomainIdArgs, get_domain_detail))
registry.register(AgentAction("domain.update", "Update safe editable domain fields", "mutate", DomainUpdateArgs, update_domain))
registry.register(AgentAction("contact.upsert", "Create or update a contact", "mutate", ContactUpsertArgs, upsert_contact))
registry.register(AgentAction("link_price.upsert", "Create or update link pricing", "mutate", LinkPriceUpsertArgs, upsert_link_price))
registry.register(AgentAction("domain.classify_adult", "Run cached adult signal classification", "mutate", DomainIdArgs, classify_domain))
registry.register(AgentAction("campaign.research", "Research target site URLs, anchors, and candidate domains for a campaign", "read", CampaignResearchArgs, research_campaign))
registry.register(AgentAction("campaign.create", "Create a link-building campaign", "mutate", CampaignCreateArgs, create_campaign))
registry.register(AgentAction("campaign.update", "Update an existing campaign, including domain filters like adult directory/topsite constraints", "mutate", CampaignUpdateArgs, update_campaign))
registry.register(AgentAction("campaign.create_from_research", "Create a campaign after resolving a target site and adding researched target URLs", "mutate", CampaignCreateFromResearchArgs, create_campaign_from_research))
registry.register(AgentAction("campaign.target.create", "Add a target URL/brand to a campaign", "mutate", CampaignTargetCreateArgs, create_campaign_target))
registry.register(AgentAction("campaign.summary", "Summarize a campaign", "read", SummaryArgs, summarize_campaign))
registry.register(AgentAction("order.create", "Create a publisher order in a campaign", "mutate", OrderCreateArgs, create_order))
registry.register(AgentAction("order.link.create", "Add a link slot to an order", "mutate", OrderLinkCreateArgs, create_order_link))
registry.register(AgentAction("order.summary", "Summarize an order", "read", SummaryArgs, summarize_order))
registry.register(AgentAction("contact.grab", "Grab and save emails/socials/forms for one domain", "mutate", ContactGrabArgs, grab_contacts_for_domain))
registry.register(AgentAction("contact.grab_missing", "Bulk grab and save contacts for domains missing contact info, optionally scoped to a campaign", "mutate", ContactGrabMissingArgs, grab_missing_contacts))
registry.register(AgentAction("publisher_rules.grab", "Extract publisher rules from known replies", "mutate", DomainIdArgs, grab_publisher_rules_for_domain))
registry.register(AgentAction(
    "order.generate_article",
    "Generate content for an order",
    "high_risk",
    ArticleGenerationArgs,
    generate_order_article,
    requires_confirmation=True,
))
registry.register(AgentAction(
    "order.approve_article",
    "Approve generated article and continue the order flow",
    "high_risk",
    ArticleApprovalArgs,
    approve_order_article,
    requires_confirmation=True,
))
registry.register(AgentAction(
    "order.reject_article",
    "Reject generated article",
    "high_risk",
    OrderIdArgs,
    reject_order_article,
    requires_confirmation=True,
))
registry.register(AgentAction(
    "order.send",
    "Send an order email to the publisher",
    "high_risk",
    OrderIdArgs,
    send_order_email,
    requires_confirmation=True,
))
registry.register(AgentAction(
    "order.verify_live",
    "Verify a published order live URL",
    "high_risk",
    VerifyOrderArgs,
    verify_order_live_url,
    requires_confirmation=True,
))
registry.register(AgentAction(
    "order.mark_payment_sent",
    "Mark payment sent and notify the publisher",
    "high_risk",
    PaymentActionArgs,
    mark_order_payment_sent,
    requires_confirmation=True,
))
registry.register(AgentAction(
    "order.confirm_payment",
    "Confirm payment and run related notifications/verification",
    "high_risk",
    PaymentActionArgs,
    confirm_order_payment,
    requires_confirmation=True,
))
registry.register(AgentAction(
    "contact_form.submit",
    "Submit an outreach contact form",
    "high_risk",
    ContactFormSubmitArgs,
    submit_contact_form_for_domain,
    requires_confirmation=True,
))


async def execute_registered_action(db: Session, user: User, action_name: str, args: dict[str, Any]) -> tuple[AgentAction, ActionResult]:
    action = registry.get(action_name)
    parsed = action.validate_args(args)
    result = action.handler(db, user, parsed)
    if isawaitable(result):
        result = await result
    return action, result


def require_known_action(action_name: str) -> AgentAction:
    try:
        return registry.get(action_name)
    except ActionExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
