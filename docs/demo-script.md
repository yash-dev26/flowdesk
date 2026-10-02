# Demo video script (about 4 minutes)

Setup: `docker compose up --build`, open http://localhost:8000, failure toggle set to `off`.

1. **Intro (20s).** One sentence on the service, then point at the three areas: message box, result card, metrics and tickets.
2. **Normal billing ticket (40s).** Click *Billing*, analyse. Show category, priority, sentiment, extracted order ID and email, the drafted reply and its source article.
3. **Hinglish multi-issue (40s).** Click *Multi-issue*, then paste a Hinglish message. Show that both issues are covered and the sources come from two articles.
4. **Irrelevant message (30s).** Click *Irrelevant*. Show: no reply, human-review banner, reason "no help-center article answers this". Say why: the service never makes up an answer.
5. **Prompt injection (40s).** Click *Injection*. Show the red alert, review banner, and that no refund was approved. Mention the layers: detector, delimiters, no tools, output guard.
6. **Failure case (50s).** Set the toggle to `timeout`, analyse any message. Show the clean fallback ticket (other / medium / human review) with no error. Then `invalid_json` to show the repair then fallback. Back to `off`.
7. **Metrics (20s).** Show latency p50/p95, tokens, cost, fallback and review rates moving. Open `/metrics`.
8. **Eval and tests (30s).** Terminal: `python -m eval.run_eval` summary, then `pytest -q`.
9. **Close (10s).** Trade-offs and what you would improve next (README).
