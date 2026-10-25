import argparse
import geopandas as gpd
from config.towns import load_towns, raw_dir

MASS_STATE_PLANE = "EPSG:26986"
PARCEL_COLS = [
    "loc_id", "use_code", "use_desc", "use_class", "site_addr", "owner1", "zoning",
    "year_built", "stories", "total_val", "bld_area", "lot_acres", "geometry",
]


def clean(gdf):
    gdf = gdf.to_crs(MASS_STATE_PLANE)
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf


def join(town):
    folder = raw_dir(town["id"])
    buildings = gpd.read_file(folder / "buildings.gpkg")
    parcels = clean(gpd.read_file(folder / "parcels.gpkg"))[PARCEL_COLS]

    degrees_area = buildings.geometry.area.median()
    buildings = clean(buildings)
    buildings["footprint_m2"] = buildings.geometry.area

    points = buildings.copy()
    points["geometry"] = buildings.geometry.representative_point()
    matched = gpd.sjoin(points, parcels, how="left", predicate="within")
    matched = matched.drop_duplicates("osm_id").drop(columns=["index_right", "geometry"])

    joined = buildings[["osm_id", "geometry"]].merge(matched, on="osm_id")
    joined.to_file(folder / "buildings_parcels.gpkg", driver="GPKG")
    return joined, degrees_area


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--towns", nargs="*")
    args = parser.parse_args()

    for town in load_towns(args.towns):
        joined, degrees_area = join(town)
        has_parcel = joined["loc_id"].notna()
        per_parcel = joined[has_parcel].groupby("loc_id").size()
        classes = joined["use_class"].value_counts(dropna=False).to_dict()
        print(
            f"{town['name']:12s} buildings {len(joined):6d}  with parcel {has_parcel.mean():.1%}  "
            f"median footprint {joined['footprint_m2'].median():.0f} m2 (in degrees it was {degrees_area:.2e})  "
            f"max buildings on one parcel {per_parcel.max()}  classes {classes}"
        )
