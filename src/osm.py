import time
import geopandas as gpd
import osmnx as ox
import requests
from osmnx._errors import InsufficientResponseError, ResponseStatusCodeError

from towns import DATA_RAW

OVERPASS_URLS = [
    "https://overpass-api.de/api",
    "https://overpass.private.coffee/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
]

NETWORK_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError,
    ResponseStatusCodeError,
)


def setup():
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(DATA_RAW / "osm_cache")
    ox.settings.log_console = False
    ox.settings.overpass_rate_limit = False
    ox.settings.requests_timeout = 300


def features(polygon, tags):
    last_error = None
    for url in OVERPASS_URLS:
        ox.settings.overpass_url = url
        try:
            return ox.features_from_polygon(polygon, tags=tags)
        except InsufficientResponseError:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        except NETWORK_ERRORS as error:
            print(f"  {url} failed, trying next")
            last_error = error
            time.sleep(5)
    raise last_error
