"""Local geographic selection and inverse-distance interpolation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
import math

from .api import Measurement, Station
from .const import IDW_POWER, MINIMUM_DISTANCE_KM


@dataclass(frozen=True, slots=True)
class Contributor:
    station: Station
    measurement: Measurement
    distance_km: float


@dataclass(frozen=True, slots=True)
class Estimate:
    temperature: float | None
    humidity: float | None
    heat_status: str | None
    observed_at: datetime | None
    temperature_contributors: tuple[Contributor, ...]
    humidity_contributors: tuple[Contributor, ...]


def distance_km(
    latitude: float, longitude: float, other_latitude: float, other_longitude: float
) -> float:
    """Return WGS84 great-circle distance in kilometres."""
    lat1, lat2 = math.radians(latitude), math.radians(other_latitude)
    dlat, dlon = lat2 - lat1, math.radians(other_longitude - longitude)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def select_contributors(
    stations: Iterable[Station],
    measurements: dict[str, Measurement],
    latitude: float,
    longitude: float,
    radius_km: float,
    maximum: int,
    now: datetime,
    stale_after: timedelta,
) -> tuple[Contributor, ...]:
    """Select nearest fresh station observations within the closed radius."""
    candidates = []
    for station in stations:
        measurement = measurements.get(station.station_id)
        distance = distance_km(latitude, longitude, station.latitude, station.longitude)
        if (
            measurement is not None
            and now - measurement.observed_at <= stale_after
            and distance <= radius_km
        ):
            candidates.append(Contributor(station, measurement, distance))
    return tuple(sorted(candidates, key=lambda item: item.distance_km)[:maximum])


def _idw(
    contributors: Iterable[Contributor], getter: Callable[[Measurement], float | None]
) -> tuple[float | None, tuple[Contributor, ...]]:
    valid = tuple(item for item in contributors if getter(item.measurement) is not None)
    if not valid:
        return None, ()
    if valid[0].distance_km <= MINIMUM_DISTANCE_KM:
        return getter(valid[0].measurement), (valid[0],)
    weighted = [
        (getter(item.measurement), 1 / item.distance_km**IDW_POWER) for item in valid
    ]
    return sum(value * weight for value, weight in weighted if value is not None) / sum(
        weight for _, weight in weighted
    ), valid


def interpolate(contributors: Iterable[Contributor]) -> Estimate:
    """Interpolate each continuous field independently with IDW power two."""
    contributors = tuple(contributors)
    temperature, temperature_sources = _idw(contributors, lambda item: item.temperature)
    humidity, humidity_sources = _idw(contributors, lambda item: item.humidity)
    freshest = max(
        (item.measurement.observed_at for item in contributors), default=None
    )
    # Heat status is categorical; transparently use the nearest fresh source.
    heat_status = next(
        (
            item.measurement.heat_status
            for item in contributors
            if item.measurement.heat_status
        ),
        None,
    )
    return Estimate(
        temperature,
        humidity,
        heat_status,
        freshest,
        temperature_sources,
        humidity_sources,
    )
