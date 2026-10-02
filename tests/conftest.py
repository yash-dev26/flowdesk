import json
from pathlib import Path

import pytest

from app.config import Settings
from app.llm.fake import FakeLLM
from app.rag.embeddings import HashingEmbeddings
from app.rag.kb import build_vectorstore
from app.triage.graph import TriagePipeline

KB_DIR = str(Path(__file__).resolve().parent.parent / "kb")


def triage_json(**over) -> str:
    base = {
        "category": "billing", "priority": "high", "sentiment": "negative",
        "entities": {"order_id": None, "email": None}, "language": "en",
        "injection_suspected": False, "search_queries": ["charged twice duplicate charge"],
    }
    base.update(over)
    return json.dumps(base)


def reply_json(**over) -> str:
    base = {"answerable": True, "reply": "A second charge is often a pending authorization.",
            "article_ids": ["billing-duplicate-charge"]}
    base.update(over)
    return json.dumps(base)


@pytest.fixture(scope="session")
def vectorstore():
    return build_vectorstore(KB_DIR, HashingEmbeddings())


@pytest.fixture()
def make_pipeline(vectorstore):
    def _make(script, vs="default"):
        fake = FakeLLM(script)
        settings = Settings(llm_max_retries=1, retrieval_min_score=0.2, embedding_provider="hashing")
        store = vectorstore if vs == "default" else vs
        return TriagePipeline(fake, store, settings, sleep=lambda s: None), fake
    return _make
