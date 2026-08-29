"""Async client for Münster's Open Data weather dataset."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import io
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
}


def _normalise(value: str) -> str:
    return "".join(char for char in value.casefold().replace("ß", "ss") if char.isalnum() or char == "_")


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

    async def _resource_url(self) -> str:
        if self._data_url:
            return self._data_url
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
        self._data_url = candidates[-1]["url"]
        return self._data_url

    async def _rows(self) -> list[dict[str, str]]:
        payload = await self._request(await self._resource_url())
        if isinstance(payload, dict):
            payload = payload.get("result", {}).get("records", payload.get("records", []))
        if isinstance(payload, list):
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
                stations[station_id] = Station(station_id, _value(row, "station_name") or station_id)
        if not stations:
            raise MuensterWeatherDataError("No stations found")
        return sorted(stations.values(), key=lambda station: station.name.casefold())

    async def async_get_observation(self, station_id: str) -> dict[str, Any]:
        matching = [row for row in await self._rows() if _value(row, "station_id") == station_id]
        if not matching:
            raise MuensterWeatherDataError(f"Station {station_id} is absent from the dataset")
        row = matching[-1]
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
