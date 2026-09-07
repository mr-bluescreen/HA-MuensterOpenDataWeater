"""Asynchronous client for the Stadt Münster weather-station WFS."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import io
import logging
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


class MuensterWeatherNoStationsError(MuensterWeatherError):
    """A valid station registry contains no usable stations."""


@dataclass(frozen=True, slots=True)
class Station:
    """A public station from the master-data feature type."""

    station_id: str
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class CurrentMeasurement:
    """One latest observation; missing and rejected values remain ``None``."""

    station_id: str
    observed_at: datetime
    temperature: float | None
    humidity: float | None
    heat_status: str | None
    temperature_valid: bool
    humidity_valid: bool


# Compatibility alias for the initial public release.
Measurement = CurrentMeasurement


_ID: Final = ("device_id", "deviceid", "stations_id", "station_id", "station", "id")
_NAME: Final = (
    "description",
    "beschreibung",
    "name",
    "bezeichnung",
    "standort",
    "stationsname",
    "station_name",
)
_TIME: Final = (
    "timestamp",
    "datetime",
    "observed_at",
    "zeitstempel",
    "messzeitpunkt",
    "datum",
    "time",
)
_TEMP: Final = (
    "temperature", "air_temperature", "temperatur", "temp", "lufttemperatur"
)
_HUMIDITY: Final = (
    "humidity",
    "luftfeuchtigkeit",
    "relative_luftfeuchtigkeit",
    "rel_humidity",
    "relative_humidity",
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

_LOGGER = logging.getLogger(__name__)


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
    """Parse the station registry CSV, with GeoJSON support for compatibility."""
    if isinstance(payload, str):
        if not payload.strip():
            raise MuensterWeatherNoStationsError("Station response is empty")
        try:
            dialect = csv.Sniffer().sniff(payload[:4096], delimiters=";,\t")
            payload = list(csv.DictReader(io.StringIO(payload), dialect=dialect))
        except csv.Error as err:
            raise MuensterWeatherResponseError("Station response is invalid CSV") from err
    features = payload.get("features") if isinstance(payload, Mapping) else payload
    if not isinstance(features, list):
        raise MuensterWeatherResponseError("Station response has no feature list")
    _LOGGER.debug("Station metadata contains %d raw records", len(features))
    stations: dict[str, Station] = {}
    for feature in features:
        try:
            properties, coordinates = _properties(feature)
        except MuensterWeatherResponseError as err:
            _LOGGER.debug("Skipping malformed station record: %s", err)
            continue
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
            _LOGGER.debug(
                "Skipping station record with missing ID or malformed coordinates"
            )
            continue
        station_id = str(identifier).strip()
        if not station_id:
            continue
        stations[station_id] = Station(
            station_id,
            str(_get(properties, _NAME) or station_id).strip(),
            latitude,
            longitude,
        )
    if not stations:
        raise MuensterWeatherNoStationsError(
            "Station response contains no usable stations"
        )
    return sorted(
        stations.values(),
        key=lambda station: (station.name.casefold(), station.station_id),
    )


def _measurement_records(payload: object) -> list[object]:
    """Extract records from representations emitted by ``JSON_AKTUELL``."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, Mapping):
        raise MuensterWeatherResponseError("Measurement response has no record list")
    for key in (
        "features", "data", "records", "measurements", "wetterstationen_aktuell"
    ):
        if isinstance(records := payload.get(key), list):
            return records
    indexed: list[object] = []
    for station_id, value in payload.items():
        if not isinstance(value, Mapping):
            break
        item = dict(value)
        item.setdefault("device_id", station_id)
        indexed.append(item)
    if indexed and len(indexed) == len(payload):
        return indexed
    raise MuensterWeatherResponseError("Measurement response has no record list")


def parse_measurements(payload: object) -> dict[str, CurrentMeasurement]:
    """Parse current observations independently of station master data."""
    records = _measurement_records(payload)
    result: dict[str, CurrentMeasurement] = {}
    for record in records:
        properties, _ = _properties(record)
        identifier = _get(properties, _ID)
        if identifier is None:
            continue
        temperature_valid = _quality_is_valid(_get(properties, _TEMP_QUALITY))
        humidity_valid = _quality_is_valid(_get(properties, _HUMIDITY_QUALITY))
        station_id = str(identifier).strip()
        if not station_id:
            continue
        measurement = CurrentMeasurement(
            station_id=station_id,
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

    async def _get(self, params: Mapping[str, str], *, json: bool = True) -> object:
        try:
            async with self._session.get(API_URL, params=params) as response:
                _LOGGER.debug("Requesting Münster weather resource: %s", response.url)
                response.raise_for_status()
                _LOGGER.debug(
                    "Received Münster weather response: status=%s content_type=%s",
                    response.status,
                    response.content_type,
                )
                return (
                    await response.json(content_type=None)
                    if json
                    else await response.text()
                )
        except (ClientError, TimeoutError) as err:
            raise MuensterWeatherConnectionError from err
        except (ValueError, TypeError) as err:
            raise MuensterWeatherResponseError("Response is not valid JSON") from err

    async def async_get_stations(self) -> list[Station]:
        payload = await self._get(STATION_PARAMS, json=False)
        _LOGGER.debug("Station metadata top-level response type: %s", type(payload).__name__)
        stations = parse_stations(payload)
        _LOGGER.debug("Successfully parsed %d stations", len(stations))
        return stations

    async def async_get_latest(
        self, station_ids: Sequence[str]
    ) -> dict[str, CurrentMeasurement]:
        params = dict(LATEST_PARAMS)
        if station_ids:
            params["device_ids"] = ",".join(
                str(value).strip() for value in station_ids
            )
        _LOGGER.debug("Requesting current measurements for station IDs %s", station_ids)
        values = parse_measurements(await self._get(params))
        _LOGGER.debug("Received %d current measurement records", len(values))
        return values
