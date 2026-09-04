"""Async client for Münster's Open Data weather dataset."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import io
import math
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import CKAN_API, DATASET_ID


class MuensterWeatherApiError(Exception):
    """Base API error."""


class MuensterWeatherConnectionError(MuensterWeatherApiError):
    """The portal could not be reached."""


class MuensterWeatherDataError(MuensterWeatherApiError):
    """The portal returned unusable data."""


@dataclass(frozen=True, slots=True)
class Station:
    """A weather station advertised by the dataset."""

    station_id: str
    name: str
    latitude: float | None = None
    longitude: float | None = None


_ALIASES = {
    "station_id": ("station_id", "stations_id", "station", "stationsname", "id", "sensor_id"),
    "station_name": ("station_name", "stationsname", "name", "standort", "location"),
    "timestamp": ("timestamp", "zeitstempel", "datetime", "datum", "time", "created_at"),
    "temperature": ("temperature", "temperatur", "temp", "lufttemperatur"),
    "humidity": ("humidity", "luftfeuchtigkeit", "relative_feuchte", "feuchtigkeit"),
    "pressure": ("pressure", "luftdruck", "barometer"),
    "wind_speed": ("wind_speed", "windgeschwindigkeit", "windspeed"),
    "wind_bearing": ("wind_bearing", "windrichtung", "wind_direction"),
    "precipitation": ("precipitation", "niederschlag", "rain", "regen"),
    "illuminance": ("illuminance", "beleuchtungsstaerke", "helligkeit", "lux"),
    "latitude": ("latitude", "lat", "breitengrad", "geo_lat", "y"),
    "longitude": ("longitude", "lon", "lng", "laengengrad", "langengrad", "geo_lon", "x"),
}


def _normalise(value: str) -> str:
    value = value.casefold().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return "".join(char for char in value if char.isalnum() or char == "_")


def _value(row: dict[str, str], field: str) -> str | None:
    normalised = {_normalise(key): value for key, value in row.items()}
    for alias in _ALIASES[field]:
        if (value := normalised.get(_normalise(alias))) not in (None, ""):
            return value.strip()
    return None


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


class MuensterWeatherClient:
    """Retrieve and normalise the published tabular observations."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._data_url: str | None = None

    async def _request(self, url: str, *, params: dict[str, str] | None = None) -> Any:
        try:
            async with self._session.get(url, params=params, timeout=30) as response:
                response.raise_for_status()
                if "json" in response.content_type:
                    return await response.json(content_type=None)
                return await response.text()
        except (ClientError, TimeoutError) as err:
            raise MuensterWeatherConnectionError from err

    async def _resource_urls(self) -> list[str]:
        """Return machine-readable resources, preferring the newest one.

        The portal occasionally leaves a broken generated resource (for example a
        failed zipball download) as the newest dataset resource.  Keep the older
        resources as fallbacks instead of making that one portal entry take the
        integration down.
        """
        if self._data_url:
            return [self._data_url]
        payload = await self._request(CKAN_API, params={"id": DATASET_ID})
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        resources = result.get("resources", [])
        candidates = [
            item for item in resources
            if str(item.get("format", "")).casefold() in {"csv", "json"} and item.get("url")
        ]
        if not candidates:
            raise MuensterWeatherDataError("The dataset contains no CSV or JSON resource")
        # The portal orders resources chronologically; the latest machine-readable file wins.
        return [item["url"] for item in reversed(candidates)]

    async def _resource_url(self) -> str:
        """Return the preferred resource URL (kept for API compatibility)."""
        return (await self._resource_urls())[0]

    async def _rows(self) -> list[dict[str, str]]:
        errors: list[MuensterWeatherApiError] = []
        for url in await self._resource_urls():
            try:
                rows = await self._rows_from_url(url)
                if not any(_value(row, "station_id") for row in rows):
                    raise MuensterWeatherDataError(
                        "The resource contains no weather-station records"
                    )
            except MuensterWeatherApiError as err:
                errors.append(err)
                continue
            self._data_url = url
            return rows
        if errors and all(isinstance(err, MuensterWeatherConnectionError) for err in errors):
            raise MuensterWeatherConnectionError("No dataset resource could be reached")
        raise MuensterWeatherDataError("No usable CSV or JSON resource found")

    async def _rows_from_url(self, url: str) -> list[dict[str, str]]:
        """Download and parse one dataset resource."""
        payload = await self._request(url)
        if isinstance(payload, dict):
            payload = payload.get("result", {}).get("records", payload.get("records", []))
        if isinstance(payload, list):
            if not all(isinstance(row, dict) for row in payload):
                raise MuensterWeatherDataError("Invalid JSON data")
            return [{str(k): str(v) for k, v in row.items()} for row in payload]
        if not isinstance(payload, str):
            raise MuensterWeatherDataError("Unsupported resource format")
        sample = payload[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t,")
            return list(csv.DictReader(io.StringIO(payload), dialect=dialect))
        except csv.Error as err:
            raise MuensterWeatherDataError("Invalid CSV data") from err

    async def async_get_stations(self) -> list[Station]:
        stations: dict[str, Station] = {}
        for row in await self._rows():
            station_id = _value(row, "station_id")
            if station_id:
                stations[station_id] = Station(
                    station_id,
                    _value(row, "station_name") or station_id,
                    _number(_value(row, "latitude")),
                    _number(_value(row, "longitude")),
                )
        if not stations:
            raise MuensterWeatherDataError("No stations found")
        return sorted(stations.values(), key=lambda station: station.name.casefold())

    async def async_get_observation(self, station_id: str) -> dict[str, Any]:
        matching = [row for row in await self._rows() if _value(row, "station_id") == station_id]
        if not matching:
            raise MuensterWeatherDataError(f"Station {station_id} is absent from the dataset")
        return _observation(matching[-1])

    async def async_get_averaged_observation(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        max_stations: int,
    ) -> dict[str, Any]:
        """Return a distance-weighted observation around a position."""
        rows = await self._rows()
        latest: dict[str, dict[str, str]] = {}
        stations: dict[str, Station] = {}
        for row in rows:
            station_id = _value(row, "station_id")
            if not station_id:
                continue
            latest[station_id] = row
            stations[station_id] = Station(
                station_id,
                _value(row, "station_name") or station_id,
                _number(_value(row, "latitude")),
                _number(_value(row, "longitude")),
            )
        nearby = sorted(
            (
                (_distance_km(latitude, longitude, station.latitude, station.longitude), station)
                for station in stations.values()
                if station.latitude is not None and station.longitude is not None
            ),
            key=lambda item: item[0],
        )
        nearby = [item for item in nearby if item[0] <= radius_km][:max_stations]
        if not nearby:
            raise MuensterWeatherDataError("No geolocated station is within the configured radius")

        observations = [(_observation(latest[station.station_id]), distance, station) for distance, station in nearby]
        weights = [1 / max(distance, 0.05) for _, distance, _ in observations]
        result: dict[str, Any] = {}
        for field in ("temperature", "humidity", "pressure", "wind_speed", "precipitation", "illuminance"):
            values = [(observation[field], weight) for (observation, _, _), weight in zip(observations, weights) if observation[field] is not None]
            result[field] = sum(value * weight for value, weight in values) / sum(weight for _, weight in values) if values else None
        bearings = [(observation["wind_bearing"], weight) for (observation, _, _), weight in zip(observations, weights) if observation["wind_bearing"] is not None]
        if bearings:
            x = sum(math.cos(math.radians(value)) * weight for value, weight in bearings)
            y = sum(math.sin(math.radians(value)) * weight for value, weight in bearings)
            result["wind_bearing"] = math.degrees(math.atan2(y, x)) % 360
        else:
            result["wind_bearing"] = None
        timestamps = [observation["observed_at"] for observation, _, _ in observations if observation["observed_at"]]
        result["observed_at"] = max(timestamps) if timestamps else None
        result["stations"] = [
            {"station_id": station.station_id, "name": station.name, "distance_km": round(distance, 2)}
            for _, distance, station in observations
        ]
        return result


def _observation(row: dict[str, str]) -> dict[str, Any]:
    """Normalise one source row."""
    timestamp = _value(row, "timestamp")
    observed_at = None
    if timestamp:
        try:
            observed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            pass
    return {
        "observed_at": observed_at,
        **{field: _number(_value(row, field)) for field in (
            "temperature", "humidity", "pressure", "wind_speed", "wind_bearing", "precipitation", "illuminance"
        )},
    }


def _distance_km(latitude: float, longitude: float, other_latitude: float, other_longitude: float) -> float:
    """Calculate the great-circle distance between two WGS84 positions."""
    lat1, lat2 = math.radians(latitude), math.radians(other_latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(other_longitude - longitude)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
