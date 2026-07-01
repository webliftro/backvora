"""
Contacts API router - CRUD + grabber + forms + templates.
"""

import random
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from ..models import Contact, Domain, ContactForm, OutreachTemplate
from ..schemas.contact import ContactCreate, ContactUpdate, ContactResponse, ContactList
from ..schemas.contact_form import (
    ContactFormResponse, OutreachTemplateCreate, OutreachTemplateUpdate,
    OutreachTemplateResponse, GrabResult,
)
from ..services.scraper import EmailScraper, ContactsGrabber

router = APIRouter()

# ============ Seed Templates ============

SEED_TEMPLATES = [
    {
        "name": "Template 1 - Advertising Inquiry",
        "subject_template": "Advertising on $domain",
        "body_template": "Hi, I came across $domain and I'm interested in advertising opportunities. Do you offer sponsored posts or link placements? Could you share your rates?\n\nBest, Tony",
    },
    {
        "name": "Template 2 - Collaboration",
        "subject_template": "Advertising on $domain",
        "body_template": "Hi there, I'm reaching out about a potential collaboration on $domain. I'd like to place a high-quality article with a link on your site. What would your rates be?\n\nBest, Tony",
    },
    {
        "name": "Template 3 - Guest Post",
        "subject_template": "Advertising on $domain",
        "body_template": "Hey, I'm interested in placing a guest post on $domain. I provide well-written, unique content that fits your audience. Could you let me know your pricing and any guidelines?\n\nBest, Tony",
    },
    {
        "name": "Template 4 - Sponsored Content",
        "subject_template": "Advertising on $domain",
        "body_template": "Hello, I'd like to inquire about guest posting or sponsored content options on $domain. What are your terms and rates?\n\nBest, Tony",
    },
]


def seed_templates(db: Session):
    """Seed default templates if none exist."""
    if db.query(OutreachTemplate).count() == 0:
        for t in SEED_TEMPLATES:
            db.add(OutreachTemplate(**t))
        db.commit()


# ============ Contacts CRUD ============

