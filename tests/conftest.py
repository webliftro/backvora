"""Shared fixtures for BackVora tests."""

import os
import sys
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch settings BEFORE importing any backend modules
_test_settings_patch = patch.dict(os.environ, {
    "DATABASE_URL": "sqlite:///:memory:",
    "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test/webhook",
    "SMTP_HOST": "smtp.test.com",
    "SMTP_PORT": "465",
    "EMAIL_ACCOUNT": "test@test.com",
    "EMAIL_PASSWORD": "testpass",
    "ANTHROPIC_API_KEY": "sk-test",
    "IMAP_HOST": "imap.test.com",
    "IMAP_PORT": "993",
})
_test_settings_patch.start()

from backend.database import Base
from backend.models import (
    Order, Domain, OrderLink, Campaign, Contact, LinkCheck,
    DomainPaymentMethod, DomainStatus, LinkPrice, SentEmail,
)


@pytest.fixture
def db():
    """In-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_domain(db):
    """A sample domain."""
    d = Domain(
        id="dom-1",
        domain="example.com",
        domain_rating=45,
        organic_traffic=5000,
        status=DomainStatus.DEAL_CLOSED,
        email="pub@example.com",
        owner="John Publisher",
    )
    db.add(d)
    db.commit()
    return d


@pytest.fixture
def sample_campaign(db):
    """A sample campaign."""
    c = Campaign(
        id="camp-1",
        name="Test Campaign",
        target_site="mysite.com",
        status="active",
    )
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def sample_order(db, sample_domain, sample_campaign):
    """A sample order with links."""
    o = Order(
        id="order-1",
        campaign_id=sample_campaign.id,
        domain_id=sample_domain.id,
        link_type="Guest Post",
        price=100,
        currency="USD",
        target_url="https://mysite.com/page",
        anchor_text="my site",
        article_content="This is a test article with enough words to count. " * 20,
        status="sent",
    )
    db.add(o)
    db.commit()

    ol1 = OrderLink(
        id="ol-1",
        order_id=o.id,
        target_url="https://mysite.com/page",
        anchor_text="my site",
        slot=1,
    )
    ol2 = OrderLink(
        id="ol-2",
        order_id=o.id,
        target_url="https://mysite.com/other",
        anchor_text="click here",
        slot=2,
    )
    db.add_all([ol1, ol2])
    db.commit()
    return o


@pytest.fixture
def sample_contact(db, sample_domain):
    """A sample contact."""
    c = Contact(
        id="contact-1",
        domain_id=sample_domain.id,
        email="pub@example.com",
        name="John Publisher",
        is_primary=True,
    )
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def sample_payment_method(db, sample_domain):
    """A sample payment method."""
    pm = DomainPaymentMethod(
        id="pm-1",
        domain_id=sample_domain.id,
        method="PayPal",
        details="pub@example.com",
        is_preferred=True,
    )
    db.add(pm)
    db.commit()
    return pm


def make_html(links=None, text="", images=0):
    """Helper to build test HTML pages.
    
    links: list of (href, anchor_text, rel) tuples
    text: body text content
    images: number of <img> tags
    """
    parts = ["<html><body>"]
    if text:
        parts.append(f"<p>{text}</p>")
    if links:
        for href, anchor, rel in links:
            rel_attr = f' rel="{rel}"' if rel else ""
            parts.append(f'<a href="{href}"{rel_attr}>{anchor}</a>')
    for i in range(images):
        parts.append(f'<img src="image{i}.jpg" />')
    parts.append("</body></html>")
    return "\n".join(parts)
