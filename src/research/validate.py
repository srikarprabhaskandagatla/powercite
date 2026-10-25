import re

LIMITS = {"demand_charges": (0, 100), "incentives": (0, 1000)}
VALUE_FIELD = {"demand_charges": "usd_per_unit", "incentives": "usd_per_kw"}


def squash(text):
    return re.sub(r"\s+", " ", text or "").strip()


def value_forms(value):
    return {f"{value:.2f}", f"{value:g}", f"{value:,.2f}", f"{value:,.0f}" if value == int(value) else f"{value:.2f}"}


def check_item(item, kind, page_text):
    value = item[VALUE_FIELD[kind]]
    low, high = LIMITS[kind]
    quote = squash(item["quote"])
    checks = {
        "quote_in_page": bool(quote) and quote in squash(page_text),
        "value_in_quote": any(form in quote for form in value_forms(value)),
        "value_in_range": low < value < high,
    }
    return checks, all(checks.values())


def validate(facts, page_text):
    accepted = {"demand_charges": [], "incentives": []}
    rejected = []
    for kind in accepted:
        for item in facts[kind]:
            checks, ok = check_item(item, kind, page_text)
            if ok:
                accepted[kind].append(item)
            else:
                rejected.append({"kind": kind, "item": item, "checks": checks})
    effective_ok = facts.get("effective_quote") is not None and squash(facts["effective_quote"]) in squash(page_text)
    return {
        "utility": facts.get("utility"),
        "effective_date": facts.get("effective_date") if effective_ok else None,
        "effective_quote": facts.get("effective_quote") if effective_ok else None,
        **accepted,
        "rejected": rejected,
    }
