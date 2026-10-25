import argparse
import geopandas as gpd
from config.towns import DATA_RAW, load_towns, raw_dir

BUSINESS_BUILDINGS = {
    "commercial", "retail", "industrial", "office", "warehouse",
    "supermarket", "manufacture", "hospital", "school", "university",
    "hotel", "civic", "public", "government", "college",
}

BUSINESS_TAGS = ["shop", "amenity", "office", "craft"]

KEEP = [
    "osm_id", "building", "name", "addr:housenumber", "addr:street",
    "building:levels", "shop", "amenity", "office", "craft", "geometry",
]


def fetch(town, area_buildings):
    boundary = gpd.read_file(raw_dir(town["id"]) / "boundary.gpkg").union_all()
    gdf = area_buildings[area_buildings.intersects(boundary)][KEEP].copy()
    gdf["osm_business"] = gdf["building"].isin(BUSINESS_BUILDINGS) | gdf[BUSINESS_TAGS].notna().any(axis=1)
    gdf.to_file(raw_dir(town["id"]) / "buildings.gpkg", driver="GPKG")
    return gdf


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--towns", nargs="*")
    args = parser.parse_args()

    area_buildings = gpd.read_file(DATA_RAW / "osm" / "area_buildings.gpkg")

    for town in load_towns(args.towns):
        gdf = fetch(town, area_buildings)
        top = gdf["building"].value_counts().head(5).to_dict()
        print(f"{town['name']:12s} buildings {len(gdf):6d}  business {int(gdf['osm_business'].sum()):5d}  top tags {top}")
