"""
SQLAlchemy ORM models for the link builder.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, 
    ForeignKey, Boolean, Enum as SQLEnum, JSON
)
from sqlalchemy.orm import relationship
import enum

from .database import Base


def generate_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid4())


class DomainStatus(enum.Enum):
    """Status of a domain in our pipeline."""
    NEW = "new"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    SCRAPING = "scraping"
    SCRAPED = "scraped"
    CONTACTED = "contacted"
    REPLIED = "replied"
    NEGOTIATING = "negotiating"
    DEAL_CLOSED = "deal_closed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLACKLISTED = "blacklisted"


class OutreachStatus(enum.Enum):
    """Status of an outreach attempt."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENT = "sent"
    OPENED = "opened"
    REPLIED = "replied"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete


class User(TimestampMixin, Base):
    """Application user for authentication."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)


class Domain(TimestampMixin, Base):
    """
    A domain we're tracking for link building.
    Could be a competitor or a potential link source.
    """
    __tablename__ = "domains"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    
    # Ahrefs metrics
    domain_rating = Column(Integer, nullable=True)
    organic_traffic = Column(Integer, nullable=True)
    referring_domains = Column(Integer, nullable=True)
    backlinks_count = Column(Integer, nullable=True)
    
    # Classification
    is_competitor = Column(Boolean, default=False)
    is_adult = Column(Boolean, default=True)
    category = Column(String(100), nullable=True)  # Single category
    tags = Column(String(500), nullable=True)  # Comma-separated tags
    niche_tags = Column(String(500), nullable=True)  # Legacy - comma-separated
    
    # Status
    status = Column(SQLEnum(DomainStatus), default=DomainStatus.NEW)
    last_analyzed_at = Column(DateTime, nullable=True)

    # Payment agreement — set True when publisher insists on upfront and we've agreed (e.g. PayPal buyer protection)
    accepts_upfront_payment = Column(Boolean, default=False, nullable=False)
    
    # Contact info
    owner = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    telegram = Column(String(255), nullable=True)
    
    # Content requirements
    language = Column(String(50), nullable=True, default="English")  # Language for articles on this domain
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Relationships
    contacts = relationship("Contact", back_populates="domain", cascade="all, delete-orphan")
    backlinks = relationship("Backlink", back_populates="source_domain", 
                            foreign_keys="Backlink.source_domain_id")
    link_prices = relationship("LinkPrice", back_populates="domain", cascade="all, delete-orphan")
    payment_methods = relationship("DomainPaymentMethod", back_populates="domain", cascade="all, delete-orphan")


class Contact(TimestampMixin, Base):
    """
    A contact person/email at a domain.
    """
    __tablename__ = "contacts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=False)
    
    # Contact info
    email = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    role = Column(String(100), nullable=True)  # owner, webmaster, editor, etc.
    
    # Social
    social_twitter = Column(String(500), nullable=True)
    social_linkedin = Column(String(500), nullable=True)
    social_telegram = Column(String(500), nullable=True)
    
    # Source
    source_page = Column(String(500), nullable=True)  # URL where we found the email
    source_type = Column(String(50), nullable=True)  # contact_page, privacy, whois, etc.
    
    # Validation
    is_valid = Column(Boolean, nullable=True)  # Email validation result
    is_primary = Column(Boolean, default=False)  # Primary contact for this domain
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Relationships
    domain = relationship("Domain", back_populates="contacts")
    outreach_messages = relationship("OutreachMessage", back_populates="contact")


class Backlink(TimestampMixin, Base):
    """
    A backlink relationship between domains.
    Used for competitor analysis.
    """
    __tablename__ = "backlinks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    
    # The domain giving the link
    source_domain_id = Column(String(36), ForeignKey("domains.id"), nullable=False)
    source_url = Column(String(2000), nullable=True)
    
    # The domain receiving the link (competitor)
    target_domain = Column(String(255), nullable=False, index=True)
    target_url = Column(String(2000), nullable=True)
    
    # Link attributes
    anchor_text = Column(String(500), nullable=True)
    is_dofollow = Column(Boolean, default=True)
    is_image = Column(Boolean, default=False)
    
    # Ahrefs metrics
    domain_rating = Column(Integer, nullable=True)
    url_rating = Column(Integer, nullable=True)
    traffic = Column(Integer, nullable=True)
    
    # Dates
    first_seen = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    
    # Relationships
    source_domain = relationship("Domain", back_populates="backlinks",
                                foreign_keys=[source_domain_id])


class OutreachCampaign(TimestampMixin, Base):
    """
    An outreach campaign grouping multiple messages.
    """
    __tablename__ = "outreach_campaigns"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Template
    subject_template = Column(String(500), nullable=True)
    body_template = Column(Text, nullable=True)
    
    # Stats
    total_sent = Column(Integer, default=0)
    total_opened = Column(Integer, default=0)
    total_replied = Column(Integer, default=0)
    
    # Relationships
    messages = relationship("OutreachMessage", back_populates="campaign")


class OutreachMessage(TimestampMixin, Base):
    """
    An individual outreach message sent to a contact.
    """
    __tablename__ = "outreach_messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    campaign_id = Column(String(36), ForeignKey("outreach_campaigns.id"), nullable=True)
    contact_id = Column(String(36), ForeignKey("contacts.id"), nullable=False)
    
    # Message content
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    
    # Status tracking
    status = Column(SQLEnum(OutreachStatus), default=OutreachStatus.DRAFT)
    sent_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    
    # Follow-up
    follow_up_count = Column(Integer, default=0)
    next_follow_up_at = Column(DateTime, nullable=True)
    
    # Relationships
    campaign = relationship("OutreachCampaign", back_populates="messages")
    contact = relationship("Contact", back_populates="outreach_messages")


class LinkPrice(TimestampMixin, Base):
    """
    A link pricing option for a domain.
    Each domain can have multiple link types with different prices/durations.
    """
    __tablename__ = "link_prices"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=False)
    
    # Link type (e.g., "Guest Post", "Link Insert", "Homepage Link", etc.)
    link_type = Column(String(100), nullable=False)
    
    # Pricing
    price = Column(Float, nullable=True)
    currency = Column(String(3), default="USD")
    
    # Duration: months (3-12) or permanent
    duration_months = Column(Integer, nullable=True)  # null if permanent
    is_permanent = Column(Boolean, default=False)
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Relationships
    domain = relationship("Domain", back_populates="link_prices")


class DomainPaymentMethod(TimestampMixin, Base):
    """
    A payment method accepted by a domain owner.
    Multiple per domain, one marked as preferred.
    """
    __tablename__ = "domain_payment_methods"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=False)
    method = Column(String(50), nullable=False)  # paypal, wire_transfer, paxum, crypto
    details = Column(Text, nullable=True)  # e.g. PayPal email, wallet address
    is_preferred = Column(Boolean, default=False)

    domain = relationship("Domain", back_populates="payment_methods")


class Deal(TimestampMixin, Base):
    """
    A link purchase deal being negotiated.
    """
    __tablename__ = "deals"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=False)
    contact_id = Column(String(36), ForeignKey("contacts.id"), nullable=True)
    
    # Deal details
    link_type = Column(String(50), nullable=True)  # guest_post, link_insert, homepage, etc.
    target_url = Column(String(2000), nullable=True)  # URL we want link to
    anchor_text = Column(String(255), nullable=True)
    
    # Pricing
    asking_price = Column(Float, nullable=True)
    offered_price = Column(Float, nullable=True)
    final_price = Column(Float, nullable=True)
    currency = Column(String(3), default="USD")
    
    # Status
    status = Column(String(50), default="negotiating")  # negotiating, agreed, paid, live, cancelled
    
    # Dates
    agreed_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    live_at = Column(DateTime, nullable=True)
    
    # Verification
    live_url = Column(String(2000), nullable=True)  # Actual URL where link is placed
    is_verified = Column(Boolean, default=False)
    
    # Notes
    notes = Column(Text, nullable=True)


class ContactForm(TimestampMixin, Base):
    """Detected contact form on a domain."""
    __tablename__ = "contact_forms"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=False)
    form_url = Column(String(2000), nullable=False)
    form_action = Column(String(2000), nullable=True)
    form_method = Column(String(10), default="POST")
    fields_json = Column(JSON, nullable=True)  # list of {name, type, required, label}
    last_submitted_at = Column(DateTime, nullable=True)
    submission_status = Column(String(50), nullable=True)  # pending, success, failed
    has_captcha = Column(Boolean, default=False, nullable=False)
    captcha_type = Column(String(50), nullable=True)  # recaptcha_v2, recaptcha_v3, hcaptcha, none
    captcha_site_key = Column(Text, nullable=True)  # reCAPTCHA/hCaptcha site key

    domain = relationship("Domain")


class SentEmail(TimestampMixin, Base):
    """Emails sent via BackVora."""
    __tablename__ = "sent_emails"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    to_email = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=True)
    contact_id = Column(String(36), ForeignKey("contacts.id"), nullable=True)
    sent_at = Column(DateTime, nullable=False)
    message_id = Column(String(500), nullable=True)


class OutreachTemplate(TimestampMixin, Base):
    """Outreach email/form template."""
    __tablename__ = "outreach_templates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    subject_template = Column(String(500), nullable=True)
    body_template = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)


class Campaign(TimestampMixin, Base):
    """Link building campaign - groups orders and tracks progress."""
    __tablename__ = "campaigns"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)  # e.g. "CamHours Growth Q1"
    target_site = Column(String(255), nullable=False)  # e.g. "camhours.com" (legacy)
    target_site_id = Column(String(36), ForeignKey("target_sites.id"), nullable=True)  # link to TargetSite
    status = Column(String(50), default="active")  # active, paused, completed
    budget = Column(Float, nullable=True)
    spent = Column(Float, default=0)
    notes = Column(Text, nullable=True)
    
    # Anchor text distribution defaults for guest posts (percentages)
    anchor_brand_pct = Column(Integer, default=60)
    anchor_generic_pct = Column(Integer, default=20)
    anchor_topical_pct = Column(Integer, default=15)
    anchor_exact_pct = Column(Integer, default=5)
    
    # Mode: manual (default) or auto
    mode = Column(String(20), default="manual")  # manual, auto

    # Domain filters (for auto mode domain selection)
    filter_traffic_min = Column(Integer, nullable=True)
    filter_traffic_max = Column(Integer, nullable=True)
    filter_dr_min = Column(Integer, nullable=True)
    filter_dr_max = Column(Integer, nullable=True)
    filter_price_min = Column(Float, nullable=True)
    filter_price_max = Column(Float, nullable=True)
    filter_niche_tags = Column(String(500), nullable=True)  # comma-separated
    filter_link_type = Column(String(100), nullable=True)  # Guest Post, Header, etc.

    # Link velocity
    velocity_count = Column(Integer, default=1)
    velocity_period_days = Column(Integer, default=7)
    last_order_sent_at = Column(DateTime, nullable=True)

    # Budget
    budget_total = Column(Float, nullable=True)
    budget_spent = Column(Float, default=0.0)

    # Self-learning approval
    approval_mode = Column(String(20), default="review")  # review, auto
    consecutive_approvals = Column(Integer, default=0)
    approval_threshold = Column(Integer, default=10)

    # Link rel attribute defaults for new orders
    nofollow_target = Column(Boolean, default=False, nullable=False)  # Default nofollow on target links
    nofollow_resources = Column(Boolean, default=False, nullable=False)  # Default nofollow ugc on resource links
    skip_resource_links = Column(Boolean, default=False, nullable=False)  # Don't include resource links
    
    # Schedule
    schedule_enabled = Column(Boolean, default=False)
    schedule_interval_hours = Column(Integer, default=6)

    targets = relationship("CampaignTarget", back_populates="campaign", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="campaign", cascade="all, delete-orphan")


class CampaignTarget(TimestampMixin, Base):
    """Target URL for a campaign - what we're building links to."""
    __tablename__ = "campaign_targets"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False)
    url = Column(String(2000), nullable=False)  # e.g. "https://camhours.com/girls"
    brand_name = Column(String(255), nullable=False)  # e.g. "CamHours"
    description = Column(String(500), nullable=True)  # for toplist descriptors
    priority = Column(Integer, default=1)  # higher = more links to this URL
    
    campaign = relationship("Campaign", back_populates="targets")


