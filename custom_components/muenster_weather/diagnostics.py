"""Diagnostics support with private target coordinates deliberately omitted."""

from homeassistant.core import HomeAssistant

from . import MuensterWeatherConfigEntry
from .const import CONF_MAX_STATIONS, CONF_MODE, CONF_RADIUS_KM, CONF_STATION_ID


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MuensterWeatherConfigEntry
) -> dict[str, object]:
    coordinator = entry.runtime_data
    data: dict[str, object] = {
        "mode": entry.data[CONF_MODE],
        "station_id": entry.data.get(CONF_STATION_ID),
        "radius_km": entry.options.get(CONF_RADIUS_KM, entry.data.get(CONF_RADIUS_KM)),
        "maximum_stations": entry.options.get(
            CONF_MAX_STATIONS, entry.data.get(CONF_MAX_STATIONS)
        ),
        "last_update_success": coordinator.last_update_success,
        "known_station_count": len(coordinator.stations),
        "contributing_station_ids": [
            item.station.station_id for item in coordinator.data.contributors
        ],
    }
    if coordinator.data.measurement:
        data["observed_at"] = coordinator.data.measurement.observed_at.isoformat()
    elif coordinator.data.estimate and coordinator.data.estimate.observed_at:
        data["observed_at"] = coordinator.data.estimate.observed_at.isoformat()
    return data
