"""Data update coordinator for Münster Open Data Weather."""
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MuensterWeatherApiError, MuensterWeatherClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN


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
            return await self.client.async_get_observation(self.station_id)
        except MuensterWeatherApiError as err:
            raise UpdateFailed(str(err)) from err
