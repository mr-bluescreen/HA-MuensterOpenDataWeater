"""Shared entity support."""
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODE, DOMAIN, MODE_AUTOMATIC
from .coordinator import MuensterWeatherCoordinator


class MuensterWeatherEntity(CoordinatorEntity[MuensterWeatherCoordinator]):
    """Base entity attached to a station device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MuensterWeatherCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        automatic = entry.data.get(CONF_MODE) == MODE_AUTOMATIC
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.station_id)},
            name=entry.data["station_name"],
            manufacturer="Stadt Münster",
            model="Distance-weighted local average" if automatic else "Open Data weather station",
            configuration_url="https://opendata.stadt-muenster.de/dataset/messdaten-der-wetterstationen-aus-dem-projekt-stadt-temperatur",
        )

    @property
    def extra_state_attributes(self):
        """Expose contributing stations for an automatic aggregate."""
        if self.coordinator.config_entry.data.get(CONF_MODE) == MODE_AUTOMATIC:
            return {"contributing_stations": self.coordinator.data.get("stations", [])}
        return None
