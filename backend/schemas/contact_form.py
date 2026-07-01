from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ContactFormResponse(BaseModel):
    id: str
    domain_id: str
    form_url: str
    form_action: Optional[str] = None
    form_method: str
    fields_json: Optional[list] = None
    last_submitted_at: Optional[datetime] = None
    submission_status: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OutreachTemplateBase(BaseModel):
    name: str
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    is_active: bool = True


class OutreachTemplateCreate(OutreachTemplateBase):
    pass


class OutreachTemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    is_active: Optional[bool] = None


class OutreachTemplateResponse(OutreachTemplateBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class GrabResult(BaseModel):
    domain: str
    emails: list[dict]
    socials: dict
    forms: list[dict]
    contacts_added: int
    forms_detected: int
