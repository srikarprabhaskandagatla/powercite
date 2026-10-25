import argparse
import zipfile
import geopandas as gpd
import pandas as pd
import pyogrio
import requests
from config.towns import load_towns, raw_dir

MASSGIS_URL = "https://s3.us-east-1.amazonaws.com/download.massgis.digital.mass.gov/shapefiles/l3parcels/{}.zip"
KEEP_POLY_TYPES = ["FEE", "TAX"]
SQFT_PER_ACRE = 43560
USE_CLASS = {
    "0": "mixed", "1": "residential", "2": "open_space", "3": "commercial", "4": "industrial",
    "5": "personal_property", "6": "forest", "7": "agricultural", "8": "recreational", "9": "exempt",
}
FIRST_FIELDS = ["USE_CODE", "SITE_ADDR", "OWNER1", "ZONING", "YEAR_BUILT", "STORIES"]
SUM_FIELDS = ["TOTAL_VAL", "BLDG_VAL", "BLD_AREA", "RES_AREA", "UNITS"]


def download(town):
    src = raw_dir(town["id"]) / "parcels_src"
    src.mkdir(exist_ok=True)
    zip_path = src / "parcels.zip"
    if not zip_path.exists():
        response = requests.get(MASSGIS_URL.format(town["massgis_zip"]), timeout=120)
        response.raise_for_status()
        zip_path.write_bytes(response.content)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(src)
    return src


def find(src, pattern):
    matches = sorted(src.rglob(pattern))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one {pattern} in {src}, found {len(matches)}")
    return matches[0]


def tidy_assess(src):
    assess = pyogrio.read_dataframe(find(src, "*Assess*.dbf"), read_geometry=False)
    assess["lot_acres"] = assess["LOT_SIZE"].where(assess["LOT_UNITS"] != "S", assess["LOT_SIZE"] / SQFT_PER_ACRE)

    first = assess.sort_values("TOTAL_VAL", ascending=False).drop_duplicates("LOC_ID")[["LOC_ID"] + FIRST_FIELDS]
    sums = assess.groupby("LOC_ID")[SUM_FIELDS].sum().reset_index()
    extra = assess.groupby("LOC_ID").agg(lot_acres=("lot_acres", "max"), n_records=("LOC_ID", "size")).reset_index()
    parcels = first.merge(sums, on="LOC_ID").merge(extra, on="LOC_ID")

    lut = pyogrio.read_dataframe(find(src, "*UC_LUT*.dbf"), read_geometry=False)
    lut = lut.sort_values("TOWN_ID").drop_duplicates("USE_CODE", keep="last")[["USE_CODE", "USE_DESC"]]
    parcels = parcels.merge(lut, on="USE_CODE", how="left")
    parcels["use_class"] = parcels["USE_CODE"].str[0].map(USE_CLASS)
    return parcels


def build(town):
    src = download(town)
    shapes = gpd.read_file(find(src, "*TaxPar*.shp"), columns=["LOC_ID", "POLY_TYPE"])
    shapes = shapes[shapes["POLY_TYPE"].isin(KEEP_POLY_TYPES)]
    parcels = shapes.merge(tidy_assess(src), on="LOC_ID", how="left")
    parcels.columns = [c.lower() for c in parcels.columns]
    parcels.to_file(raw_dir(town["id"]) / "parcels.gpkg", driver="GPKG")
    return parcels


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--towns", nargs="*")
    args = parser.parse_args()

    for town in load_towns(args.towns):
        parcels = build(town)
        classes = parcels["use_class"].value_counts(dropna=False).to_dict()
        print(f"{town['name']:12s} parcels {len(parcels):6d}  crs {parcels.crs.to_epsg()}  classes {classes}")
