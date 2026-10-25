import argparse
import geopandas as gpd
import pandas as pd
from config.assumptions import (
    ACRE_TO_M2, CANDIDATE_CLASSES, DISTRIBUTION_TYPES, LOAD_KEYWORDS,
    MASS_STATE_PLANE, MIN_FOOTPRINT_M2, PEAK_W_PER_M2, SQFT_TO_M2,
)
from config.towns import DATA_PROCESSED, load_towns, raw_dir

PARCEL_FIELDS = [
    "use_code", "use_desc", "use_class", "site_addr", "owner1",
    "zoning", "year_built", "total_val", "bld_area", "lot_acres",
]


def load_profile(use_desc, use_class):
    text = str(use_desc).lower()
    for keywords, profile in LOAD_KEYWORDS:
        if any(word in text for word in keywords):
            return profile
    return use_class


def build_sites(buildings):
    buildings = buildings[buildings["use_class"].isin(CANDIDATE_CLASSES)]
    largest_name = (
        buildings.sort_values("footprint_m2", ascending=False)
        .dropna(subset=["name"]).drop_duplicates("loc_id").set_index("loc_id")["name"]
    )
    agg = {field: "first" for field in PARCEL_FIELDS}
    agg.update(footprint_m2="sum", osm_id="count")
    sites = buildings.dissolve(by="loc_id", aggfunc=agg).rename(columns={"osm_id": "n_buildings"})
    sites["osm_name"] = largest_name.reindex(sites.index)
    return sites[sites["footprint_m2"] >= MIN_FOOTPRINT_M2].reset_index()


def add_size(sites):
    assessor_m2 = sites["bld_area"] * SQFT_TO_M2
    use_assessor = assessor_m2 >= sites["footprint_m2"]
    sites["floor_area_m2"] = assessor_m2.where(use_assessor, sites["footprint_m2"])
    sites["floor_area_source"] = use_assessor.map({True: "assessor", False: "footprint"})
    sites["lot_m2"] = sites["lot_acres"] * ACRE_TO_M2
    sites["open_lot_m2"] = (sites["lot_m2"] - sites["footprint_m2"]).clip(lower=0)
    sites["load_profile"] = [load_profile(d, c) for d, c in zip(sites["use_desc"], sites["use_class"])]
    sites["peak_kw_est"] = sites["floor_area_m2"] * sites["load_profile"].map(PEAK_W_PER_M2) / 1000
    return sites


def add_grid(sites, folder):
    subs = gpd.read_file(folder / "substations.gpkg").to_crs(MASS_STATE_PLANE)
    lines = gpd.read_file(folder / "power_lines.gpkg").to_crs(MASS_STATE_PLANE)
    dist_subs = subs[subs["substation"].isin(DISTRIBUTION_TYPES)]

    points = sites[["loc_id", "geometry"]].copy()
    points["geometry"] = sites.geometry.representative_point()

    nearest = gpd.sjoin_nearest(points, dist_subs[["name", "voltage", "geometry"]], distance_col="dist_substation_m")
    nearest = nearest.drop_duplicates("loc_id").set_index("loc_id")
    sites["substation_name"] = sites["loc_id"].map(nearest["name"])
    sites["substation_voltage"] = sites["loc_id"].map(nearest["voltage"])
    sites["dist_substation_m"] = sites["loc_id"].map(nearest["dist_substation_m"])

    near_line = gpd.sjoin_nearest(points, lines[["geometry"]], distance_col="dist_line_m").drop_duplicates("loc_id")
    sites["dist_line_m"] = sites["loc_id"].map(near_line.set_index("loc_id")["dist_line_m"])

    lonlat = points.to_crs("EPSG:4326").geometry
    sites["lon"] = lonlat.x.round(6).values
    sites["lat"] = lonlat.y.round(6).values
    return sites


def run(town):
    folder = raw_dir(town["id"])
    buildings = gpd.read_file(folder / "buildings_parcels.gpkg").to_crs(MASS_STATE_PLANE)
    sites = add_grid(add_size(build_sites(buildings)), folder)
    sites.insert(0, "town", town["id"])
    sites.to_file(folder / "sites.gpkg", driver="GPKG")

    out = DATA_PROCESSED / town["id"]
    out.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(sites.drop(columns="geometry"))
    measures = table.select_dtypes("float").columns.difference(["lon", "lat"])
    table[measures] = table[measures].round(2)
    table.to_csv(out / "sites.csv", index=False)
    return sites


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--towns", nargs="*")
    args = parser.parse_args()

    for town in load_towns(args.towns):
        sites = run(town)
        print(
            f"{town['name']:12s} sites {len(sites):5d}  "
            f"median peak {sites['peak_kw_est'].median():6.0f} kW  "
            f"median to substation {sites['dist_substation_m'].median():5.0f} m  "
            f"assessor area {(sites['floor_area_source'] == 'assessor').mean():.0%}  "
            f"profiles {sites['load_profile'].value_counts().head(5).to_dict()}"
        )
