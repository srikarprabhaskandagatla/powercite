import argparse
import geopandas as gpd
import osmnx as ox
from config.towns import DATA_RAW, load_towns, raw_dir

MASS_STATE_PLANE = "EPSG:26986"
BUFFER_M = 5000
SUB_KEEP = ["osm_id", "name", "operator", "substation", "voltage", "geometry"]
LINE_KEEP = ["osm_id", "power", "voltage", "operator", "geometry"]


def town_boundary(town):
    path = raw_dir(town["id"]) / "boundary.gpkg"
    if path.exists():
        return gpd.read_file(path)
    boundary = ox.geocode_to_gdf(town["osm"])[["geometry"]]
    boundary.to_file(path, driver="GPKG")
    return boundary


def fetch(town, subs_ma, lines_ma):
    out_path = raw_dir(town["id"])
    search = town_boundary(town).to_crs(MASS_STATE_PLANE).buffer(BUFFER_M).union_all()

    subs = subs_ma[subs_ma.intersects(search)][SUB_KEEP].copy()
    subs["geometry"] = subs.geometry.centroid
    subs = subs.to_crs("EPSG:4326")
    subs.to_file(out_path / "substations.gpkg", driver="GPKG")

    lines = lines_ma[lines_ma.intersects(search)][LINE_KEEP].to_crs("EPSG:4326")
    lines.to_file(out_path / "power_lines.gpkg", driver="GPKG")
    return subs, lines


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--towns", nargs="*")
    args = parser.parse_args()

    subs_ma = gpd.read_file(DATA_RAW / "osm" / "ma_substations.gpkg").to_crs(MASS_STATE_PLANE)
    lines_ma = gpd.read_file(DATA_RAW / "osm" / "ma_power_lines.gpkg").to_crs(MASS_STATE_PLANE)

    for town in load_towns(args.towns):
        subs, lines = fetch(town, subs_ma, lines_ma)
        types = subs["substation"].value_counts(dropna=False).to_dict()
        named = int(subs["name"].notna().sum())
        volts = int(subs["voltage"].notna().sum())
        print(f"{town['name']:12s} substations {len(subs):3d}  named {named:3d}  with voltage {volts:3d}  types {types}  lines {len(lines):4d}")
