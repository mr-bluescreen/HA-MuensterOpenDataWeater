"""Münster Open Data Weather integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import issue_registry as ir

from .api import MuensterWeatherClient
from .const import CONF_MODE, CONF_STATION_ID, DOMAIN, MODE_ESTIMATE
from .coordinator import MuensterWeatherCoordinator

PLATFORMS = [Platform.SENSOR]
type MuensterWeatherConfigEntry = ConfigEntry[MuensterWeatherCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: MuensterWeatherConfigEntry
) -> bool:
    """Set up an entry after validating master data and initial observations."""
    client = MuensterWeatherClient(async_get_clientsession(hass))
    stations = await client.async_get_stations()
    issue_id = f"station_removed_{entry.entry_id}"
    if entry.data[CONF_MODE] != MODE_ESTIMATE and not any(
        station.station_id == entry.data[CONF_STATION_ID] for station in stations
    ):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key="station_removed",
            translation_placeholders={"station_id": entry.data[CONF_STATION_ID]},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    coordinator = MuensterWeatherCoordinator(hass, entry, client, stations)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MuensterWeatherConfigEntry
) -> bool:
    """Unload an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(
    hass: HomeAssistant, entry: MuensterWeatherConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
