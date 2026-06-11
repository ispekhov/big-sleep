"""End-to-end API tests via FastAPI TestClient.

Uses the app's real (temp) SQLite DB + in-memory vector store, seeded with the
synthetic catalogue so search returns matches.
"""

import pytest
from fastapi.testclient import TestClient

from encounter import seed as seed_module
from encounter.main import app
from tests.conftest import make_jpeg


@pytest.fixture(scope="module")
def client():
    seed_module.seed()  # populate DB + vector index
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["indexed_vectors"] > 0


def test_list_brands_and_products(client):
    brands = client.get("/brands").json()
    assert any(b["name"] == "Tom Dixon" for b in brands)
    bid = next(b["id"] for b in brands if b["name"] == "Tom Dixon")
    products = client.get(f"/brands/{bid}/products").json()
    assert len(products) >= 1
    assert products[0]["images"]


def test_visual_search_endpoint(client):
    # Use the same procedural image the seed uses for Melt Pendant (orange).
    img = seed_module._make_image((255, 140, 0), 0)
    r = client.post("/search", files={"file": ("q.jpg", img, "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert body["top_candidate"]["product_name"] == "Melt Pendant"
    assert body["top_candidate"]["confidence"] > 0.9


def test_search_rejects_empty_upload(client):
    r = client.post("/search", files={"file": ("q.jpg", b"", "image/jpeg")})
    assert r.status_code == 400


def test_field_capture_and_verification_flow(client):
    img = make_jpeg(color=(123, 200, 50), seed=7)
    r = client.post(
        "/field-capture",
        data={"brand": "Flos", "product_name": "Arco", "location": "Cafe"},
        files={"file": ("capture.jpg", img, "image/jpeg")},
    )
    assert r.status_code == 200
    image = r.json()
    assert image["image_type"] == "field_capture_unverified"
    assert image["verification_status"] == "submitted"

    # Appears in the submitted review queue.
    queue = client.get("/review/images?status=submitted").json()
    assert any(i["id"] == image["id"] for i in queue)

    # Verify it -> promoted to field_capture_verified.
    r = client.patch(
        f"/images/{image['id']}/verification",
        json={"status": "verified", "reviewer_notes": "looks right"},
    )
    assert r.status_code == 200
    assert r.json()["image_type"] == "field_capture_verified"


def test_product_correction(client):
    products = client.get("/products?limit=1").json()
    pid = products[0]["id"]
    r = client.patch(
        f"/products/{pid}",
        json={"category": "Statement Lighting", "price": 999.0},
    )
    assert r.status_code == 200
    assert r.json()["category"] == "Statement Lighting"
    assert r.json()["needs_review"] is False
