"""Asynchronous client for the Stadt Münster weather-station WFS."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import math
from typing import Final, TypeAlias

from aiohttp import ClientError, ClientSession

from .const import API_URL, LATEST_PARAMS, STATION_PARAMS

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class MuensterWeatherError(Exception):
    """Base client exception."""


class MuensterWeatherConnectionError(MuensterWeatherError):
    """The service could not be reached."""


class MuensterWeatherResponseError(MuensterWeatherError):
    """The service returned an invalid response."""


@dataclass(frozen=True, slots=True)
class Station:
    """A public station from the master-data feature type."""

    station_id: str
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class Measurement:
    """One latest observation; missing and rejected values remain ``None``."""

    station_id: str
    observed_at: datetime
    temperature: float | None
    humidity: float | None
    heat_status: str | None
    temperature_valid: bool
    humidity_valid: bool


_ID: Final = ("device_id", "deviceid", "stations_id", "station_id", "station", "id")
_NAME: Final = ("name", "bezeichnung", "standort", "stationsname", "station_name")
_TIME: Final = ("timestamp", "zeitstempel", "messzeitpunkt", "datum", "time")
_TEMP: Final = ("temperature", "temperatur", "temp", "lufttemperatur")
_HUMIDITY: Final = (
    "humidity",
    "luftfeuchtigkeit",
    "relative_luftfeuchtigkeit",
    "rel_humidity",
)
_HEAT: Final = ("heat_notification", "hitzewarnung", "hitzestatus", "heat_status")
_TEMP_QUALITY: Final = (
    "temperature_quality",
    "qualitaet_temperatur",
    "temp_quality",
    "q_temperature",
)
_HUMIDITY_QUALITY: Final = (
    "humidity_quality",
    "qualitaet_luftfeuchtigkeit",
    "humidity_quality_flag",
    "q_humidity",
)
_LAT: Final = ("latitude", "lat", "breitengrad")
_LON: Final = ("longitude", "lon", "lng", "laengengrad")


def _key(value: str) -> str:
    replacements: dict[str, str | int | None] = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    return "".join(
        character
        for character in value.casefold().translate(str.maketrans(replacements))
        if character.isalnum()
    )


def _properties(value: object) -> tuple[Mapping[str, object], Sequence[object] | None]:
    if not isinstance(value, Mapping):
        raise MuensterWeatherResponseError("A feature must be an object")
    properties = value.get("properties", value)
    if not isinstance(properties, Mapping):
        raise MuensterWeatherResponseError("Feature properties must be an object")
    geometry = value.get("geometry")
    coordinates: Sequence[object] | None = None
    if isinstance(geometry, Mapping) and isinstance(
        geometry.get("coordinates"), Sequence
    ):
        coordinates = geometry["coordinates"]
    return properties, coordinates


def _get(properties: Mapping[str, object], aliases: Sequence[str]) -> object | None:
    normalised = {_key(str(key)): value for key, value in properties.items()}
    return next(
        (normalised[_key(alias)] for alias in aliases if _key(alias) in normalised),
        None,
    )


def _number(
    value: object, *, minimum: float | None = None, maximum: float | None = None
) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip().replace(",", "."))
    except ValueError:
        return None
    if (
        not math.isfinite(number)
        or minimum is not None
        and number < minimum
        or maximum is not None
        and number > maximum
    ):
        return None
    return number


def _quality_is_valid(value: object) -> bool:
    """Accept absent/explicitly-good flags and reject explicit bad flags.

    The WFS has emitted both booleans and textual quality labels. Unknown values
    are rejected rather than guessed, which is the safe behaviour for estimates.
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {
        "0",
        "ok",
        "valid",
        "gültig",
        "gueltig",
        "good",
    }


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MuensterWeatherResponseError("Measurement timestamp is missing")
    text = value.strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(text)
    except ValueError as err:
        raise MuensterWeatherResponseError("Measurement timestamp is invalid") from err
    # Source timestamps without an offset are local Münster civil time.
    if result.tzinfo is None:
        from zoneinfo import ZoneInfo

        result = result.replace(tzinfo=ZoneInfo("Europe/Berlin"))
    return result.astimezone(UTC)


def parse_stations(payload: object) -> list[Station]:
    """Parse GeoJSON station master data (coordinates are longitude, latitude)."""
    features = payload.get("features") if isinstance(payload, Mapping) else payload
    if not isinstance(features, list):
        raise MuensterWeatherResponseError("Station response has no feature list")
    stations: dict[str, Station] = {}
    for feature in features:
        properties, coordinates = _properties(feature)
        identifier = _get(properties, _ID)
        longitude = _number(
            coordinates[0]
            if coordinates and len(coordinates) >= 2
            else _get(properties, _LON),
            minimum=-180,
            maximum=180,
        )
        latitude = _number(
            coordinates[1]
            if coordinates and len(coordinates) >= 2
            else _get(properties, _LAT),
            minimum=-90,
            maximum=90,
        )
        if identifier is None or latitude is None or longitude is None:
            continue
        station_id = str(identifier).strip()
        stations[station_id] = Station(
            station_id,
            str(_get(properties, _NAME) or station_id).strip(),
            latitude,
            longitude,
        )
    if not stations:
        raise MuensterWeatherResponseError(
            "Station response contains no usable stations"
        )
    return sorted(
        stations.values(),
        key=lambda station: (station.name.casefold(), station.station_id),
    )


def parse_measurements(payload: object) -> dict[str, Measurement]:
    """Parse the latest-measurement JSON/GeoJSON representation."""
    records = (
        payload.get("features", payload.get("data", payload.get("records")))
        if isinstance(payload, Mapping)
        else payload
    )
    if not isinstance(records, list):
        raise MuensterWeatherResponseError("Measurement response has no record list")
    result: dict[str, Measurement] = {}
    for record in records:
        properties, _ = _properties(record)
        identifier = _get(properties, _ID)
        if identifier is None:
            continue
        temperature_valid = _quality_is_valid(_get(properties, _TEMP_QUALITY))
        humidity_valid = _quality_is_valid(_get(properties, _HUMIDITY_QUALITY))
        measurement = Measurement(
            station_id=str(identifier).strip(),
            observed_at=_timestamp(_get(properties, _TIME)),
            temperature=_number(_get(properties, _TEMP), minimum=-60, maximum=70)
            if temperature_valid
            else None,
            humidity=_number(_get(properties, _HUMIDITY), minimum=0, maximum=100)
            if humidity_valid
            else None,
            heat_status=str(value).strip()
            if (value := _get(properties, _HEAT)) not in (None, "")
            else None,
            temperature_valid=temperature_valid,
            humidity_valid=humidity_valid,
        )
        old = result.get(measurement.station_id)
        if old is None or measurement.observed_at > old.observed_at:
            result[measurement.station_id] = measurement
    return result


class MuensterWeatherClient:
    """Small injected-session WFS client."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _get(self, params: Mapping[str, str]) -> object:
        try:
            async with self._session.get(API_URL, params=params) as response:
                response.raise_for_status()
                return await response.json(content_type=None)
        except (ClientError, TimeoutError) as err:
            raise MuensterWeatherConnectionError from err
        except (ValueError, TypeError) as err:
            raise MuensterWeatherResponseError("Response is not valid JSON") from err

    async def async_get_stations(self) -> list[Station]:
        return parse_stations(await self._get(STATION_PARAMS))

    async def async_get_latest(
        self, station_ids: Sequence[str]
    ) -> dict[str, Measurement]:
        params = dict(LATEST_PARAMS)
        if station_ids:
            params["device_ids"] = ",".join(station_ids)
        return parse_measurements(await self._get(params))
