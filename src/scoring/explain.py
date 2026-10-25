import hashlib
import json
import os
import re
import pandas as pd
from dotenv import load_dotenv
from config.assumptions import SCORE_WEIGHTS
from config.towns import DATA_CACHE, DATA_PROCESSED, ROOT, load_towns

TOP_PER_TOWN = 300
LLM_TOP = 20
LLM_MODEL = "claude-sonnet-5-5"
LINE_CACHE = DATA_CACHE / "reasons"
FACTORS = list(SCORE_WEIGHTS)

load_dotenv(ROOT / ".env")


def upper_first(text):
    return text[:1].upper() + text[1:]


def display_name(row):
    for value in (row["linked_names"], row["osm_name"], row["owner1"]):
        if pd.notna(value) and str(value).strip():
            return str(value)
    return row["site_addr"]


def strength(row, factor):
    return {
        "savings": f"worth about ${row['value_month']:,.0f} a month on {row['rate_class']} at ${row['demand_usd_per_kw']:.2f}/kW",
        "spikiness": f"{row['load_profile'].replace('_', ' ')} load tends to spike",
        "space": f"{row['open_lot_m2']:,.0f} m2 of open lot for the battery",
        "grid": f"{row['dist_substation_m']:,.0f} m from {row['substation_name'] if pd.notna(row['substation_name']) else 'a substation'}",
        "confidence": "floor area and grid data are well sourced",
    }[factor]


def weakness(row, factor):
    return {
        "savings": f"small savings, about ${row['value_month']:,.0f} a month",
        "spikiness": f"{row['load_profile'].replace('_', ' ')} load is fairly flat",
        "space": f"only {row['open_lot_m2']:,.0f} m2 of open lot",
        "grid": f"{row['dist_substation_m']:,.0f} m from the nearest substation",
        "confidence": "floor area or grid data is thin",
    }[factor]


def explain(sites):
    contrib = sites[[f"c_{f}" for f in FACTORS]]
    edge = contrib - contrib.median()
    edge.columns = FACTORS
    order = edge.apply(lambda r: list(r.sort_values(ascending=False).index), axis=1)
    sites["reason"] = [
        upper_first("; ".join(strength(row, f) for f in factors[:2]))
        for (_, row), factors in zip(sites.iterrows(), order)
    ]
    sites["weak_point"] = [
        upper_first(weakness(row, factors[-1])) if edges[factors[-1]] < 0 else "No clear weak point"
        for (_, row), factors, (_, edges) in zip(sites.iterrows(), order, edge.iterrows())
    ]
    sites["top_factor"] = [factors[0] for factors in order]
    sites["confidence_label"] = pd.cut(sites["f_confidence"], [-0.01, 0.4, 0.7, 1.0], labels=["low", "medium", "high"])
    sites["display_name"] = [display_name(row) for _, row in sites.iterrows()]
    return sites


def facts_for(row):
    return {
        "name": row["display_name"], "address": row["site_addr"], "town": row["town"],
        "use": row["use_desc"], "peak_kw_estimate": round(row["peak_kw_est"]),
        "rate_class": row["rate_class"], "demand_usd_per_kw": row["demand_usd_per_kw"],
        "battery_kw": row["battery_kw"], "value_per_month_usd": round(row["value_month"]),
        "distance_to_substation_m": round(row["dist_substation_m"]),
        "open_lot_m2": round(row["open_lot_m2"]), "reason": row["reason"], "weak_point": row["weak_point"],
    }


def grounded(line, facts):
    source = json.dumps(facts).replace(",", "")
    return all(n in source for n in re.findall(r"\d+(?:\.\d+)?", line.replace(",", "")))


def llm_line(row):
    facts = facts_for(row)
    payload = json.dumps(facts, sort_keys=True)
    path = LINE_CACHE / f"{hashlib.sha1(payload.encode()).hexdigest()[:16]}.json"
    if path.exists():
        return json.loads(path.read_text())["line"], "cached"
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None, "no key"
    import anthropic
    response = anthropic.Anthropic().messages.create(
        model=LLM_MODEL,
        max_tokens=300,
        output_config={"effort": "low"},
        system=(
            "Write one plain sentence, under 30 words, telling a battery sales team why this site is worth a call. "
            "Use only the facts given. Do not invent numbers. Mention the main risk if there is one."
        ),
        messages=[{"role": "user", "content": payload}],
    )
    line = "".join(b.text for b in response.content if b.type == "text").strip()
    if response.stop_reason == "refusal" or not grounded(line, facts):
        return None, "rejected"
    LINE_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"facts": facts, "line": line}, indent=2))
    return line, "live"


if __name__ == "__main__":
    sites = explain(pd.read_csv(DATA_PROCESSED / "scored_sites.csv"))
    print(f"top factor share {sites['top_factor'].value_counts(normalize=True).round(2).to_dict()}")
    print(f"confidence {sites['confidence_label'].value_counts().to_dict()}")
    print(f"one-line writer: {LLM_MODEL if os.getenv('ANTHROPIC_API_KEY') else 'template only (no ANTHROPIC_API_KEY)'}")

    for town in load_towns():
        top = sites[sites["town"] == town["id"]].nsmallest(TOP_PER_TOWN, "rank_in_town").copy()
        statuses = {}
        lines = []
        for _, row in top.iterrows():
            line, status = llm_line(row) if row["rank_in_town"] <= LLM_TOP else (None, "not top")
            statuses[status] = statuses.get(status, 0) + 1
            risk = "No clear weak point." if row["weak_point"] == "No clear weak point" else f"Watch out, {row['weak_point'][0].lower() + row['weak_point'][1:]}."
            lines.append(line or f"{row['reason']}. {risk}")
        top["pitch"] = lines
        top.to_csv(DATA_PROCESSED / town["id"] / "ranked.csv", index=False)
        print(f"\n{town['name']}: {statuses}")
        for _, row in top.head(3).iterrows():
            print(f"  #{row['rank_in_town']} {row['display_name'][:40]} ({row['confidence_label']})")
            print(f"     {row['pitch']}")
