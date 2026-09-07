"""Constants for Münster Open Data Weather."""

from typing import Final

DOMAIN: Final = "muenster_weather"
API_URL: Final = "https://geo.stadt-muenster.de/mapserv/wetterstationen_serv"
DATASET_URL: Final = "https://opendata.stadt-muenster.de/dataset/messdaten-der-wetterstationen-aus-dem-projekt-stadt-temperatur"
COMMON_PARAMS: Final = {"SERVICE": "WFS", "VERSION": "1.1.0", "REQUEST": "GetFeature"}
STATION_PARAMS: Final = {
    **COMMON_PARAMS,
    "TYPENAME": "wetterstationen",
    "OUTPUTFORMAT": "geojson",
}
LATEST_PARAMS: Final = {
    **COMMON_PARAMS,
    "TYPENAME": "wetterstationen_aktuell",
    "OUTPUTFORMAT": "JSON_AKTUELL",
}

CONF_MODE: Final = "mode"
CONF_STATION_ID: Final = "station_id"
CONF_STATION_NAME: Final = "station_name"
CONF_LATITUDE: Final = "latitude"
CONF_LONGITUDE: Final = "longitude"
CONF_RADIUS_KM: Final = "radius_km"
CONF_MAX_STATIONS: Final = "max_stations"
MODE_STATION: Final = "station"
MODE_ESTIMATE: Final = "estimate"
DEFAULT_RADIUS_KM: Final = 5.0
DEFAULT_MAX_STATIONS: Final = 5
UPDATE_INTERVAL_MINUTES: Final = 15
STALE_AFTER_MINUTES: Final = 45
MINIMUM_DISTANCE_KM: Final = 0.05
IDW_POWER: Final = 2.0
