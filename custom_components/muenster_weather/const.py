"""Constants for Münster Open Data Weather."""

DOMAIN = "muenster_weather"
DEFAULT_SCAN_INTERVAL = 300
DATASET_ID = "messdaten-der-wetterstationen-aus-dem-projekt-stadt-temperatur"
CKAN_API = "https://opendata.stadt-muenster.de/api/3/action/package_show"
STATIONS_URL = (
    "https://geo.stadt-muenster.de/mapserv/wetterstationen_serv"
    "?SERVICE=WFS&VERSION=1.1.0&REQUEST=GetFeature"
    "&TYPENAME=wetterstationen&OUTPUTFORMAT=CSV_STAMMDATEN"
)
CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_MODE = "mode"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS_KM = "radius_km"
CONF_MAX_STATIONS = "max_stations"
MODE_STATION = "station"
MODE_AUTOMATIC = "automatic"
AUTOMATIC_ID = "automatic"
DEFAULT_RADIUS_KM = 10.0
DEFAULT_MAX_STATIONS = 3
