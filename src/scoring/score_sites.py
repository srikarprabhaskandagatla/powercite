import json
import numpy as np
import pandas as pd
from config.assumptions import (
    INCENTIVE_PAGE, INCENTIVE_QUOTE, INCENTIVE_USD_PER_KW_YEAR, LARGE_RATE_FROM_KW, LOAD_SPIKINESS,
    MAX_BATTERY_KW, NO_DEMAND_CHARGE_BELOW_KW, PEAK_SHAVE_FRACTION, SCORE_WEIGHTS, SPACE_NEEDED_M2,
)
from config.towns import DATA_CACHE, DATA_PROCESSED, load_towns


def load_sites():
    frames = []
    for town in load_towns():
        sites = pd.read_csv(DATA_PROCESSED / town["id"] / "sites.csv")
        links = pd.read_csv(DATA_PROCESSED / town["id"] / "links.csv").dropna(subset=["building_id"])
        names = links.groupby("building_id")["name"].apply(lambda s: ", ".join(sorted(set(s))[:3]))
        sites["linked_names"] = sites["loc_id"].map(names)
        frames.append(sites)
    return pd.concat(frames, ignore_index=True)


def incentive_is_sourced():
    page = json.loads((DATA_CACHE / "pages" / f"{INCENTIVE_PAGE}.json").read_text())
    return INCENTIVE_QUOTE in page["text"]


def add_money(sites, tariffs, incentive_rate):
    sites["rate_class"] = np.select(
        [sites["peak_kw_est"] < NO_DEMAND_CHARGE_BELOW_KW, sites["peak_kw_est"] >= LARGE_RATE_FROM_KW],
        ["G-1", "G-3"], "G-2",
    )
    rate = [tariffs[t].get(c, {}).get("usd_per_kw", 0.0) for t, c in zip(sites["town"], sites["rate_class"])]
    sites["demand_usd_per_kw"] = rate
    sites["battery_kw"] = (sites["peak_kw_est"] * PEAK_SHAVE_FRACTION).clip(upper=MAX_BATTERY_KW).round(1)
    sites["bill_savings_month"] = (sites["battery_kw"] * sites["demand_usd_per_kw"]).round(0)
    sites["incentive_month"] = (sites["battery_kw"] * incentive_rate / 12).round(0)
    sites["value_month"] = sites["bill_savings_month"] + sites["incentive_month"]
    return sites


def percentile(series):
    return series.rank(pct=True).fillna(0)


def add_features(sites):
    sites["f_savings"] = percentile(sites["bill_savings_month"]).where(sites["bill_savings_month"] > 0, 0)
    sites["f_spikiness"] = sites["load_profile"].map(LOAD_SPIKINESS).fillna(0.5)
    sites["f_space"] = (sites["open_lot_m2"] / SPACE_NEEDED_M2).clip(0, 1)
    sites["f_grid"] = 1 - percentile(sites["dist_substation_m"])
    sites["f_confidence"] = (
        (sites["floor_area_source"] == "assessor").astype(float) * 0.5
        + sites["linked_names"].notna().astype(float) * 0.25
        + sites["substation_voltage"].notna().astype(float) * 0.25
    )
    return sites


def add_score(sites):
    for name, weight in SCORE_WEIGHTS.items():
        sites[f"c_{name}"] = (weight * sites[f"f_{name}"]).round(4)
    sites["score"] = (100 * sites[[f"c_{n}" for n in SCORE_WEIGHTS]].sum(axis=1)).round(1)
    sites["rank_in_town"] = sites.groupby("town")["score"].rank(ascending=False, method="first").astype(int)
    return sites


if __name__ == "__main__":
    tariffs = json.loads((DATA_PROCESSED / "tariffs.json").read_text())
    sourced = incentive_is_sourced()
    incentive_rate = INCENTIVE_USD_PER_KW_YEAR if sourced else 0
    print(f"incentive {INCENTIVE_QUOTE} found in cached page {INCENTIVE_PAGE}: {sourced}")

    sites = add_score(add_features(add_money(load_sites(), tariffs, incentive_rate)))
    sites.sort_values(["town", "rank_in_town"]).to_csv(DATA_PROCESSED / "scored_sites.csv", index=False)

    print(f"sites {len(sites)}  rate classes {sites['rate_class'].value_counts().to_dict()}")
    print(f"value per month: median ${sites['value_month'].median():.0f}  top 10% ${sites['value_month'].quantile(0.9):.0f}  max ${sites['value_month'].max():.0f}")
    print(f"score vs peak kW rank correlation {sites['score'].corr(sites['peak_kw_est'], method='spearman'):.2f}")
    cols = ["rank_in_town", "score", "site_addr", "load_profile", "peak_kw_est", "rate_class", "value_month", "dist_substation_m"]
    for town in load_towns():
        top = sites[sites["town"] == town["id"]].nsmallest(5, "rank_in_town")[cols]
        print(f"\n{town['name']}")
        print(top.to_string(index=False, float_format=lambda v: f"{v:.0f}"))
