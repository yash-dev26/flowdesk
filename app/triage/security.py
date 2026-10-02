"""Prompt-injection defences that do not depend on the model behaving.

Layers (see README): 1) heuristic detection, 2) delimiter + sanitising so the
customer text stays data, 3) the LLM has no tools and no authority, 4) output
guards that reject replies claiming an action was taken or citing unknown articles.
"""
import re

from app.schemas import EMAIL_RE, Entities

_VERB = r"(?:ignore|disregard|override|bypass)"
_NOUN = r"(?:instructions?|rules|prompts?|guidelines|directions)"
_INJECTION_PATTERNS = [
    # "ignore all previous instructions", "disregard your prior rules"
    rf"\b(?:{_VERB}|forget)\W+(?:(?:all|any|of|the|your|my|these|those)\W+){{0,2}}"
    rf"(?:previous|prior|above|earlier|preceding|original|initial|system|safety)\W+(?:\w+\W+)?{_NOUN}",
    # "ignore your instructions", "bypass all rules" (not "ignore my ticket")
    rf"\b{_VERB}\W+(?:all|any|your|these)\W+{_NOUN}",
    # Hinglish: "pichle saare instructions ignore karo", "instructions ignore karo"
    r"\b(?:pichle|purane|saare|sare|sabhi|upar ke)\W+(?:\w+\W+){0,2}(?:instruction|rules?|nirdesh)\w*\W+(?:\w+\W+){0,3}(?:ignore|bhool|bhul)",
    r"\b(?:instruction|nirdesh)\w*\W+ignore\W+kar",
    r"\b(?:reveal|show|print|repeat|leak)\W+(?:\w+\W+){0,4}(?:system prompt|your prompt|your instructions)",
    r"\bsystem prompt",
    r"\byou are now (?:an? |the )?(?:admin\w*|developer|dan|unrestricted|jailbroken|root)\b",
    r"\b(?:developer|admin|god|dan) mode\b",
    r"\bjailbreak",
    r"</?\s*(?:system|assistant|customer_message)\s*>",
    r"\[/?inst\]",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJECTION_PATTERNS), re.IGNORECASE)

# Completed-action claims: first person ("I have approved ...") or about the customer's own
# case ("your refund has been approved"). Generic policy text ("approved refunds reach ...")
# and conditionals ("if your refund is approved") are fine.
_ACTION = r"(?:approved|processed|issued|refunded|credited|cancell?ed|upgraded|deleted|reset|escalated|granted|completed)"
_ACTION_CLAIM_RE = re.compile(
    rf"\b(?:i|we)(?:'ve| have)\s+{_ACTION}\b"
    rf"|\byour\s+(?:\w+\s+){{0,2}}(?:refund|request|cancellation|upgrade|account|ticket|payment|invoice)"
    rf"\s+(?:has been|have been|is now|was|is)\s+{_ACTION}\b",
    re.IGNORECASE,
)
_CONDITIONAL_RE = re.compile(r"\b(?:if|once|when|after|until|unless|whether)\b", re.IGNORECASE)

_DELIMITER_RE = re.compile(r"</?\s*customer_message\s*>", re.IGNORECASE)


def detect_injection(message: str) -> list[str]:
    """Return the matched suspicious snippets (empty list = nothing found)."""
    return [m.group(0).strip()[:60] for m in _INJECTION_RE.finditer(message)]


def sanitize(message: str) -> str:
    """Stop the customer closing our delimiter early and smuggling in instructions."""
    return _DELIMITER_RE.sub("", message).strip()


def reply_claims_action(reply: str) -> bool:
    for m in _ACTION_CLAIM_RE.finditer(reply):
        clause_start = max(reply.rfind(c, 0, m.start()) for c in ".!?,;") + 1
        if not _CONDITIONAL_RE.search(reply[clause_start:m.start()]):
            return True  # a real claim, not "if your refund is approved, ..."
    return False


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