@router.get("", response_model=ContactList)
async def list_contacts(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    domain_id: Optional[str] = None,
    is_valid: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Contact).filter(Contact.deleted_at.is_(None))
    if domain_id:
        query = query.filter(Contact.domain_id == domain_id)
    if is_valid is not None:
        query = query.filter(Contact.is_valid == is_valid)
    if search:
        query = query.filter(
            (Contact.email.ilike(f"%{search}%")) | (Contact.name.ilike(f"%{search}%"))
        )
    total = query.count()
    contacts = query.offset((page - 1) * per_page).limit(per_page).all()
    return {"items": contacts, "total": total, "page": page, "per_page": per_page, "pages": (total + per_page - 1) // per_page}


@router.post("", response_model=ContactResponse)
async def create_contact(data: ContactCreate, db: Session = Depends(get_db)):
    domain = db.query(Domain).filter(Domain.id == data.domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    contact = Contact(**data.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(contact_id: str, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.put("/{contact_id}", response_model=ContactResponse)
async def update_contact(contact_id: str, data: ContactUpdate, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(contact, key, value)
    db.commit()
    db.refresh(contact)
    return contact


@router.post("/{contact_id}/set-primary")
async def set_primary_contact(contact_id: str, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id, Contact.deleted_at.is_(None)).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    # Unset all other primary contacts for this domain
    db.query(Contact).filter(
        Contact.domain_id == contact.domain_id,
        Contact.id != contact_id,
        Contact.deleted_at.is_(None),
    ).update({"is_primary": False})
    contact.is_primary = True
    db.commit()
    db.refresh(contact)
    return contact


@router.delete("/{contact_id}")
async def delete_contact(contact_id: str, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    contact.deleted_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "Contact deleted"}


# ============ Scrape (legacy) ============

@router.post("/scrape/{domain_id}")
async def scrape_contacts(domain_id: str, db: Session = Depends(get_db)):
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    try:
        scraper = EmailScraper()
        results = await scraper.scrape_domain(domain.domain)
        added = []
        for email_info in results:
            existing = db.query(Contact).filter(Contact.domain_id == domain_id, Contact.email == email_info["email"]).first()
            if existing:
                continue
            contact = Contact(domain_id=domain_id, email=email_info["email"], source_page=email_info.get("source_url"), source_type=email_info.get("source_type"))
            db.add(contact)
            added.append(email_info["email"])
        db.commit()
        return {"success": True, "domain": domain.domain, "found": len(results), "added": len(added), "emails": added}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ Contacts Grabber ============

@router.post("/grab/{domain_id}")
async def grab_contacts(
    domain_id: str,
    use_browser: bool = Query(False, description="Force Playwright browser mode for deep scraping"),
    db: Session = Depends(get_db)
):
    """Full contacts grab: emails + socials + forms."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    try:
        grabber = ContactsGrabber()
        data = await grabber.grab_all(domain.domain, use_browser=use_browser)
        
        # Check which emails are already saved
        existing_emails = {c.email.lower() for c in db.query(Contact).filter(
            Contact.domain_id == domain_id
        ).all() if c.email}
        for email_info in data["emails"]:
            email_info["already_saved"] = email_info["email"].lower() in existing_emails
        
        # Save detected forms (metadata only, not contacts)
        forms_detected = 0
        for form_info in data["forms"]:
            existing = db.query(ContactForm).filter(
                ContactForm.domain_id == domain_id,
                ContactForm.form_url == form_info["form_url"],
                ContactForm.form_action == form_info["form_action"],
            ).first()
            if not existing:
                cf = ContactForm(
                    domain_id=domain_id,
                    form_url=form_info["form_url"],
                    form_action=form_info["form_action"],
                    form_method=form_info["form_method"],
                    fields_json=form_info["fields"],
                    has_captcha=form_info.get("has_captcha", False),
                    captcha_type=form_info.get("captcha_type", "none"),
                    captcha_site_key=form_info.get("captcha_site_key"),
                )
                db.add(cf)
                forms_detected += 1
        
        db.commit()
        
        return {
            "success": True,
            "domain": domain.domain,
            "method": data.get("method", "static"),
            "emails": data["emails"],
            "socials": data["socials"],
            "names": data["names"],
            "forms": data["forms"],
            "contacts_added": 0,
            "forms_detected": forms_detected,
            "_browser_error": data.get("_browser_error"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ Forms ============

@router.get("/forms/{domain_id}")
async def get_forms(domain_id: str, db: Session = Depends(get_db)):
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    forms = db.query(ContactForm).filter(ContactForm.domain_id == domain_id).all()
    return {"items": [ContactFormResponse.model_validate(f) for f in forms]}


@router.post("/submit-form/{domain_id}")
async def submit_form(
    domain_id: str, 
    form_id: Optional[str] = None, 
    template_id: Optional[str] = None, 
    force_browser: bool = Query(False, description="Force browser-based submission even without CAPTCHA"),
    db: Session = Depends(get_db)
):
    """Submit a detected contact form using a template."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    # Get form
    if form_id:
        form = db.query(ContactForm).filter(ContactForm.id == form_id).first()
    else:
        form = db.query(ContactForm).filter(ContactForm.domain_id == domain_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="No contact form found for this domain")
    
    # Get template
    seed_templates(db)
    if template_id:
        template = db.query(OutreachTemplate).filter(OutreachTemplate.id == template_id).first()
    else:
        active = db.query(OutreachTemplate).filter(OutreachTemplate.is_active == True).all()
        if not active:
            raise HTTPException(status_code=404, detail="No active templates")
        template = random.choice(active)
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Decide whether to use browser-based submission
    use_browser = force_browser or (form.has_captcha and form.captcha_type != "none")
    
    # Build form data
    subject = (template.subject_template or "").replace("$domain", domain.domain)
    body = (template.body_template or "").replace("$domain", domain.domain)
    
    form_data = {}
    for field in (form.fields_json or []):
        name = field["name"].lower()
        label = field.get("label", "").lower()
        combined = f"{name} {label}"
        if any(k in combined for k in ["email", "e-mail", "mail"]):
            form_data[field["name"]] = settings.email_account
        elif any(k in combined for k in ["name", "your name", "full name"]):
            form_data[field["name"]] = "Tony"
        elif any(k in combined for k in ["subject", "topic"]):
            form_data[field["name"]] = subject
        elif any(k in combined for k in ["message", "body", "content", "comment", "text"]):
            form_data[field["name"]] = body
        elif field["type"] == "textarea":
            form_data[field["name"]] = body
        else:
            form_data[field["name"]] = ""
    
    if use_browser:
        # Use browser-based submission with CAPTCHA solving
        from ..services.browser_scraper import BrowserFormSubmitter
        
        submitter = BrowserFormSubmitter(headless=True, page_load_timeout=30)
        result = await submitter.submit_form_with_captcha(
            form_url=form.form_url,
            form_data=form_data,
            fields=form.fields_json or [],
            captcha_site_key=form.captcha_site_key,
            captcha_type=form.captcha_type or "none",
            form_action=form.form_action,
        )
    else:
        # Use traditional HTTP submission
        grabber = ContactsGrabber()
        result = await grabber.submit_form(
            form_action=form.form_action or form.form_url,
            form_method=form.form_method,
            fields_json=form.fields_json or [],
            template_body=template.body_template or "",
            template_subject=template.subject_template or "",
            domain=domain.domain,
        )
    
    form.last_submitted_at = datetime.utcnow()
    form.submission_status = "success" if result.get("success") else "failed"
    db.commit()
    
    return {
        "success": result.get("success", False),
        "template_used": template.name,
        "form_url": form.form_url,
        "used_browser": use_browser,
        "captcha_solved": result.get("captcha_solved", False),
        "status_code": result.get("status_code"),
        "error": result.get("error"),
        "data_sent": form_data,
    }


@router.post("/submit-form/{domain_id}/preview")
async def preview_form_submission(domain_id: str, form_id: Optional[str] = None, template_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Preview what would be sent without actually submitting."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    if form_id:
        form = db.query(ContactForm).filter(ContactForm.id == form_id).first()
    else:
        form = db.query(ContactForm).filter(ContactForm.domain_id == domain_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="No contact form found")
    
    seed_templates(db)
    if template_id:
        template = db.query(OutreachTemplate).filter(OutreachTemplate.id == template_id).first()
    else:
        active = db.query(OutreachTemplate).filter(OutreachTemplate.is_active == True).all()
        if not active:
            raise HTTPException(status_code=404, detail="No active templates")
        template = random.choice(active)
    
    subject = (template.subject_template or "").replace("$domain", domain.domain)
    body = (template.body_template or "").replace("$domain", domain.domain)
    
    # Build preview data
    form_data = {}
    for field in (form.fields_json or []):
        name = field["name"].lower()
        label = field.get("label", "").lower()
        combined = f"{name} {label}"
        if any(k in combined for k in ["email", "e-mail", "mail"]):
            form_data[field["name"]] = settings.email_account
        elif any(k in combined for k in ["name", "your name", "full name"]):
            form_data[field["name"]] = "Tony"
        elif any(k in combined for k in ["subject", "topic"]):
            form_data[field["name"]] = subject
        elif any(k in combined for k in ["message", "body", "content", "comment", "text"]):
            form_data[field["name"]] = body
        elif field["type"] == "textarea":
            form_data[field["name"]] = body
        else:
            form_data[field["name"]] = ""
    
    return {
        "template_name": template.name,
        "template_id": template.id,
        "form_id": form.id,
        "form_url": form.form_url,
        "form_action": form.form_action,
        "form_method": form.form_method,
        "subject": subject,
        "body": body,
        "form_data": form_data,
        "fields": form.fields_json,
    }


# ============ Templates CRUD ============

@router.get("/templates/list")
async def list_templates(db: Session = Depends(get_db)):
    seed_templates(db)
    templates = db.query(OutreachTemplate).order_by(OutreachTemplate.created_at).all()
    return {"items": [OutreachTemplateResponse.model_validate(t) for t in templates]}


@router.post("/templates")
async def create_template(data: OutreachTemplateCreate, db: Session = Depends(get_db)):
    t = OutreachTemplate(**data.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return OutreachTemplateResponse.model_validate(t)


@router.put("/templates/{template_id}")
async def update_template(template_id: str, data: OutreachTemplateUpdate, db: Session = Depends(get_db)):
    t = db.query(OutreachTemplate).filter(OutreachTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(t, key, value)
    db.commit()
    db.refresh(t)
    return OutreachTemplateResponse.model_validate(t)


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, db: Session = Depends(get_db)):
    t = db.query(OutreachTemplate).filter(OutreachTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(t)
    db.commit()
    return {"success": True}


# ============ Bulk Grab Contacts ============

class BulkGrabRequest(BaseModel):
    domain_ids: list[str] | None = None

@router.post("/grab-bulk")
async def bulk_grab_contacts(body: BulkGrabRequest = BulkGrabRequest(), db: Session = Depends(get_db)):
    """
    Bulk grab contacts for multiple domains.
    If domain_ids is None or empty, grabs all domains without any contacts.
    """
    import asyncio
    from sqlalchemy import func, exists, select
    
    domain_ids = body.domain_ids
    # Determine which domains to process
    if domain_ids:
        domains = db.query(Domain).filter(Domain.id.in_(domain_ids)).all()
    else:
        # Find all domains without any saved contacts
        domains = db.query(Domain).filter(
            ~exists(select(Contact.id).where(
                Contact.domain_id == Domain.id,
                Contact.deleted_at.is_(None)
            ))
        ).all()
    
    if not domains:
        return {
            "success": True,
            "processed": 0,
            "results": [],
            "message": "No domains to process"
        }
    
    grabber = ContactsGrabber()
    results = []
    total_contacts = 0
    total_forms = 0
    
    for idx, domain in enumerate(domains):
        try:
            # Grab contacts with rate limiting (2 second delay between domains, except for the first one)
            if idx > 0:
                await asyncio.sleep(2)
            
            data = await grabber.grab_all(domain.domain)
            
            contacts_added = 0
            # Save emails as contacts
            for email_info in data["emails"]:
                existing = db.query(Contact).filter(
                    Contact.domain_id == domain.id, Contact.email == email_info["email"]
                ).first()
                if existing:
                    # Update socials on existing
                    if data["socials"]["twitter"] and not existing.social_twitter:
                        existing.social_twitter = data["socials"]["twitter"][0]
                    if data["socials"]["linkedin"] and not existing.social_linkedin:
                        existing.social_linkedin = data["socials"]["linkedin"][0]
                    if data["socials"]["telegram"] and not existing.social_telegram:
                        existing.social_telegram = data["socials"]["telegram"][0]
                    continue
                
                contact = Contact(
                    domain_id=domain.id,
                    email=email_info["email"],
                    source_page=email_info.get("source_url"),
                    source_type=email_info.get("source_type"),
                    social_twitter=data["socials"]["twitter"][0] if data["socials"]["twitter"] else None,
                    social_linkedin=data["socials"]["linkedin"][0] if data["socials"]["linkedin"] else None,
                    social_telegram=data["socials"]["telegram"][0] if data["socials"]["telegram"] else None,
                )
                # Assign name/role if found
                if data["names"]:
                    contact.name = data["names"][0].get("name")
                    contact.role = data["names"][0].get("role")
                
                db.add(contact)
                contacts_added += 1
            
            # Save detected forms
            forms_detected = 0
            for form_info in data["forms"]:
                existing = db.query(ContactForm).filter(
                    ContactForm.domain_id == domain.id,
                    ContactForm.form_url == form_info["form_url"],
                    ContactForm.form_action == form_info["form_action"],
                ).first()
                if not existing:
                    cf = ContactForm(
                        domain_id=domain.id,
                        form_url=form_info["form_url"],
                        form_action=form_info["form_action"],
                        form_method=form_info["form_method"],
                        fields_json=form_info["fields"],
                        has_captcha=form_info.get("has_captcha", False),
                        captcha_type=form_info.get("captcha_type", "none"),
                        captcha_site_key=form_info.get("captcha_site_key"),
                    )
                    db.add(cf)
                    forms_detected += 1
            
            db.commit()
            
            total_contacts += contacts_added
            total_forms += forms_detected
            
            results.append({
                "domain": domain.domain,
                "domain_id": domain.id,
                "success": True,
                "contacts_added": contacts_added,
                "forms_detected": forms_detected,
                "emails_found": len(data["emails"]),
            })
            
        except Exception as e:
            results.append({
                "domain": domain.domain,
                "domain_id": domain.id,
                "success": False,
                "error": str(e),
            })
            continue
    
    return {
        "success": True,
        "processed": len(domains),
        "total_contacts_added": total_contacts,
        "total_forms_detected": total_forms,
        "results": results,
    }
