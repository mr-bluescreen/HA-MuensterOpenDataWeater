"""Data update coordinator for Münster weather observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Measurement, MuensterWeatherClient, MuensterWeatherError, Station
from .const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAX_STATIONS,
    CONF_MODE,
    CONF_RADIUS_KM,
    CONF_STATION_ID,
    DOMAIN,
    MODE_ESTIMATE,
    STALE_AFTER_MINUTES,
    UPDATE_INTERVAL_MINUTES,
)
from .interpolation import (
    Contributor,
    Estimate,
    distance_km,
    interpolate,
    select_contributors,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CoordinatorData:
    measurement: Measurement | None
    estimate: Estimate | None
    contributors: tuple[Contributor, ...]


class MuensterWeatherCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Fetch a filtered set of current measurements for one entry."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: MuensterWeatherClient,
        stations: list[Station],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self.client = client
        self.stations = stations
        self.station = next(
            (
                station
                for station in stations
                if station.station_id == entry.data.get(CONF_STATION_ID)
            ),
            None,
        )
        if entry.data[CONF_MODE] != MODE_ESTIMATE and self.station is None:
            raise ConfigEntryError(
                translation_domain=DOMAIN, translation_key="station_removed"
            )

    async def _async_update_data(self) -> CoordinatorData:
        try:
            if self.config_entry.data[CONF_MODE] != MODE_ESTIMATE:
                assert self.station is not None
                values = await self.client.async_get_latest([self.station.station_id])
                measurement = values.get(self.station.station_id)
                if measurement is not None and datetime.now(
                    UTC
                ) - measurement.observed_at > timedelta(minutes=STALE_AFTER_MINUTES):
                    measurement = None
                return CoordinatorData(measurement, None, ())
            latitude = float(
                self.config_entry.options.get(
                    CONF_LATITUDE, self.config_entry.data[CONF_LATITUDE]
                )
            )
            longitude = float(
                self.config_entry.options.get(
                    CONF_LONGITUDE, self.config_entry.data[CONF_LONGITUDE]
                )
            )
            radius = float(
                self.config_entry.options.get(
                    CONF_RADIUS_KM, self.config_entry.data[CONF_RADIUS_KM]
                )
            )
            maximum = int(
                self.config_entry.options.get(
                    CONF_MAX_STATIONS, self.config_entry.data[CONF_MAX_STATIONS]
                )
            )
            nearby = sorted(
                self.stations,
                key=lambda station: distance_km(
                    latitude, longitude, station.latitude, station.longitude
                ),
            )
            ids = [
                station.station_id
                for station in nearby
                if distance_km(latitude, longitude, station.latitude, station.longitude)
                <= radius
            ][:maximum]
            values = await self.client.async_get_latest(ids) if ids else {}
            contributors = select_contributors(
                self.stations,
                values,
                latitude,
                longitude,
                radius,
                maximum,
                datetime.now(UTC),
                timedelta(minutes=STALE_AFTER_MINUTES),
            )
            return CoordinatorData(None, interpolate(contributors), contributors)
        except MuensterWeatherError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="update_failed"
            ) from err
