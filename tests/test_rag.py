from app.rag.kb import load_articles
from tests.conftest import KB_DIR


def test_kb_has_at_least_10_articles_with_unique_ids():
    docs = load_articles(KB_DIR)
    ids = [d.metadata["id"] for d in docs]
    assert len(ids) >= 10 and len(set(ids)) == len(ids)


def test_relevant_query_finds_right_article(vectorstore):
    top, score = vectorstore.similarity_search_with_score("charged twice duplicate charge", k=1)[0]
    assert top.metadata["id"] == "billing-duplicate-charge" and score > 0.2


def test_irrelevant_query_scores_below_threshold(vectorstore):
    scores = [s for _, s in vectorstore.similarity_search_with_score("weather forecast tomorrow", k=3)]
    assert max(scores) < 0.2
