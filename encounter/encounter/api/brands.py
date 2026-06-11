"""Brand import + browse endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..importer.pipeline import (
    ImportPipeline,
    make_http_downloader,
    make_http_fetcher,
)
from ..models import Brand, Product
from ..schemas import BrandOut, ImportRequest, ImportSummary, ProductOut

router = APIRouter(prefix="/brands", tags=["brands"])


@router.post("/import", response_model=ImportSummary)
def import_brand(
    req: ImportRequest, session: Session = Depends(get_session)
) -> ImportSummary:
    """Crawl a brand website and import its product catalogue.

    Example: ``{"url": "https://www.tomdixon.net"}`` ->
    ``427 products imported, 3842 images imported, 46 need review``.
    """
    pipeline = ImportPipeline(
        session, fetcher=make_http_fetcher(), downloader=make_http_downloader()
    )
    return pipeline.run(req.url, max_pages=req.max_pages)


@router.get("", response_model=list[BrandOut])
def list_brands(session: Session = Depends(get_session)) -> list[Brand]:
    return list(session.scalars(select(Brand).order_by(Brand.name)).all())


@router.get("/{brand_id}", response_model=BrandOut)
def get_brand(brand_id: int, session: Session = Depends(get_session)) -> Brand:
    brand = session.get(Brand, brand_id)
    if brand is None:
        raise HTTPException(404, "Brand not found")
    return brand


@router.get("/{brand_id}/products", response_model=list[ProductOut])
def brand_products(
    brand_id: int, session: Session = Depends(get_session)
) -> list[Product]:
    if session.get(Brand, brand_id) is None:
        raise HTTPException(404, "Brand not found")
    stmt = (
        select(Product)
        .where(Product.brand_id == brand_id)
        .options(
            selectinload(Product.brand),
            selectinload(Product.images),
            selectinload(Product.variants),
        )
        .order_by(Product.name)
    )
    return list(session.scalars(stmt).all())
