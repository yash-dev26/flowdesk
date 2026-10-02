import logging
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

log = logging.getLogger("flowdesk.rag")


def load_articles(kb_dir: str) -> list[Document]:
    """Each kb/<article-id>.md: first line `# Title`, rest is the body."""
    docs = []
    for path in sorted(Path(kb_dir).glob("*.md")):
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        title = lines[0].lstrip("# ").strip()
        body = " ".join(l.strip() for l in lines[1:] if l.strip())
        docs.append(Document(
            page_content=f"{title}. {body}",
            metadata={"id": path.stem, "title": title},
        ))
    return docs


def build_vectorstore(kb_dir: str, embeddings: Embeddings) -> InMemoryVectorStore:
    docs = load_articles(kb_dir)
    if not docs:
        raise ValueError(f"No knowledge base articles found in {kb_dir!r}")
    store = InMemoryVectorStore(embeddings)
    store.add_documents(docs, ids=[d.metadata["id"] for d in docs])
    log.info("knowledge base indexed: %d articles", len(docs))
    return store
