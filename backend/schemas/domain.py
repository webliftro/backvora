"""
Domain Pydantic schemas for request/response validation.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from ..models import DomainStatus


class DomainBase(BaseModel):
    """Base domain fields."""
    domain: str = Field(..., min_length=1, max_length=255)
    is_competitor: bool = False
    is_adult: bool = True
    category: Optional[str] = Field(None, max_length=100)
    tags: Optional[str] = Field(None, max_length=500)  # Comma-separated
    niche_tags: Optional[str] = None  # Legacy
    notes: Optional[str] = None


class DomainCreate(DomainBase):
    """Schema for creating a domain."""
    pass


class DomainUpdate(BaseModel):
    """Schema for updating a domain (all fields optional)."""
    domain: Optional[str] = Field(None, min_length=1, max_length=255)
    is_competitor: Optional[bool] = None
    is_adult: Optional[bool] = None
    category: Optional[str] = Field(None, max_length=100)
    tags: Optional[str] = Field(None, max_length=500)
    niche_tags: Optional[str] = None
    owner: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    telegram: Optional[str] = Field(None, max_length=255)
    language: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    status: Optional[DomainStatus] = None


class DomainResponse(DomainBase):
    """Schema for domain response."""
    id: str
    domain_rating: Optional[float] = None
    organic_traffic: Optional[int] = None
    referring_domains: Optional[int] = None
    backlinks_count: Optional[int] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    language: Optional[str] = None
    status: DomainStatus
    last_analyzed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BulkDeleteRequest(BaseModel):
    """Schema for bulk delete."""
    ids: list[str]


class BulkUpdateRequest(BaseModel):
    """Schema for bulk update."""
    ids: list[str]
    category: Optional[str] = None
    tags: Optional[str] = None
    status: Optional[DomainStatus] = None


class DomainList(BaseModel):
    """Schema for paginated domain list."""
    items: list[DomainResponse]
    total: int
    page: int
    per_page: int
    pages: int