class PublisherRules(TimestampMixin, Base):
    """Per-domain publisher rules, extracted from email replies or manually set."""
    __tablename__ = "publisher_rules"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=False, unique=True)
    max_urls = Column(Integer, nullable=True)  # max URLs allowed per article
    cross_domain = Column(Boolean, nullable=True)  # allow links to different domains?
    we_write = Column(Boolean, nullable=True)  # do we provide the article?
    min_words = Column(Integer, nullable=True)
    max_words = Column(Integer, nullable=True)  # max word count for articles
    link_attribute = Column(String(50), nullable=True)  # dofollow, nofollow, sponsored, or null
    max_images = Column(Integer, nullable=True)  # max images allowed per article
    image_count = Column(Integer, nullable=True)  # recommended/required number of images
    resource_links_count = Column(Integer, nullable=True)  # number of resource/authority links allowed
    skip_resource_links = Column(Boolean, nullable=True)  # publisher forbids outbound links to other sites
    brand_mentions_scope = Column(String(20), nullable=True)  # any, all
    brand_mentions_brands = Column(Text, nullable=True)  # comma-separated brand names to enforce specifically
    brand_mentions_in_title = Column(Boolean, nullable=True)  # require brand mention in title
    brand_mentions_body_count = Column(Integer, nullable=True)  # per-brand mention count in body
    content_guidelines = Column(Text, nullable=True)
    placement_notes = Column(Text, nullable=True)
    
    domain = relationship("Domain")


