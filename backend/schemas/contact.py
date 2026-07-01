"""
Contact Pydantic schemas for request/response validation.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class ContactBase(BaseModel):
    """Base contact fields."""
    email: EmailStr
    name: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = Field(None, max_length=100)
    social_twitter: Optional[str] = Field(None, max_length=500)
    social_linkedin: Optional[str] = Field(None, max_length=500)
    social_telegram: Optional[str] = Field(None, max_length=500)
    source_page: Optional[str] = Field(None, max_length=500)
    source_type: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class ContactCreate(ContactBase):
    """Schema for creating a contact."""
    domain_id: str


class ContactUpdate(BaseModel):
    """Schema for updating a contact (all fields optional)."""
    email: Optional[EmailStr] = None
    name: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = Field(None, max_length=100)
    is_valid: Optional[bool] = None
    is_primary: Optional[bool] = None
    notes: Optional[str] = None


class ContactResponse(ContactBase):
    """Schema for contact response."""
    id: str
    domain_id: str
    is_valid: Optional[bool] = None
    is_primary: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContactList(BaseModel):
    """Schema for paginated contact list."""
    items: list[ContactResponse]
    total: int
    page: int
    per_page: int
    pages: int
