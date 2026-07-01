"""Preview email that would be sent (without actually sending)"""
from backend.database import SessionLocal
from backend.models import Order, Domain, Contact, OrderLink, PublisherRules, Campaign
from backend.services.order_sender import get_contact_email

db = SessionLocal()

order_id = "07846548-9678-4edc-8e1b-553c57723ef1"
order = db.query(Order).filter(Order.id == order_id).first()
domain = db.query(Domain).filter(Domain.id == order.domain_id).first()
campaign = db.query(Campaign).filter(Campaign.id == order.campaign_id).first()

print("=" * 80)
print("EMAIL PREVIEW")
print("=" * 80)
print()

# Get contact
try:
    contact_email, contact_name = get_contact_email(order, domain, db)
    print(f"To: {contact_email}")
    print(f"Contact Name: {contact_name}")
except Exception as e:
    print(f"⚠️  Would fail: {e}")
    print("This order needs a contact email to be sent!")

print(f"Domain: {domain.domain}")
print(f"Campaign: {campaign.name if campaign else 'Unknown'}")
print(f"Link Type: {order.link_type}")
print(f"Status: {order.status}")
print()

# Get links
links = db.query(OrderLink).filter(OrderLink.order_id == order_id).all()
if not links and order.anchor_text and order.target_url:
    print("Links (legacy):")
    print(f"  • {order.anchor_text} → {order.target_url}")
else:
    print("Links:")
    for link in links:
        print(f"  • {link.anchor_text} → {link.target_url}")

print()
print("Article word count:", len(order.article_content.split()))
print()
print("Article preview (first 300 chars):")
print(order.article_content[:300] + "...")
print()

db.close()
