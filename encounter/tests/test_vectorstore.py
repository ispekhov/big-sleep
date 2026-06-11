import numpy as np

from encounter.vectorstore.memory import InMemoryVectorStore


def _unit(vec):
    vec = np.asarray(vec, dtype="float32")
    return vec / np.linalg.norm(vec)


def test_upsert_search_delete():
    store = InMemoryVectorStore()
    store.upsert(1, _unit([1, 0, 0]), {"product_id": 10})
    store.upsert(2, _unit([0, 1, 0]), {"product_id": 20})
    store.upsert(3, _unit([0.9, 0.1, 0]), {"product_id": 30})

    assert store.count() == 3
    hits = store.search(_unit([1, 0, 0]), top_k=2)
    assert hits[0].image_id == 1
    assert hits[0].product_id == 10
    assert hits[1].image_id == 3  # closest after exact match

    store.delete(1)
    assert store.count() == 2
    assert all(h.image_id != 1 for h in store.search(_unit([1, 0, 0]), top_k=5))


def test_upsert_overwrites():
    store = InMemoryVectorStore()
    store.upsert(1, _unit([1, 0, 0]), {"product_id": 10})
    store.upsert(1, _unit([0, 1, 0]), {"product_id": 11})
    assert store.count() == 1
    hits = store.search(_unit([0, 1, 0]), top_k=1)
    assert hits[0].product_id == 11
