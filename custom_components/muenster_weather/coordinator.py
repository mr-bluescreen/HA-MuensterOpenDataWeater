"""Data update coordinator for Münster Open Data Weather."""
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MuensterWeatherApiError, MuensterWeatherClient
from .const import (
    CONF_LATITUDE, CONF_LONGITUDE, CONF_MAX_STATIONS, CONF_MODE, CONF_RADIUS_KM,
    DEFAULT_SCAN_INTERVAL, DOMAIN, MODE_AUTOMATIC,
)


class MuensterWeatherCoordinator(DataUpdateCoordinator[dict]):
    """Coordinate one station's observations."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: MuensterWeatherClient) -> None:
        super().__init__(hass, logger=__import__("logging").getLogger(__name__), name=DOMAIN,
                         update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL), config_entry=entry)
        self.client = client
        self.station_id = entry.data["station_id"]

    async def _async_update_data(self) -> dict:
        try:
            if self.config_entry.data.get(CONF_MODE) == MODE_AUTOMATIC:
                return await self.client.async_get_averaged_observation(
                    self.config_entry.data[CONF_LATITUDE],
                    self.config_entry.data[CONF_LONGITUDE],
                    self.config_entry.data[CONF_RADIUS_KM],
                    self.config_entry.data[CONF_MAX_STATIONS],
                )
            return await self.client.async_get_observation(self.station_id)
        except MuensterWeatherApiError as err:
            raise UpdateFailed(str(err)) from err
