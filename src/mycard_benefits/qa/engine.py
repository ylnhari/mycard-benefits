"""Conservative token grammar for deterministic public catalog questions.

Only the documented phrases below are interpreted; all other text is plain,
ephemeral input and receives a bounded clarification rather than a guess.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from mycard_benefits.catalog import Catalog
from mycard_benefits.catalog.model import BenefitRule, Offering

MAX_QUERY_LENGTH = 500
MAX_FACTS = 12
_TYPES = frozenset({"reward_points", "conversion", "movie", "hotel", "food", "cashback", "voucher", "meet_and_greet", "lounge", "priority_pass", "other"})


def answer(catalog: Catalog, query: str, *, as_of: date | None = None) -> dict[str, Any]:
    """Interpret `benefits for OFFERING`, `offerings for TYPE`, `benefit TYPE for OFFERING`, or `compare A and B`."""
    tokens = _tokens(query)
    as_of = as_of or catalog.release.generated_at.date()
    all_offerings = tuple(sorted(catalog.offerings, key=lambda item: item.slug))
    offerings = tuple(item for item in all_offerings if _in_range(as_of, item.effective_from, item.effective_to))
    mentioned = _mentions(offerings, tokens)
    inactive_mentioned = _mentions(all_offerings, tokens)
    if len(mentioned) > 1 and not (tokens and tokens[0] == "compare"):
        return {**_safe("ambiguous", "More than one offering matched; choose one."), "choices": [_offering(item) for item in mentioned[:MAX_FACTS]]}
    if tokens[:1] == ("compare",):
        if len(mentioned) != 2:
            return _safe("compare_offerings", "Use compare followed by exactly two offering names.")
        return {"intent": "compare_offerings", "offerings": [{"offering": _offering(item), "benefits": _facts(catalog, as_of, offering=item)} for item in mentioned]}
    if tokens[:2] == ("offerings", "for"):
        benefit_type = _type("_".join(tokens[2:]))
        if benefit_type is None:
            return _safe("offerings_by_benefit", "Use a supported benefit type.")
        facts = _facts(catalog, as_of, benefit_type=benefit_type)
        groups: dict[str, dict[str, Any]] = {}
        for fact in facts:
            groups.setdefault(str(fact["offering"]["id"]), {"offering": fact["offering"], "benefits": []})["benefits"].append(fact)
        if not groups:
            return _safe("no_result", "No approved active in-date benefit matched.")
        return {"intent": "offerings_by_benefit", "benefit_type": benefit_type, "offerings": list(groups.values())[:MAX_FACTS]}
    if tokens[:1] == ("benefit",) and "for" in tokens:
        split = tokens.index("for")
        if split < 2:
            return _safe("benefit_detail", "Use benefit TYPE for OFFERING.")
        benefit_type = _type("_".join(tokens[1:split]))
        if benefit_type is None:
            return _safe("benefit_detail", "Use benefit TYPE for exactly one offering.")
        if len(mentioned) != 1:
            if len(inactive_mentioned) == 1:
                return _safe("no_result", "No approved active in-date benefit matched.")
            return _safe("benefit_detail", "Use benefit TYPE for exactly one offering.")
        facts = _facts(catalog, as_of, offering=mentioned[0], benefit_type=benefit_type)
        if not facts:
            return _safe("no_result", "No approved active in-date benefit matched.")
        return {"intent": "benefit_detail", "offering": _offering(mentioned[0]), "benefits": facts}
    if tokens[:2] == ("benefits", "for"):
        if len(mentioned) == 1:
            facts = _facts(catalog, as_of, offering=mentioned[0])
            if not facts:
                return _safe("no_result", "No approved active in-date benefit matched.")
            return {"intent": "offering_benefits", "offering": _offering(mentioned[0]), "benefits": facts}
        if len(inactive_mentioned) == 1:
            return _safe("no_result", "No approved active in-date benefit matched.")
    return _safe("unknown", "Use benefits for OFFERING, offerings for TYPE, benefit TYPE for OFFERING, or compare A and B.")


def _facts(catalog: Catalog, as_of: date, *, offering: Offering | None = None, benefit_type: str | None = None) -> list[dict[str, Any]]:
    facts = []
    owners = {item.id: item for item in catalog.offerings if _in_range(as_of, item.effective_from, item.effective_to)}
    for rule in catalog.benefits:
        if rule.offering_id not in owners or (offering and rule.offering_id != offering.id) or (benefit_type and rule.benefit_type != benefit_type):
            continue
        if rule.status != "active" or not _in_range(as_of, rule.effective_from, rule.effective_to):
            continue
        evidence = [item for item in rule.evidence if item.review_state == "approved" and item.confidence in {"high", "medium"} and _in_range(as_of, item.effective_from, item.effective_to)]
        if evidence:
            facts.append(_fact(rule, owners[rule.offering_id], evidence))
    return sorted(facts, key=lambda item: (str(item["offering"]["slug"]), str(item["benefit"]["id"])))[:MAX_FACTS]


def _fact(rule: BenefitRule, offering: Offering, evidence: list[Any]) -> dict[str, Any]:
    return {"benefit": {"id": rule.id, "type": rule.benefit_type, "title": rule.title}, "offering": _offering(offering), "evidence": [{"id": item.id, "url": item.url, "source_class": item.source_policy_class, "retrieved_at": item.retrieved_at.isoformat(), "effective_from": _date(item.effective_from), "effective_to": _date(item.effective_to), "confidence": item.confidence, "content_sha256": item.content_sha256} for item in sorted(evidence, key=lambda item: item.id)]}


def _mentions(offerings: tuple[Offering, ...], tokens: tuple[str, ...]) -> tuple[Offering, ...]:
    return tuple(item for item in offerings if any(_contains(tokens, _tokens(value)) for value in (item.slug, item.display_name, *item.aliases)))


def _contains(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    return bool(phrase) and any(tokens[index:index + len(phrase)] == phrase for index in range(len(tokens) - len(phrase) + 1))


def _tokens(query: str) -> tuple[str, ...]:
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LENGTH:
        raise ValueError("query must be a non-blank string of at most 500 characters")
    return tuple(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", query).casefold(), flags=re.UNICODE))


def _type(token: str) -> str | None:
    return token if token in _TYPES else None


def _offering(item: Offering) -> dict[str, str]:
    return {"id": item.id, "slug": item.slug, "display_name": item.display_name}


def _safe(intent: str, message: str) -> dict[str, Any]:
    return {"intent": intent, "message": message, "suggestions": ["benefits for OFFERING", "offerings for TYPE", "benefit TYPE for OFFERING", "compare A and B"]}


def _in_range(value: date, start: date | None, end: date | None) -> bool:
    return (start is None or start <= value) and (end is None or value <= end)


def _date(value: date | None) -> str | None:
    return value.isoformat() if value else None
