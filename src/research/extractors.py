import os
import re
from research.schemas import PageFacts

MODEL = "claude-haiku-5-5"
CLASS_HEADING = re.compile(r"^(G-\d+)\s*–")
EVERSOURCE_DEMAND = re.compile(r"^(.*Demand Charge) \(per (kW|kVA)\)(\(Optional\))?:?\s*\n\$(-?[\d.]+)", re.M)
NGRID_DEMAND = re.compile(r"Demand \$([\d.]+) per (kW|kVA)")
EFFECTIVE = re.compile(r"Effective:? ([A-Z][a-z]+ \d{1,2}, \d{4})")

SYSTEM_PROMPT = """You extract facts from Massachusetts electric utility tariff and incentive pages.
Use only the page text you are given. Never use outside knowledge.
For every value, copy a short quote that appears in the page exactly, character for character, and contains the number.
Demand charges are dollars per kW or per kVA of monthly peak demand, listed under a rate class such as G-2 or G-3. Ignore charges per kWh and per month.
Mark a demand charge optional when the page says it is optional.
Incentives are dollars per kW paid for reducing demand during peak events. Say whether each one is for business or residential customers and whether batteries qualify.
If the page does not state something, use null or an empty list."""


def has_key():
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def extract_llm(page, feedback=None):
    import anthropic
    client = anthropic.Anthropic()
    content = f"Page id: {page['id']}\nURL: {page['url']}\n\n<page>\n{page['text']}\n</page>"
    if feedback:
        content += f"\n\nYour last answer had items that failed checks. Fix or drop them:\n{feedback}"
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        output_format=PageFacts,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"no parsed output, stop_reason {response.stop_reason}")
    return response.parsed_output.model_dump()


def extract_rules(page):
    text = page["text"]
    charges = []
    rate_class = None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        heading = CLASS_HEADING.match(line.strip())
        if heading:
            rate_class = heading.group(1)
        if rate_class is None:
            continue
        window = "\n".join(lines[i:i + 2])
        match = EVERSOURCE_DEMAND.match(window.strip())
        if match:
            charges.append({
                "rate_class": rate_class,
                "component": match.group(1).replace(" Demand Charge", "").lower(),
                "usd_per_unit": float(match.group(4)),
                "unit": match.group(2),
                "optional": match.group(3) is not None,
                "quote": f"{line.strip()} {lines[i + 1].strip()}",
            })
            continue
        match = NGRID_DEMAND.search(line)
        if match:
            charges.append({
                "rate_class": rate_class,
                "component": "distribution",
                "usd_per_unit": float(match.group(1)),
                "unit": match.group(2),
                "optional": False,
                "quote": match.group(0),
            })
    effective = EFFECTIVE.search(text)
    return {
        "utility": page.get("utility"),
        "effective_date": effective.group(1) if effective else None,
        "effective_quote": effective.group(0) if effective else None,
        "demand_charges": charges,
        "incentives": [],
    }