class Order(TimestampMixin, Base):
    """A link purchase order - tracks the full lifecycle."""
    __tablename__ = "orders"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=False)
    contact_id = Column(String(36), ForeignKey("contacts.id"), nullable=True)
    
    # What we're buying
    link_type = Column(String(100), nullable=False)  # Guest Post, Header, etc.
    price = Column(Float, nullable=True)
    currency = Column(String(3), default="USD")
    
    # Content (for guest posts)
    target_url = Column(String(2000), nullable=True)
    anchor_text = Column(String(255), nullable=True)
    anchor_type = Column(String(50), nullable=True)  # brand, generic, topical, exact
    anchor_text_id = Column(String(36), ForeignKey("anchor_texts.id"), nullable=True)  # link to AnchorText pool
    article_content = Column(Text, nullable=True)
    article_topic = Column(String(500), nullable=True)  # User-specified topic/angle for article generation
    
    # Link rel attributes
    nofollow_target = Column(Boolean, default=False, nullable=False)  # Add rel="nofollow" to our money links
    nofollow_resources = Column(Boolean, default=False, nullable=False)  # Add rel="nofollow ugc" to authority/resource links
    skip_resource_links = Column(Boolean, default=False, nullable=False)  # Don't include any resource/authority links
    max_words = Column(Integer, nullable=True)  # Max word count for generated article (None = default 1200)
    resource_links_count = Column(Integer, nullable=True)  # Number of resource/authority links (None = default 2-3)
    brand_mentions_scope = Column(String(20), nullable=True)  # any, all
    brand_mentions_brands = Column(Text, nullable=True)  # comma-separated brand names to enforce specifically
    brand_mentions_in_title = Column(Boolean, nullable=True)  # require brand mention in title
    brand_mentions_body_count = Column(Integer, nullable=True)  # per-brand mention count in body
    
    # Placement
    live_url = Column(String(2000), nullable=True)  # URL where our link was placed
    
    # Status: draft → content_ready → sent → published → paid → live → offline
    # For upfront-payment publishers: any status → payment_sent → (resumes normal flow)
    status = Column(String(50), default="draft")
    paid_at = Column(DateTime, nullable=True)
    payment_sent_at = Column(DateTime, nullable=True)
    live_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    last_check_status = Column(String(50), nullable=True)  # ok, removed, anchor_changed
    
    campaign = relationship("Campaign", back_populates="orders")
    domain = relationship("Domain")
    contact = relationship("Contact")
    links = relationship("OrderLink", back_populates="order", cascade="all, delete-orphan")


