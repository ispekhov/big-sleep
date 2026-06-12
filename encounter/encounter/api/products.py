"""Product browse + correction endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import Product
from ..schemas import ProductOut

router = APIRouter(prefix="/products", tags=["products"])


class ProductCorrection(BaseModel):
    """Human correction of importer-extracted product fields."""

    name: str | None = None
    category: str | None = None
    collection: str | None = None
    description: str | None = None
    materials: str | None = None
    dimensions: str | None = None
    price: float | None = None
    currency: str | None = None
    sku: str | None = None
    resolve_review: bool = True


def _load(session: Session, product_id: int) -> Product:
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.brand),
            selectinload(Product.images),
            selectinload(Product.variants),
        )
    )
    product = session.scalar(stmt)
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


@router.get("", response_model=list[ProductOut])
def list_products(
    session: Session = Depends(get_session),
    brand_id: int | None = None,
    category: str | None = None,
    needs_review: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[Product]:
    stmt = select(Product).options(
        selectinload(Product.brand),
        selectinload(Product.images),
        selectinload(Product.variants),
    )
    if brand_id is not None:
        stmt = stmt.where(Product.brand_id == brand_id)
    if category is not None:
        stmt = stmt.where(Product.category == category)
    if needs_review is not None:
        stmt = stmt.where(Product.needs_review == needs_review)
    stmt = stmt.order_by(Product.id).limit(limit).offset(offset)
    return list(session.scalars(stmt).all())


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, session: Session = Depends(get_session)) -> Product:
    return _load(session, product_id)


@router.patch("/{product_id}", response_model=ProductOut)
def correct_product(
    product_id: int,
    correction: ProductCorrection,
    session: Session = Depends(get_session),
) -> Product:
    """Apply a human correction to a product (used by the Correction UI)."""
    product = _load(session, product_id)
    data = correction.model_dump(exclude_unset=True, exclude={"resolve_review"})
    for field, value in data.items():
        setattr(product, field, value)
    if correction.resolve_review:
        product.needs_review = False
    session.commit()
    session.refresh(product)
    return product


@router.delete("/{product_id}")
def delete_product(
    product_id: int, session: Session = Depends(get_session)
) -> dict:
    """Remove a wrongly-extracted product (e.g. a swatch or non-product page).

    Cascades to its images and variants. Used by the Catalogue QA view's
    "Not a product" action.
    """
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    session.delete(product)  # ORM cascade removes images + variants
    session.commit()
    return {"deleted": product_id}
