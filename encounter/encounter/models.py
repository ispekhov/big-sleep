"""SQLAlchemy ORM models: Brand, Product, Variant, Image, Source.

The schema follows the V1 product data model. Embeddings are stored as JSON
floats so the platform runs on plain Postgres/SQLite; the authoritative
similarity index lives in the vector store (Qdrant). Keeping a copy here makes
it trivial to re-index and to back-fill a fresh vector collection.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .enums import ImageType, SourceType, VerificationStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow
    )


class Source(Base, TimestampMixin):
    """A place records came from (a brand site, a retailer, a capture, …)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[SourceType] = mapped_column(SAEnum(SourceType))
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(1024))

    products: Mapped[list["Product"]] = relationship(back_populates="source")
    images: Mapped[list["Image"]] = relationship(back_populates="source")


class Brand(Base, TimestampMixin):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text)

    products: Mapped[list["Product"]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("brand_id", "product_url", name="uq_product_brand_url"),
        Index("ix_product_brand_name", "brand_id", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))

    # Required product fields from the spec.
    name: Mapped[str] = mapped_column(String(512), index=True)
    category: Mapped[str | None] = mapped_column(String(255), index=True)
    collection: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    materials: Mapped[str | None] = mapped_column(String(512))
    dimensions: Mapped[str | None] = mapped_column(String(512))
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    sku: Mapped[str | None] = mapped_column(String(128), index=True)
    product_url: Mapped[str | None] = mapped_column(String(1024))

    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus), default=VerificationStatus.submitted, index=True
    )
    # True when the importer could not confidently extract required fields.
    needs_review: Mapped[bool] = mapped_column(default=False, index=True)

    brand: Mapped[Brand] = relationship(back_populates="products")
    source: Mapped[Source | None] = relationship(back_populates="products")
    variants: Mapped[list["Variant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    images: Mapped[list["Image"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class Variant(Base, TimestampMixin):
    __tablename__ = "variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    sku: Mapped[str | None] = mapped_column(String(128))
    color: Mapped[str | None] = mapped_column(String(128))
    finish: Mapped[str | None] = mapped_column(String(128))
    price: Mapped[float | None] = mapped_column(Float)

    product: Mapped[Product] = relationship(back_populates="variants")


class Image(Base, TimestampMixin):
    __tablename__ = "images"
    __table_args__ = (
        Index("ix_image_status_type", "verification_status", "image_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), index=True
    )
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))

    # Required image fields from the spec.
    image_url: Mapped[str] = mapped_column(String(1024))
    storage_key: Mapped[str | None] = mapped_column(String(1024))
    image_type: Mapped[ImageType] = mapped_column(SAEnum(ImageType))
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus), default=VerificationStatus.submitted, index=True
    )

    # Field-capture context (optional, set for real-world captures).
    capture_location: Mapped[str | None] = mapped_column(String(255))
    capture_notes: Mapped[str | None] = mapped_column(Text)

    source: Mapped[Source | None] = relationship(back_populates="images")
    product: Mapped[Product | None] = relationship(back_populates="images")


class BrandQueue(Base, TimestampMixin):
    """A queued brand to import in the batch pipeline (one job per brand)."""

    __tablename__ = "brand_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    # pending -> done / empty / failed / failed_timeout
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    classification: Mapped[str | None] = mapped_column(String(64))
    products_imported: Mapped[int] = mapped_column(default=0)
    images_imported: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
