"""Seed the database with synthetic products so search is demonstrable offline.

Generates a handful of design products, each with a distinct procedurally
drawn image, embeds and indexes them. Run: ``python -m encounter.seed``.

This is for local demos/tests only — real data comes from the brand importer.
"""

from __future__ import annotations

import io
import random

from PIL import Image as PILImage, ImageDraw

from .db import init_db, session_scope
from .embeddings import get_embedder
from .enums import ImageType, SourceType, VerificationStatus
from .models import Brand, Image, Product, Source
from .storage import get_storage
from .vectorstore import get_vector_store

_SEED_PRODUCTS = [
    ("Melt Pendant", "Lighting", "Melt", 950.0, (255, 140, 0)),
    ("Beat Light Tall", "Lighting", "Beat", 560.0, (40, 40, 40)),
    ("Wingback Chair", "Seating", "Wingback", 2100.0, (120, 30, 60)),
    ("Cog Table", "Tables", "Cog", 1800.0, (180, 150, 90)),
    ("Mirror Ball Floor", "Lighting", "Mirror Ball", 1250.0, (200, 200, 210)),
    ("Tube Chair", "Seating", "Tube", 990.0, (30, 90, 140)),
]


def _make_image(color: tuple[int, int, int], variant: int) -> bytes:
    """Distinct, deterministic image per product (so embeddings differ)."""
    rng = random.Random(sum(color) * 100 + variant)
    img = PILImage.new("RGB", (256, 256), (20, 20, 24))
    draw = ImageDraw.Draw(img)
    for _ in range(6):
        x0, y0 = rng.randint(0, 200), rng.randint(0, 200)
        x1, y1 = x0 + rng.randint(30, 90), y0 + rng.randint(30, 90)
        jitter = tuple(min(255, max(0, c + rng.randint(-25, 25))) for c in color)
        draw.ellipse([x0, y0, x1, y1], fill=jitter)
    draw.rectangle([60, 60, 196, 196], outline=color, width=8)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def seed() -> None:
    init_db()
    embedder = get_embedder()
    storage = get_storage()
    store = get_vector_store()

    with session_scope() as session:
        brand = session.query(Brand).filter_by(name="Tom Dixon").one_or_none()
        if brand is None:
            brand = Brand(name="Tom Dixon", website="https://www.tomdixon.net")
            session.add(brand)
            session.flush()
        source = Source(
            type=SourceType.brand_site, name="Tom Dixon", url="https://www.tomdixon.net"
        )
        session.add(source)
        session.flush()

        for name, category, collection, price, color in _SEED_PRODUCTS:
            if session.query(Product).filter_by(
                brand_id=brand.id, name=name
            ).one_or_none():
                continue
            product = Product(
                brand_id=brand.id, source_id=source.id, name=name,
                category=category, collection=collection, price=price,
                currency="USD", description=f"{collection} {category.lower()} by Tom Dixon.",
                verification_status=VerificationStatus.ai_validated,
            )
            session.add(product)
            session.flush()
            for v in range(2):
                data = _make_image(color, v)
                vec = embedder.embed(data)
                key = f"products/{brand.id}/{product.id}/seed{v}.jpg"
                url = storage.put(key, data)
                image = Image(
                    product_id=product.id, source_id=source.id, image_url=url,
                    storage_key=key, image_type=ImageType.official_product_image,
                    embedding=[float(x) for x in vec.tolist()],
                    embedding_model=embedder.name,
                    verification_status=VerificationStatus.ai_validated,
                )
                session.add(image)
                session.flush()
                store.upsert(
                    image.id, vec,
                    {"product_id": product.id, "image_type": image.image_type.value},
                )
    print("Seeded synthetic Tom Dixon catalogue.")


if __name__ == "__main__":
    seed()
