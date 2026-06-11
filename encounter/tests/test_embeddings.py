import numpy as np

from encounter.embeddings.fallback import PerceptualEmbedder
from tests.conftest import make_jpeg


def test_embedding_is_normalized_and_sized():
    emb = PerceptualEmbedder(dim=256)
    v = emb.embed(make_jpeg())
    assert v.shape == (256,)
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-4


def test_similar_images_closer_than_different():
    emb = PerceptualEmbedder(dim=512)
    red_a = emb.embed(make_jpeg(color=(220, 30, 30), seed=1))
    red_b = emb.embed(make_jpeg(color=(220, 30, 30), seed=1))  # identical
    blue = emb.embed(make_jpeg(color=(30, 30, 220), seed=9))

    sim_same = float(red_a @ red_b)
    sim_diff = float(red_a @ blue)
    assert sim_same > sim_diff
    assert sim_same > 0.95  # identical inputs -> near-identical vectors


def test_deterministic_across_instances():
    a = PerceptualEmbedder(dim=128).embed(make_jpeg(seed=3))
    b = PerceptualEmbedder(dim=128).embed(make_jpeg(seed=3))
    assert np.allclose(a, b)
