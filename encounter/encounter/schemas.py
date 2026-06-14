"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import ImageType, VerificationStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Brands --------------------------------------------------------------
class BrandOut(ORMModel):
    id: int
    name: str
    website: str | None = None
    description: str | None = None


# --- Images --------------------------------------------------------------
class ImageOut(ORMModel):
    id: int
    image_url: str
    image_type: ImageType
    verification_status: VerificationStatus
    capture_location: str | None = None


# --- Variants ------------------------------------------------------------
class VariantOut(ORMModel):
    id: int
    name: str
    sku: str | None = None
    color: str | None = None
    finish: str | None = None
    price: float | None = None


# --- Products ------------------------------------------------------------
class ProductOut(ORMModel):
    id: int
    brand_id: int
    name: str
    category: str | None = None
    collection: str | None = None
    description: str | None = None
    materials: str | None = None
    dimensions: str | None = None
    price: float | None = None
    currency: str | None = None
    sku: str | None = None
    product_url: str | None = None
    verification_status: VerificationStatus
    needs_review: bool
    brand: BrandOut | None = None
    images: list[ImageOut] = Field(default_factory=list)
    variants: list[VariantOut] = Field(default_factory=list)


# --- Import --------------------------------------------------------------
class ImportRequest(BaseModel):
    url: str = Field(..., examples=["https://www.tomdixon.net"])
    max_pages: int | None = Field(default=None, ge=1, le=5000)


class ImportSummary(BaseModel):
    brand: str
    products_imported: int
    images_imported: int
    products_need_review: int
    pages_crawled: int
    message: str = "Ready for visual search"


# --- Batch queue ---------------------------------------------------------
class BrandQueueItem(BaseModel):
    url: str
    name: str | None = None


class BrandEnqueueRequest(BaseModel):
    brands: list[BrandQueueItem] = Field(default_factory=list)


class BrandEnqueueResult(BaseModel):
    added: int
    skipped_existing: int
    invalid: list[str] = Field(default_factory=list)
    pending: int


# --- Search --------------------------------------------------------------
class SearchCandidate(BaseModel):
    product_id: int
    brand: str
    product_name: str
    category: str | None = None
    price: float | None = None
    currency: str | None = None
    description: str | None = None
    confidence: float  # 0..1
    matched_image_url: str | None = None
    images: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query_image_id: int
    top_candidate: SearchCandidate | None = None
    candidates: list[SearchCandidate] = Field(default_factory=list)
    similar_products: list[SearchCandidate] = Field(default_factory=list)


# --- Field capture / corrections -----------------------------------------
class CorrectionRequest(BaseModel):
    """A user-supplied label for a query/field-capture image.

    Submitting a correction never trains the model directly — it enters the
    verification pipeline as ``submitted``.
    """

    brand: str
    product_name: str
    product_id: int | None = None
    notes: str | None = None
    capture_location: str | None = None


class VerificationUpdate(BaseModel):
    status: VerificationStatus
    reviewer_notes: str | None = None


class ImageDetail(ImageOut):
    product_id: int | None = None
    capture_notes: str | None = None
    embedding_model: str | None = None
    created_at: datetime | None = None
