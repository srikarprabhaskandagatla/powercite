import argparse
import osmnx as ox
import pandas as pd
from towns import DATA_RAW, load_towns, raw_dir

BUSINESS_BUILDINGS = {
    "commercial", "retail", "industrial", "office", "warehouse",
    "supermarket", "manufacture", "hospital", "school", "university",
    "hotel", "civic", "public", "government", "college",
}

BUSINESS_TAGS = ["shop", "amenity", "office", "craft"]

KEEP = [
    "building", "name", "addr:housenumber", "addr:street",
    "building:levels", "shop", "amenity", "office", "craft", "geometry",
]


def fetch(town):
    gdf = ox.features_from_place(town["osm"], tags={"building": True})
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    gdf = gdf.reset_index()
    gdf["osm_id"] = gdf["element"].str[0] + gdf["id"].astype(str)
    for col in KEEP:
        if col not in gdf.columns:
            gdf[col] = pd.NA
    gdf = gdf[["osm_id"] + KEEP].copy()
    gdf["osm_business"] = gdf["building"].isin(BUSINESS_BUILDINGS) | gdf[BUSINESS_TAGS].notna().any(axis=1)
    gdf = gdf.astype({c: "string" for c in KEEP if c != "geometry"})
    gdf.to_file(raw_dir(town["id"]) / "buildings.gpkg", driver="GPKG")
    return gdf


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--towns", nargs="*")
    args = parser.parse_args()

    ox.settings.use_cache = True
    ox.settings.cache_folder = str(DATA_RAW / "osm_cache")
    ox.settings.log_console = False

    for town in load_towns(args.towns):
        gdf = fetch(town)
        top = gdf["building"].value_counts().head(5).to_dict()
        print(f"{town['name']:12s} buildings {len(gdf):6d}  business {int(gdf['osm_business'].sum()):5d}  top tags {top}")
