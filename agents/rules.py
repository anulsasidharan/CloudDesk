"""Deterministic policy rules: category, severity and escalation (F2, F3, F10).

"Rules first, LLM second" (CLAUDE.md 7.2). Policy cases are decided here, never left to a model's
probability. The model adds judgement only where no rule applies. Everything below is a pure
function of the ticket text and the customer's plan; no I/O, no model call.

* Category: ``rule_category`` returns a category or ``None`` (no opinion).
* Severity: rules can RAISE the model's severity, never lower it (``raise_severity``).
* Escalation: ``ESCALATION_RULES`` always win over the model (``rule_escalation``).

All matching runs on text with injected instructions stripped out, so a sentence aimed at the
model cannot steer a rule.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.core.guardrails import strip_injection
from app.schemas.common import Category, Severity

# --------------------------------------------------------------------------------------------
# Text preparation
# --------------------------------------------------------------------------------------------


def _prepare(text: str) -> str:
    """Strip injected sentences, lowercase, fold curly apostrophes, collapse whitespace."""
    cleaned = strip_injection(text or "").lower().replace("’", "'")
    return re.sub(r"\s+", " ", cleaned)


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


# --------------------------------------------------------------------------------------------
# Severity ordering
# --------------------------------------------------------------------------------------------

SEVERITY_ORDER: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


def max_severity(*levels: Severity) -> Severity:
    return max(levels, key=SEVERITY_ORDER.__getitem__)


# --------------------------------------------------------------------------------------------
# Escalation rules (F10)
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EscalationRule:
    """One policy case. ``all_of`` lists pattern groups that must EACH match somewhere."""

    id: str
    team: str
    severity: Severity
    reason: str
    all_of: tuple[tuple[re.Pattern[str], ...], ...]
    plans: frozenset[str] | None = None  # None = every plan


_LOSS_WORDS = r"(?:disappear(?:ed)?|vanish(?:ed)?|gone|missing|deleted|lost|wiped|corrupt(?:ed)?)"
_DATA_NOUNS = r"(?:files?|documents?|folders?|data|records|scans?|backups?|photos?|images?)"

#: Order is priority: the first match names the team when several fire.
ESCALATION_RULES: tuple[EscalationRule, ...] = (
    EscalationRule(
        id="security_incident",
        team="security_response",
        severity=Severity.CRITICAL,
        reason="Possible account compromise or security incident",
        all_of=(
            (
                _rx(
                    r"\b(?:breach(?:ed)?|compromis(?:ed|e)|hack(?:ed|ing)|account takeover"
                    r"|suspicious (?:log-?ins?|sign-?ins?|activity)"
                    r"|unauthori[sz]ed (?:access|log-?ins?|sign-?ins?)"
                    r"|(?:stolen|leaked) (?:credentials|passwords?|tokens?|api keys?)"
                    r"|phishing|malware|ransomware)\b"
                ),
            ),
        ),
    ),
    EscalationRule(
        id="data_loss",
        team="data_integrity",
        severity=Severity.CRITICAL,
        reason="Customer data is reported missing or lost",
        all_of=(
            (
                _rx(rf"\b{_DATA_NOUNS}\b[^.]{{0,60}}\b{_LOSS_WORDS}\b"),
                _rx(rf"\b{_LOSS_WORDS}\b[^.]{{0,25}}\b{_DATA_NOUNS}\b"),
            ),
        ),
    ),
    EscalationRule(
        id="legal",
        team="legal_team",
        severity=Severity.HIGH,
        reason="Legal threat or legal process mentioned",
        all_of=(
            (
                _rx(
                    r"\b(?:lawsuit|sue|suing|legal action|attorney|lawyer|solicitor|subpoena"
                    r"|court order|litigation|cease and desist|legal hold)\b"
                ),
            ),
        ),
    ),
    EscalationRule(
        id="account_deletion",
        team="privacy_compliance",
        severity=Severity.HIGH,
        reason="Account, workspace or data deletion or erasure request",
        all_of=(
            (
                _rx(
                    r"\b(?:delete|erase|purge|wipe|remove)\b[^.]{0,60}"
                    r"\b(?:account|workspace|all (?:of )?(?:our |my |the )?data|personal data)\b"
                ),
                _rx(
                    r"\b(?:right to erasure|right to be forgotten|gdpr|ccpa|data subject"
                    r"|erasure request|data deletion)\b"
                ),
            ),
        ),
    ),
    EscalationRule(
        id="payment_dispute",
        team="billing_disputes",
        severity=Severity.HIGH,
        reason="Payment dispute, chargeback or unauthorised charge",
        all_of=(
            (
                _rx(r"\bchargebacks?\b"),
                _rx(
                    r"\b(?:unauthori[sz]ed|fraudulent|unrecogni[sz]ed)\s+"
                    r"(?:charges?|payments?|transactions?|debits?)\b"
                ),
                _rx(
                    r"\b(?:disputes?|disputed|disputing)\b[^.]{0,60}"
                    r"\b(?:charges?|payments?|invoices?|bank|card|transactions?)\b"
                ),
                _rx(
                    r"\b(?:charges?|payments?|invoices?|bank|card|transactions?)\b[^.]{0,60}"
                    r"\b(?:disputes?|disputed|disputing)\b"
                ),
            ),
        ),
    ),
    EscalationRule(
        id="enterprise_outage",
        team="incident_response",
        severity=Severity.CRITICAL,
        reason="Enterprise customer reports an outage affecting many users",
        all_of=(
            (
                _rx(
                    r"\b(?:whole|entire) (?:team|company|org(?:ani[sz]ation)?)\b"
                    r"|\b(?:all|none|every one) of (?:our|my|the)\b"
                    r"|\b(?:nobody|no one) (?:in|on|at|can)\b|\bnone of us\b|\beveryone\b"
                    r"|\ball (?:of )?(?:our )?users\b"
                ),
            ),
            (
                _rx(
                    r"\b(?:cannot|can't|unable|fails?|failing|failed|down|outage|not working"
                    r"|blocked|locked out|50[0-4])\b"
                ),
            ),
        ),
        plans=frozenset({"enterprise"}),
    ),
)


def _rule_matches(rule: EscalationRule, text: str, plan_name: str | None) -> bool:
    if rule.plans is not None and (plan_name or "").lower() not in rule.plans:
        return False
    return all(any(p.search(text) for p in group) for group in rule.all_of)


def matching_escalation_rules(text: str, plan_name: str | None = None) -> list[EscalationRule]:
    """Every policy rule that fires for this ticket text and plan, in priority order."""
    prepared = _prepare(text)
    return [r for r in ESCALATION_RULES if _rule_matches(r, prepared, plan_name)]


@dataclass(frozen=True)
class PolicyEscalation:
    """The decision when at least one policy rule fires. The model cannot overturn it."""

    team: str
    severity: Severity
    reason: str
    rule_ids: tuple[str, ...]


def rule_escalation(text: str, plan_name: str | None = None) -> PolicyEscalation | None:
    """Policy decision for a ticket, or ``None`` when no rule applies (model judges)."""
    matched = matching_escalation_rules(text, plan_name)
    if not matched:
        return None
    return PolicyEscalation(
        team=matched[0].team,
        severity=max_severity(*(r.severity for r in matched)),
        reason="; ".join(r.reason for r in matched),
        rule_ids=tuple(r.id for r in matched),
    )


# --------------------------------------------------------------------------------------------
# Category rules (F2)
# --------------------------------------------------------------------------------------------

# (pattern, weight). Highest total wins; ties go to the earlier entry (priority order).
_CATEGORY_RULES: tuple[tuple[Category, tuple[tuple[re.Pattern[str], int], ...]], ...] = (
    (
        Category.SECURITY,
        (
            (
                _rx(
                    r"\b(?:breach(?:ed)?|compromis(?:ed|e)|hack(?:ed|ing)|phishing|malware"
                    r"|ransomware|account takeover)\b"
                ),
                3,
            ),
            (_rx(r"\bsuspicious\b|\bunauthori[sz]ed (?:access|log-?ins?|sign-?ins?)\b"), 3),
        ),
    ),
    (
        Category.BILLING,
        (
            (_rx(r"\b(?:refunds?|chargebacks?|invoices?|billing)\b"), 3),
            (_rx(r"\b(?:charge[ds]?|payments?|credit card|card|bank|price|pricing)\b"), 2),
            (_rx(r"\b(?:dispute[ds]?|disputing|subscription cost)\b"), 2),
        ),
    ),
    (
        Category.ACCOUNT,
        (
            (
                _rx(
                    r"\b(?:delete|erase|close|remove|transfer)\b[^.]{0,40}"
                    r"\b(?:account|workspace|ownership)\b"
                ),
                3,
            ),
            (_rx(r"\b(?:gdpr|ccpa|right to erasure|right to be forgotten)\b"), 3),
        ),
    ),
    (
        Category.LOGIN_ISSUE,
        (
            (_rx(r"\b(?:sso|saml|okta|mfa|2fa|two-factor|authenticator|passkey)\b"), 3),
            (
                _rx(
                    r"\b(?:sign(?:ing)? in|log(?:ging)? in|log-?ins?|sign-?ins?|locked out"
                    r"|password reset|reset (?:my |the )?password)\b"
                ),
                2,
            ),
        ),
    ),
    (
        Category.API_FAILURE,
        (
            (_rx(r"\b429\b|\brate[- ]?limit(?:s|ed|ing)?\b"), 3),
            (_rx(r"\b(?:api|endpoints?|webhooks?|sdk)\b"), 2),
        ),
    ),
    (
        Category.STORAGE_QUOTA,
        (
            (_rx(r"\bquota\b|\bstorage (?:limit|full|space)\b|\bout of (?:space|storage)\b"), 3),
            (_rx(r"\b(?:uploads?|storage)\b"), 1),
        ),
    ),
    (
        Category.INTEGRATION,
        (
            (
                _rx(
                    r"\b(?:slack|zapier|jira|github|salesforce|microsoft teams|google drive"
                    r"|integrations?)\b"
                ),
                3,
            ),
        ),
    ),
    (
        Category.WORKSPACE_PERMISSIONS,
        (
            (_rx(r"\b(?:permissions?|external(?:ly)? shar\w+|shar(?:e|ing) (?:a |the )?folder)\b"), 3),
            (_rx(r"\b(?:share|sharing|invite|guest|read-only|access to)\b"), 1),
        ),
    ),
    (
        Category.FEATURE_REQUEST,
        (
            (
                _rx(
                    r"\b(?:feature request|dark mode|add support for|would be (?:great|nice)"
                    r"|any chance you could add|please add|wish (?:you|it) (?:had|could)"
                    r"|suggestion)\b"
                ),
                3,
            ),
        ),
    ),
)

DEFAULT_CATEGORY = Category.OTHER


def rule_category(text: str) -> Category | None:
    """Best keyword match, or ``None`` when no rule has an opinion (the model decides)."""
    prepared = _prepare(text)
    best: Category | None = None
    best_score = 0
    for category, patterns in _CATEGORY_RULES:
        score = sum(weight for pattern, weight in patterns if pattern.search(prepared))
        if score > best_score:  # strict: ties keep the earlier (higher-priority) category
            best, best_score = category, score
    return best


# --------------------------------------------------------------------------------------------
# Severity rules (F3)
# --------------------------------------------------------------------------------------------

_HIGH_SIGNALS = _rx(
    r"\b(?:urgent(?:ly)?|asap|immediately|emergency|deadline|regulatory|inspection"
    r"|blocks? (?:our|the) (?:whole|entire)|production)\b"
)


@dataclass(frozen=True)
class SeverityVerdict:
    """Rule floor for severity. ``matched=False`` means no rule had an opinion."""

    severity: Severity
    reason: str
    matched: bool
    rule_ids: tuple[str, ...] = ()


def rule_severity(
    text: str, category: Category | None = None, plan_name: str | None = None
) -> SeverityVerdict:
    """The lowest severity policy allows for this ticket (a floor, never a ceiling)."""
    category = category or rule_category(text)
    prepared = _prepare(text)
    floors: list[tuple[Severity, str, str]] = []

    for rule in matching_escalation_rules(text, plan_name):
        floors.append((rule.severity, rule.reason, rule.id))
    if _HIGH_SIGNALS.search(prepared):
        floors.append((Severity.HIGH, "Customer signals urgency or a deadline", "urgency"))
    if category is Category.BILLING and re.search(r"\brefunds?\b", prepared):
        floors.append((Severity.MEDIUM, "Refund request moves money", "refund_request"))
    if category is Category.FEATURE_REQUEST:
        floors.append((Severity.LOW, "Feature requests are low severity by policy", "feature"))

    if not floors:
        return SeverityVerdict(Severity.LOW, "No severity rule matched", matched=False)
    top = max_severity(*(f[0] for f in floors))
    top_floors = [f for f in floors if f[0] is top]
    return SeverityVerdict(
        severity=top,
        reason="; ".join(f[1] for f in top_floors),
        matched=True,
        rule_ids=tuple(f[2] for f in floors),
    )


def raise_severity(model_severity: Severity | str | None, verdict: SeverityVerdict) -> Severity:
    """Combine the model's severity with the rule floor. Rules may raise it, never lower it."""
    if model_severity is None:
        return verdict.severity
    model = Severity(model_severity)
    return max_severity(model, verdict.severity) if verdict.matched else model


def escalation_teams() -> Iterable[str]:
    """Names of every team a policy rule can route to (used by docs, UI and tests)."""
    return dict.fromkeys(rule.team for rule in ESCALATION_RULES)
