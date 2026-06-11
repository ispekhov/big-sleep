from encounter.embeddings.fallback import PerceptualEmbedder
from encounter.importer.pipeline import ImportPipeline
from encounter.search.service import SearchService
from encounter.storage.local import LocalStorage
from encounter.vectorstore.memory import InMemoryVectorStore
from tests.conftest import make_jpeg
from tests.test_pipeline import IMAGES, downloader, fetcher


def _setup(session):
    embedder = PerceptualEmbedder(dim=512)
    store = InMemoryVectorStore()
    storage = LocalStorage()
    ImportPipeline(
        session, fetcher=fetcher, downloader=downloader,
        embedder=embedder, storage=storage, vector_store=store,
    ).run("https://tomdixon.net")
    service = SearchService(
        session, embedder=embedder, vector_store=store, storage=storage
    )
    return service


def test_search_identifies_correct_product(session):
    service = _setup(session)
    # Query with the same image used for the Melt Pendant -> exact match.
    result = service.search(IMAGES["https://cdn.x/melt.jpg"], store_query=False)
    assert result.top_candidate is not None
    assert result.top_candidate.product_name == "Melt Pendant"
    assert result.top_candidate.confidence > 0.9
    assert result.top_candidate.brand == "Tom Dixon"


def test_search_ranks_beat_for_dark_image(session):
    service = _setup(session)
    result = service.search(IMAGES["https://cdn.x/beat.jpg"], store_query=False)
    assert result.top_candidate.product_name == "Beat Light"


def test_search_persists_query_image(session):
    service = _setup(session)
    from encounter.enums import ImageType
    from encounter.models import Image

    result = service.search(make_jpeg(color=(10, 200, 10), seed=99), store_query=True)
    assert result.query_image_id > 0
    img = session.get(Image, result.query_image_id)
    assert img.image_type == ImageType.user_query_image


def test_search_empty_index_returns_no_candidate(session):
    service = SearchService(
        session, embedder=PerceptualEmbedder(dim=128),
        vector_store=InMemoryVectorStore(), storage=LocalStorage(),
    )
    result = service.search(make_jpeg(), store_query=False)
    assert result.top_candidate is None
