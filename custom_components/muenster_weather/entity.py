"""Shared entities for Münster Open Data Weather."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODE, CONF_STATION_ID, DATASET_URL, DOMAIN, MODE_ESTIMATE
from .coordinator import MuensterWeatherCoordinator


class MuensterWeatherEntity(CoordinatorEntity[MuensterWeatherCoordinator]):
    """Entity associated with a municipal station or virtual estimate device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MuensterWeatherCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        estimate = entry.data[CONF_MODE] == MODE_ESTIMATE
        identity = "local_estimate" if estimate else entry.data[CONF_STATION_ID]
        self.identity = identity
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity)},
            name=entry.title,
            manufacturer="Stadt Münster",
            model="Local weather estimate" if estimate else "Public weather station",
            configuration_url=DATASET_URL,
        )
