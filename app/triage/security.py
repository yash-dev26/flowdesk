"""Prompt-injection defences that do not depend on the model behaving.

Layers (see README): 1) heuristic detection, 2) delimiter + sanitising so the
customer text stays data, 3) the LLM has no tools and no authority, 4) output
guards that reject replies claiming an action was taken or citing unknown articles.
"""
import re

from app.schemas import EMAIL_RE, Entities

_INJECTION_PATTERNS = [
    # English and Hinglish: "ignore previous instructions", "instructions ignore karo"
    r"(ignore|disregard|forget|bhool|bhul)\W+(?:\w+\W+){0,4}(instruction|rule|prompt|nirdesh)",
    r"(instruction|rule|prompt|nirdesh)\w*\W+(?:\w+\W+){0,3}(ignore|bhool|bhul)",
    r"(reveal|show|print|repeat|leak)\W+(?:\w+\W+){0,4}(system prompt|your prompt|your instructions)",
    r"system prompt",
    r"you are now\b",
    r"\b(developer|admin|god|dan) mode\b",
    r"\bjailbreak",
    r"</?\s*(system|assistant|customer_message)\s*>",
    r"\[/?inst\]",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJECTION_PATTERNS), re.IGNORECASE)

_ACTION_CLAIM_RE = re.compile(
    r"\b(i|we)(?:'ve| have)\s+(approved|processed|issued|refunded|credited|cancell?ed|upgraded|deleted|reset|escalated)\b"
    r"|\b(refund|request|cancellation|upgrade)\s+(?:has been|have been|is now|was)\s+(approved|processed|issued|completed|granted)\b"
    r"|\b(has|have) been (approved|refunded|credited|processed|issued)\b",
    re.IGNORECASE,
)

_DELIMITER_RE = re.compile(r"</?\s*customer_message\s*>", re.IGNORECASE)


def detect_injection(message: str) -> list[str]:
    """Return the matched suspicious snippets (empty list = nothing found)."""
    return [m.group(0).strip()[:60] for m in _INJECTION_RE.finditer(message)]


def sanitize(message: str) -> str:
    """Stop the customer closing our delimiter early and smuggling in instructions."""
    return _DELIMITER_RE.sub("", message).strip()


def reply_claims_action(reply: str) -> bool:
    return bool(_ACTION_CLAIM_RE.search(reply))


def reconcile_entities(entities: Entities, message: str) -> Entities:
    """Keep only entities that literally appear in the message; backfill email by regex."""
    flat = re.sub(r"[#\s]", "", message).lower()
    order_id = entities.order_id
    if order_id and re.sub(r"[#\s]", "", order_id).lower() not in flat:
        order_id = None
    email = entities.email
    if email and email.lower() not in message.lower():
        email = None
    if not email:
        m = EMAIL_RE.search(message)
        email = m.group(0) if m else None
    return Entities(order_id=order_id, email=email)
