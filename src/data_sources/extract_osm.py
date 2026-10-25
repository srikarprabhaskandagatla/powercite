import geopandas as gpd
import osmium
import pandas as pd
from shapely import wkb
from config.towns import DATA_RAW, load_towns, raw_dir

OSM_DIR = DATA_RAW / "osm"
PBF = OSM_DIR / "massachusetts-latest.osm.pbf"
POWER_TAGS = ["name", "operator", "substation", "voltage", "power"]
BUILDING_TAGS = [
    "building", "name", "addr:housenumber", "addr:street",
    "building:levels", "shop", "amenity", "office", "craft",
]
LINE_VALUES = ("line", "minor_line")
BBOX_PAD_DEG = 0.05


def make_row(obj, osm_id, geom_hex, tags):
    row = {"osm_id": osm_id}
    for tag in tags:
        row[tag] = obj.tags.get(tag)
    row["geometry"] = wkb.loads(geom_hex, hex=True)
    return row


def towns_bbox():
    boundaries = pd.concat([gpd.read_file(raw_dir(t["id"]) / "boundary.gpkg") for t in load_towns()])
    minx, miny, maxx, maxy = boundaries.total_bounds
    return minx - BBOX_PAD_DEG, miny - BBOX_PAD_DEG, maxx + BBOX_PAD_DEG, maxy + BBOX_PAD_DEG


def first_node_inside(area, bbox):
    for ring in area.outer_rings():
        for node in ring:
            return bbox[0] <= node.lon <= bbox[2] and bbox[1] <= node.lat <= bbox[3]
    return False


def extract(path, bbox):
    factory = osmium.geom.WKBFactory()
    subs, lines, buildings = [], [], []
    processor = (
        osmium.FileProcessor(str(path))
        .with_locations()
        .with_areas(osmium.filter.KeyFilter("power", "building"))
        .with_filter(osmium.filter.KeyFilter("power", "building"))
    )
    for obj in processor:
        power = obj.tags.get("power")
        try:
            if obj.is_node() and power == "substation":
                subs.append(make_row(obj, f"n{obj.id}", factory.create_point(obj), POWER_TAGS))
            elif obj.is_way() and power in LINE_VALUES:
                lines.append(make_row(obj, f"w{obj.id}", factory.create_linestring(obj), POWER_TAGS))
            elif obj.is_area():
                osm_id = f"{'w' if obj.from_way() else 'r'}{obj.orig_id()}"
                if power == "substation":
                    subs.append(make_row(obj, osm_id, factory.create_multipolygon(obj), POWER_TAGS))
                elif "building" in obj.tags and first_node_inside(obj, bbox):
                    buildings.append(make_row(obj, osm_id, factory.create_multipolygon(obj), BUILDING_TAGS))
        except RuntimeError:
            continue
    to_gdf = lambda rows: gpd.GeoDataFrame(rows, crs="EPSG:4326")
    return to_gdf(subs), to_gdf(lines), to_gdf(buildings)


if __name__ == "__main__":
    subs, lines, buildings = extract(PBF, towns_bbox())
    subs.to_file(OSM_DIR / "ma_substations.gpkg", driver="GPKG")
    lines.to_file(OSM_DIR / "ma_power_lines.gpkg", driver="GPKG")
    buildings.to_file(OSM_DIR / "area_buildings.gpkg", driver="GPKG")
    print(f"Massachusetts substations {len(subs)}  power lines {len(lines)}  buildings near our towns {len(buildings)}")
