"""Field capture, corrections, and the verification pipeline.

Raw user labels never train the model directly. A field capture or correction
enters as ``submitted`` and must climb the pipeline
(submitted -> ai_validated -> human_review -> verified) before it is eligible
as training data. ``verified`` field captures are promoted to the
``field_capture_verified`` image type.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..embeddings import get_embedder
from ..enums import ImageType, SourceType, VerificationStatus
from ..models import Brand, Image, Product, Source
from ..schemas import (
    CorrectionRequest,
    ImageDetail,
    ProductOut,
    VerificationUpdate,
)
from ..storage import get_storage
from ..vectorstore import get_vector_store

router = APIRouter(tags=["verification"])


def _get_or_create_brand(session: Session, name: str) -> Brand:
    brand = session.scalar(select(Brand).where(Brand.name == name))
    if brand is None:
        brand = Brand(name=name)
        session.add(brand)
        session.flush()
    return brand


def _get_or_create_product(session: Session, brand: Brand, name: str) -> Product:
    product = session.scalar(
        select(Product).where(Product.brand_id == brand.id, Product.name == name)
    )
    if product is None:
        product = Product(
            brand_id=brand.id,
            name=name,
            needs_review=True,
            verification_status=VerificationStatus.submitted,
        )
        session.add(product)
        session.flush()
    return product


@router.post("/field-capture", response_model=ImageDetail)
async def field_capture(
    brand: str = Form(...),
    product_name: str = Form(...),
    location: str | None = Form(None),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> Image:
    """Submit a real-world labelled photo (Field Capture Mode).

    Stored as ``field_capture_unverified`` and queued for verification.
    """
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty image upload")

    brand_obj = _get_or_create_brand(session, brand)
    product = _get_or_create_product(session, brand_obj, product_name)

    source = session.scalar(
        select(Source).where(Source.type == SourceType.field_capture)
    )
    if source is None:
        source = Source(type=SourceType.field_capture, name="field_capture")
        session.add(source)
        session.flush()

    embedder = get_embedder()
    try:
        vector = embedder.embed(data)
    except Exception as exc:
        raise HTTPException(422, f"Could not process image: {exc}") from exc

    digest = hashlib.sha256(data).hexdigest()[:24]
    key = f"field_captures/{brand_obj.id}/{digest}.jpg"
    url = get_storage().put(key, data, "image/jpeg")

    image = Image(
        product_id=product.id,
        source_id=source.id,
        image_url=url,
        storage_key=key,
        image_type=ImageType.field_capture_unverified,
        embedding=[float(x) for x in vector.tolist()],
        embedding_model=embedder.name,
        verification_status=VerificationStatus.submitted,
        capture_location=location,
        capture_notes=notes,
    )
    session.add(image)
    session.commit()
    session.refresh(image)
    return image


@router.post("/images/{image_id}/correction", response_model=ProductOut)
def correct_query_image(
    image_id: int,
    correction: CorrectionRequest,
    session: Session = Depends(get_session),
) -> Product:
    """Label a query image the system failed to identify.

    Links the image to the (existing or newly created) product and submits it
    to the verification pipeline.
    """
    image = session.get(Image, image_id)
    if image is None:
        raise HTTPException(404, "Image not found")

    if correction.product_id is not None:
        product = session.get(Product, correction.product_id)
        if product is None:
            raise HTTPException(404, "Product not found")
    else:
        brand = _get_or_create_brand(session, correction.brand)
        product = _get_or_create_product(session, brand, correction.product_name)

    image.product_id = product.id
    if image.image_type == ImageType.user_query_image:
        image.image_type = ImageType.field_capture_unverified
    image.verification_status = VerificationStatus.submitted
    if correction.notes:
        image.capture_notes = correction.notes
    if correction.capture_location:
        image.capture_location = correction.capture_location
    session.commit()

    stmt = (
        select(Product)
        .where(Product.id == product.id)
        .options(
            selectinload(Product.brand),
            selectinload(Product.images),
            selectinload(Product.variants),
        )
    )
    return session.scalar(stmt)


@router.patch("/images/{image_id}/verification", response_model=ImageDetail)
def update_verification(
    image_id: int,
    update: VerificationUpdate,
    session: Session = Depends(get_session),
) -> Image:
    """Advance an image through the verification pipeline (human review)."""
    image = session.get(Image, image_id)
    if image is None:
        raise HTTPException(404, "Image not found")

    image.verification_status = update.status
    if update.reviewer_notes:
        image.capture_notes = update.reviewer_notes

    # Verified field captures become training-eligible.
    if (
        update.status == VerificationStatus.verified
        and image.image_type == ImageType.field_capture_unverified
    ):
        image.image_type = ImageType.field_capture_verified
        # Index verified captures so they strengthen future search.
        if image.embedding and image.product_id:
            import numpy as np

            get_vector_store().upsert(
                image.id,
                np.asarray(image.embedding, dtype="float32"),
                {
                    "product_id": image.product_id,
                    "image_type": image.image_type.value,
                },
            )
    session.commit()
    session.refresh(image)
    return image


@router.get("/review/images", response_model=list[ImageDetail])
def review_image_queue(
    session: Session = Depends(get_session),
    status: VerificationStatus = VerificationStatus.submitted,
    limit: int = 50,
) -> list[Image]:
    """Images awaiting review (Correction UI verification queue)."""
    stmt = (
        select(Image)
        .where(Image.verification_status == status)
        .order_by(Image.created_at)
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


@router.get("/review/products", response_model=list[ProductOut])
def review_product_queue(
    session: Session = Depends(get_session), limit: int = 50
) -> list[Product]:
    """Products the importer flagged as needing review."""
    stmt = (
        select(Product)
        .where(Product.needs_review.is_(True))
        .options(
            selectinload(Product.brand),
            selectinload(Product.images),
            selectinload(Product.variants),
        )
        .order_by(Product.id)
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


@router.get("/images/{image_id}", response_model=ImageDetail)
def get_image(image_id: int, session: Session = Depends(get_session)) -> Image:
    image = session.get(Image, image_id)
    if image is None:
        raise HTTPException(404, "Image not found")
    return image
