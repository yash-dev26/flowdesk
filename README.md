# Flowdesk: AI Support Ticket Triage Service

Work in progress. Full README (architecture, decisions, eval results) lands in the final phase.

## Quick start (dev)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
pytest
```
