import geopandas as gpd
import osmium
from shapely import wkb
from config.towns import DATA_RAW

PBF = DATA_RAW / "osm" / "massachusetts-latest.osm.pbf"
TAGS = ["name", "operator", "substation", "voltage", "power"]
LINE_VALUES = ("line", "minor_line")


def make_row(obj, osm_id, geom_hex):
    row = {"osm_id": osm_id}
    for tag in TAGS:
        row[tag] = obj.tags.get(tag)
    row["geometry"] = wkb.loads(geom_hex, hex=True)
    return row


def extract(path):
    factory = osmium.geom.WKBFactory()
    subs, lines = [], []
    processor = (
        osmium.FileProcessor(str(path))
        .with_locations()
        .with_areas(osmium.filter.KeyFilter("power"))
        .with_filter(osmium.filter.KeyFilter("power"))
    )
    for obj in processor:
        power = obj.tags.get("power")
        try:
            if obj.is_node() and power == "substation":
                subs.append(make_row(obj, f"n{obj.id}", factory.create_point(obj)))
            elif obj.is_way() and power in LINE_VALUES:
                lines.append(make_row(obj, f"w{obj.id}", factory.create_linestring(obj)))
            elif obj.is_area() and power == "substation":
                prefix = "w" if obj.from_way() else "r"
                subs.append(make_row(obj, f"{prefix}{obj.orig_id()}", factory.create_multipolygon(obj)))
        except RuntimeError:
            continue
    return gpd.GeoDataFrame(subs, crs="EPSG:4326"), gpd.GeoDataFrame(lines, crs="EPSG:4326")


if __name__ == "__main__":
    subs, lines = extract(PBF)
    subs.to_file(DATA_RAW / "osm" / "ma_substations.gpkg", driver="GPKG")
    lines.to_file(DATA_RAW / "osm" / "ma_power_lines.gpkg", driver="GPKG")
    print(f"Massachusetts substations {len(subs)}  power lines {len(lines)}")
