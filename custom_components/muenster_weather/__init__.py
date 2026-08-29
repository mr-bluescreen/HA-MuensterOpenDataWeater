"""Münster Open Data Weather integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MuensterWeatherClient
from .coordinator import MuensterWeatherCoordinator

PLATFORMS = [Platform.SENSOR, Platform.WEATHER]
type MuensterWeatherConfigEntry = ConfigEntry[MuensterWeatherCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MuensterWeatherConfigEntry) -> bool:
    """Set up an entry."""
    coordinator = MuensterWeatherCoordinator(
        hass, entry, MuensterWeatherClient(async_get_clientsession(hass))
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MuensterWeatherConfigEntry) -> bool:
    """Unload an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
