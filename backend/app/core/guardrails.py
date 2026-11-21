"""Deterministic guardrails: injection scan, secret scrub, customer-output validation.

Phase 7 (N4, N5, N7). Pure functions, no I/O, no model calls, so they are cheap to test and cannot
be talked out of a decision. ``core`` never imports ``agents/``; agents import from here.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

# --------------------------------------------------------------------------------------------
# Secret patterns (N7) - shared by `scrub` (memory notes) and `validate_customer_output` (N5)
# --------------------------------------------------------------------------------------------

REDACTED = "[REDACTED:{kind}]"

# Candidate card numbers (13-19 digits, optional space or dash separators). A candidate is only a
# card when it passes the Luhn check, so order numbers and phone numbers are left alone.
_CARD_CANDIDATE = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "private_key": re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)"
    ),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "bearer_token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    "api_key": re.compile(
        r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"  # OpenAI / Anthropic / Stripe style
        r"|\bAKIA[0-9A-Z]{16}\b"  # AWS access key id
        r"|\bgh[pousr]_[A-Za-z0-9]{20,}"  # GitHub tokens
        r"|\bxox[baprs]-[A-Za-z0-9-]{10,}"  # Slack tokens
        r"|\bAIza[0-9A-Za-z_-]{30,}"  # Google API keys
        r"|(?i:\b(?:api[_ -]?key|secret|access[_ -]?token|auth[_ -]?token)\b)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+]{12,}"
    ),
    # "password: hunter2" / "pwd=abc123" always; "password is X" only when X looks like a
    # password (has a digit or symbol), so "my password is wrong" survives.
    "password": re.compile(
        r"(?i:\b(?:password|passwd|pwd|passcode)\b\s*[:=]\s*['\"]?[^\s'\",;]{4,})"
        r"|(?i:\b(?:password|passwd|pwd|passcode)\b\s+is\s+(?=\S*[\d!@#$%^&*])"
        r"['\"]?[^\s'\",;]{4,})"
    ),
}
# A card is found by the Luhn-checked regex above, not by SECRET_PATTERNS. Listed so callers can
# see the complete set of kinds.
SECRET_KINDS: tuple[str, ...] = (*SECRET_PATTERNS, "card_number")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _is_card(candidate: str) -> bool:
    digits = re.sub(r"\D", "", candidate)
    return 13 <= len(digits) <= 19 and _luhn_ok(digits)


def find_secret_kinds(text: str) -> list[str]:
    """Kinds of secret present in ``text`` (never the secret values themselves)."""
    kinds = [kind for kind, pattern in SECRET_PATTERNS.items() if pattern.search(text)]
    if any(_is_card(m.group()) for m in _CARD_CANDIDATE.finditer(text)):
        kinds.append("card_number")
    return kinds


def contains_secret(text: str) -> bool:
    return bool(find_secret_kinds(text))


def scrub(text: str) -> str:
    """Replace card numbers, API keys and passwords with ``[REDACTED:<kind>]``. Idempotent."""
    for kind, pattern in SECRET_PATTERNS.items():
        text = pattern.sub(REDACTED.format(kind=kind), text)
    return _CARD_CANDIDATE.sub(
        lambda m: REDACTED.format(kind="card_number") if _is_card(m.group()) else m.group(),
        text,
    )


# --------------------------------------------------------------------------------------------
# Prompt-injection scan (N4)
# --------------------------------------------------------------------------------------------

_INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "override_instructions": re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\b[^.\n]{0,30}"
        r"\b(?:previous|prior|above|earlier|all|any|your|the)\b[^.\n]{0,30}"
        r"\b(?:instructions?|prompts?|rules?|guidelines?|polic(?:y|ies)|restrictions?)\b"
    ),
    "role_hijack": re.compile(
        r"\byou are now\b|\bact as (?:an? )?(?:admin|administrator|root|developer|system)\b"
        r"|\bpretend (?:to be|you are)\b|\b(?:admin|developer|dan|god|debug|jailbreak) mode\b"
    ),
    "prompt_extraction": re.compile(
        r"\b(?:reveal|show|print|repeat|output|leak)\b[^.\n]{0,30}"
        r"\b(?:system prompt|hidden prompt|your instructions|your prompt)\b"
    ),
    "data_exfiltration": re.compile(
        r"\b(?:export|dump|send|list|email|exfiltrate|include)\b[^.\n]{0,25}"
        r"\b(?:all|every|each|entire|full)\b[^.\n]{0,25}"
        r"\b(?:customers?|users?|accounts?)\b[^.\n]{0,20}"
        r"\b(?:records?|data|emails?|details|information|list|database)\b"
    ),
    "unauthorised_action": re.compile(
        r"\b(?:approve|issue|grant|process|give)\b[^.\n]{0,20}\brefunds?\b[^.\n]{0,20}"
        r"\b(?:for|to)\b[^.\n]{0,10}\b(?:every|all|each)\b"
        r"|\b(?:disable|turn off|skip)\b[^.\n]{0,20}\b(?:approval|safety|guardrails?|checks?)\b"
    ),
    "delimiter_spoof": re.compile(
        r"</?\s*untrusted_content\b|<\|\s*(?:im_start|im_end|system)\s*\|>|\[/?inst\]"
        r"|^\s*(?:system|assistant)\s*:",
        re.MULTILINE,
    ),
    "new_instructions": re.compile(r"\bnew (?:instructions?|rules?|system prompt)\s*:"),
}

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))


def _normalise(text: str) -> str:
    """Fold look-alike characters, drop zero-width ones, lowercase, collapse spaces."""
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH).lower()
    return re.sub(r"[^\S\n]+", " ", text)


@dataclass(frozen=True)
class InjectionScan:
    flagged: bool
    matches: tuple[str, ...] = ()


def scan_for_injection(text: str) -> InjectionScan:
    """Flag text that tries to instruct the model. Flagging never blocks; it raises risk."""
    norm = _normalise(text or "")
    hits = tuple(name for name, pattern in _INJECTION_PATTERNS.items() if pattern.search(norm))
    return InjectionScan(flagged=bool(hits), matches=hits)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def strip_injection(text: str) -> str:
    """Drop the sentences that look like injected instructions; keep the genuine complaint.

    Rules (category, severity, escalation) read this cleaned text, so an attacker cannot steer
    them with a sentence that merely talks to the model.
    """
    kept = [s for s in _SENTENCE_SPLIT.split(text or "") if s and not scan_for_injection(s).flagged]
    return " ".join(kept)


# --------------------------------------------------------------------------------------------
# Customer output validation (N5)
# --------------------------------------------------------------------------------------------

#: A failed validation is, by definition, risk ``high`` (CLAUDE.md section 7.3).
OUTPUT_FAILURE_RISK: Literal["high"] = "high"

_URL = re.compile(r"(?i)\b(?:https?|ftp)://[^\s<>)\]\"']+|\bkb://[^\s<>)\]\"']+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_BARE_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_INTERNAL_PATH = re.compile(r"(?i)(?<![\w/])/(?:api/v\d+/|knowledge/[0-9a-f-]{8,}|tickets/CD-)\S*")
_INTERNAL_MARKERS = re.compile(
    r"(?i)<\s*/?\s*untrusted_content|\binternal (?:note|use only|only)\b"
    r"|\bsecurity preamble\b|\bsystem prompt\b"
)
_PRIVATE_HOST = re.compile(
    r"(?i)^(?:localhost|0\.0\.0\.0|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|169\.254\.\d+\.\d+"
    r"|[^.]+|.+\.(?:internal|local|localhost|lan|corp|intranet|home|test|svc|cluster\.local))$"
)

#: Mailboxes the company really publishes to customers. Staff and demo addresses are internal.
PUBLIC_EMAIL_DOMAINS: tuple[str, ...] = ("clouddesk.example",)


@dataclass(frozen=True)
class OutputViolation:
    kind: Literal["internal_url", "secret", "other_customer_data", "internal_marker"]
    detail: str  # a label, never the offending value (it could be the secret itself)


@dataclass(frozen=True)
class OutputValidation:
    ok: bool
    violations: tuple[OutputViolation, ...] = field(default_factory=tuple)

    @property
    def risk(self) -> Literal["low", "high"]:
        return OUTPUT_FAILURE_RISK if not self.ok else "low"


def _host_of(url: str) -> str:
    rest = url.split("://", 1)[1] if "://" in url else url
    host = re.split(r"[/?#]", rest, maxsplit=1)[0].rsplit("@", 1)[-1]
    return host.split(":", 1)[0].strip().lower()


def validate_customer_output(
    text: str,
    *,
    customer_email: str | None = None,
    allowed_emails: Iterable[str] = (),
    other_customer_markers: Iterable[str] = (),
) -> OutputValidation:
    """Check a drafted reply before a human or customer can see it as ready to send.

    ``other_customer_markers`` are names, companies, emails or ids that belong to *other*
    customers; the caller supplies them (the workflow knows who the customer is, this module
    does not). Any email address that is not the customer's own or a public company mailbox is
    treated as another party's data.
    """
    text = text or ""
    found: list[OutputViolation] = []

    for match in _URL.finditer(text):
        url = match.group()
        if url.lower().startswith("kb://") or _PRIVATE_HOST.match(_host_of(url)):
            found.append(OutputViolation("internal_url", "internal or private address"))
            break
    else:
        if _BARE_IP.search(text) or _INTERNAL_PATH.search(text):
            found.append(OutputViolation("internal_url", "internal path or IP address"))

    kinds = find_secret_kinds(text)
    if kinds:
        found.append(OutputViolation("secret", ", ".join(kinds)))

    allowed = {e.lower() for e in allowed_emails}
    if customer_email:
        allowed.add(customer_email.lower())
    for email in _EMAIL.findall(text):
        email = email.lower()
        if email in allowed or email.rsplit("@", 1)[1] in PUBLIC_EMAIL_DOMAINS:
            continue
        found.append(OutputViolation("other_customer_data", "email address that is not the customer's"))
        break
    lowered = text.lower()
    for marker in other_customer_markers:
        if marker and re.search(rf"(?<!\w){re.escape(marker.lower())}(?!\w)", lowered):
            found.append(OutputViolation("other_customer_data", "another customer's identifier"))
            break

    if _INTERNAL_MARKERS.search(text):
        found.append(OutputViolation("internal_marker", "internal wording or prompt markup"))

    return OutputValidation(ok=not found, violations=tuple(found))