class TargetSite(TimestampMixin, Base):
    """A site we're building links to (top-level, campaign-independent)."""
    __tablename__ = "target_sites"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    domain = Column(String(255), nullable=False, unique=True)  # e.g. "camhours.com"
    name = Column(String(255), nullable=False)  # e.g. "CamHours"
    brand_variations = Column(Text, nullable=True)  # comma-separated: "Cam Hours, cam hours, CAMHOURS"
    notes = Column(Text, nullable=True)
    
    # Anchor distribution targets (percentages)
    anchor_brand_pct = Column(Integer, default=60)
    anchor_generic_pct = Column(Integer, default=10)
    anchor_topical_pct = Column(Integer, default=20)
    anchor_exact_pct = Column(Integer, default=5)
    anchor_url_pct = Column(Integer, default=5)
    
    urls = relationship("TargetURL", back_populates="site", cascade="all, delete-orphan")


class TargetURL(TimestampMixin, Base):
    """A specific URL on a target site that we want links pointing to."""
    __tablename__ = "target_urls"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    site_id = Column(String(36), ForeignKey("target_sites.id"), nullable=False)
    url = Column(String(2000), nullable=False)
    description = Column(String(500), nullable=True)  # e.g. "Girls category page"
    priority = Column(Integer, default=1)  # higher = more links
    
    site = relationship("TargetSite", back_populates="urls")
    anchors = relationship("AnchorText", back_populates="target_url", cascade="all, delete-orphan")


