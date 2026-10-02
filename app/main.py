from fastapi import FastAPI

from app.config import Settings, get_settings
from app.repository import TicketRepository
from app.routers import tickets


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Flowdesk Ticket Triage", version="0.1.0")
    app.state.settings = settings
    app.state.repo = TicketRepository(settings.db_path)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    app.include_router(tickets.router)
    return app


app = create_app()
