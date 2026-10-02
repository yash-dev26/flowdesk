import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app import demo
from app.errors import register_error_handlers
from app.llm.factory import build_provider
from app.observability import MetricsStore
from app.rag.embeddings import build_embeddings
from app.rag.kb import build_vectorstore, load_articles
from app.repository import TicketRepository
from app.routers import metrics, tickets
from app.triage.graph import TriagePipeline

log = logging.getLogger("flowdesk")
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def _build_vectorstore(settings: Settings):
    """A broken embedding model or empty KB degrades to 'human review', not a crash."""
    try:
        return build_vectorstore(settings.kb_dir, build_embeddings(settings))
    except Exception:
        log.exception("knowledge base unavailable; tickets will be routed to human review")
        return None


def create_app(settings: Settings | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings or get_settings()
    app = FastAPI(title="Flowdesk Ticket Triage", version="0.2.0")
    app.state.settings = settings
    app.state.repo = TicketRepository(settings.db_path)
    app.state.metrics = MetricsStore(settings.db_path)
    provider = build_provider(settings)
    app.state.llm = demo.FaultInjectingProvider(provider) if settings.demo_mode else provider
    app.state.pipeline = TriagePipeline(app.state.llm, _build_vectorstore(settings), settings)
    register_error_handlers(app)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    app.include_router(tickets.router)
    app.include_router(metrics.router)
    if settings.demo_mode:
        app.state.kb_articles = load_articles(settings.kb_dir)
        app.include_router(demo.router)

    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")

    return app


app = create_app()