class AnchorText(TimestampMixin, Base):
    """An anchor text option for a target URL."""
    __tablename__ = "anchor_texts"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    target_url_id = Column(String(36), ForeignKey("target_urls.id"), nullable=False)
    text = Column(String(500), nullable=False)
    anchor_type = Column(String(50), nullable=False)  # brand, topical, generic, exact, url
    times_used = Column(Integer, default=0)  # how many orders use this anchor
    
    target_url = relationship("TargetURL", back_populates="anchors")


class OrderLink(TimestampMixin, Base):
    """A single link placement within an order (guest post can have multiple)."""
    __tablename__ = "order_links"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False)
    target_url = Column(String(2000), nullable=False)
    anchor_text = Column(String(500), nullable=False)
    anchor_type = Column(String(50), nullable=True)  # brand, topical, generic, exact, url
    anchor_text_id = Column(String(36), ForeignKey("anchor_texts.id"), nullable=True)
    slot = Column(Integer, default=1)  # position/order
    
    order = relationship("Order", back_populates="links")


class LinkCheck(TimestampMixin, Base):
    """Link monitoring check results."""
    __tablename__ = "link_checks"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False)
    checked_at = Column(DateTime, nullable=False)
    status = Column(String(50), nullable=False)  # ok, removed, anchor_changed, error
    http_status = Column(Integer, nullable=True)
    found_anchor = Column(String(255), nullable=True)
    found_url = Column(String(2000), nullable=True)
    notes = Column(Text, nullable=True)
    
    order = relationship("Order")


class ArticleTopic(TimestampMixin, Base):
    """Article topics to prevent duplicate content angles."""
    __tablename__ = "article_topics"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=False)
    title = Column(Text, nullable=False)
    topic_summary = Column(Text, nullable=True)  # 1-2 sentence summary of the angle
    
    order = relationship("Order")
    domain = relationship("Domain")


class ReceivedEmail(TimestampMixin, Base):
    """Incoming emails matched to tracked domains."""
    __tablename__ = "received_emails"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=True)
    contact_id = Column(String(36), ForeignKey("contacts.id"), nullable=True)
    from_addr = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    body_text = Column(Text, nullable=True)
    received_at = Column(DateTime, nullable=True)
    imap_uid = Column(String(100), nullable=True)
    parsed_data = Column(JSON, nullable=True)  # Full Claude parse result
    processing_status = Column(String(50), default="processed")  # processed, skipped, error
    processing_notes = Column(Text, nullable=True)  # Why it was skipped, error details, etc.
    message_id = Column(String(500), nullable=True)

    domain = relationship("Domain")
    contact = relationship("Contact")
