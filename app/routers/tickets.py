import logging

from fastapi import APIRouter, HTTPException, Query, Request

from app.repository import TicketRepository
from app.schemas import Category, Priority, Status, TicketCreate, TicketOut

router = APIRouter(prefix="/tickets", tags=["tickets"])
log = logging.getLogger("flowdesk.api")


def _repo(request: Request) -> TicketRepository:
    return request.app.state.repo


@router.post("", response_model=TicketOut, status_code=201)
def create_ticket(body: TicketCreate, request: Request):
    max_chars = request.app.state.settings.max_message_chars
    message = body.message[:max_chars]
    out = request.app.state.pipeline.run(message)  # never raises; degrades to human review
    ticket = _repo(request).create(message, out.result)
    try:
        request.app.state.metrics.record(ticket.id, out.stats, out.result)
    except Exception:
        log.exception("metrics recording failed for ticket=%s", ticket.id)
    return ticket


@router.get("", response_model=list[TicketOut])
def list_tickets(
    request: Request,
    category: Category | None = None,
    priority: Priority | None = None,
    status: Status | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return _repo(request).list(category, priority, status, limit, offset)


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, request: Request):
    ticket = _repo(request).get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket
