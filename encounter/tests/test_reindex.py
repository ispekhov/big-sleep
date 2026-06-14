from encounter.embeddings.fallback import PerceptualEmbedder
from encounter.importer.pipeline import ImportPipeline
from encounter.reindex import reindex
from encounter.search.service import SearchService
from encounter.storage.local import LocalStorage
from encounter.vectorstore.memory import InMemoryVectorStore
from tests.test_pipeline import IMAGES, downloader, fetcher


def _import(session, store, storage, embedder):
    ImportPipeline(
        session, fetcher=fetcher, downloader=downloader,
        embedder=embedder, storage=storage, vector_store=store,
    ).run("https://tomdixon.net")


def test_reindex_rebuilds_from_stored_embeddings(session):
    embedder = PerceptualEmbedder(dim=512)
    storage = LocalStorage()
    _import(session, InMemoryVectorStore(), storage, embedder)

    # A fresh, empty index (as on a new process boot) gets repopulated.
    fresh = InMemoryVectorStore()
    assert fresh.count() == 0
    stats = reindex(session, embedder=embedder, store=fresh, storage=storage)
    assert stats.indexed > 0
    assert fresh.count() == stats.indexed

    # Search works against the rebuilt index.
    svc = SearchService(session, embedder=embedder, vector_store=fresh, storage=storage)
    result = svc.search(IMAGES["https://cdn.x/melt.jpg"], store_query=False)
    assert result.top_candidate is not None
    assert result.top_candidate.product_name == "Melt Pendant"


def test_reindex_re_embed_overwrites_embedding_model(session):
    embedder = PerceptualEmbedder(dim=512)
    storage = LocalStorage()
    store = InMemoryVectorStore()
    _import(session, store, storage, embedder)

    # Simulate a switch to a "new model": re-fingerprint from the stored bytes.
    class _TaggedEmbedder(PerceptualEmbedder):
        name = "siglip-fake"

    new_embedder = _TaggedEmbedder(dim=512)
    fresh = InMemoryVectorStore()
    stats = reindex(
        session, embedder=new_embedder, store=fresh, storage=storage,
        re_embed=True,
    )
    assert stats.re_embedded == stats.indexed > 0
    assert stats.fetch_failed == 0

    # Every catalogue image now records the new model.
    from encounter.enums import ImageType
    from encounter.models import Image
    rows = session.query(Image).filter(
        Image.image_type == ImageType.official_product_image
    ).all()
    assert rows and all(r.embedding_model == "siglip-fake" for r in rows)


def test_reindex_scoped_to_brand(session):
    embedder = PerceptualEmbedder(dim=512)
    storage = LocalStorage()
    _import(session, InMemoryVectorStore(), storage, embedder)

    fresh = InMemoryVectorStore()
    hit = reindex(session, embedder=embedder, store=fresh, storage=storage,
                  brand="Tom Dixon")
    miss = reindex(session, embedder=embedder, store=InMemoryVectorStore(),
                   storage=storage, brand="Nonexistent Brand")
    assert hit.indexed > 0
    assert miss.indexed == 0
