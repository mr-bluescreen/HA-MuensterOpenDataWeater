"""Weather entity for Münster Open Data Weather."""
from homeassistant.components.weather import WeatherEntity, WeatherEntityFeature
from homeassistant.const import UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MuensterWeatherConfigEntry
from .entity import MuensterWeatherEntity


async def async_setup_entry(hass: HomeAssistant, entry: MuensterWeatherConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """Set up the current conditions entity."""
    async_add_entities([MuensterWeather(entry.runtime_data)])


class MuensterWeather(MuensterWeatherEntity, WeatherEntity):
    """Current observations (the source does not publish forecasts)."""

    _attr_translation_key = "current"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_supported_features = WeatherEntityFeature(0)
    _attr_condition = None

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.station_id}_weather"

    @property
    def native_temperature(self):
        return self.coordinator.data["temperature"]

    @property
    def humidity(self):
        return self.coordinator.data["humidity"]

    @property
    def native_pressure(self):
        return self.coordinator.data["pressure"]

    @property
    def native_wind_speed(self):
        return self.coordinator.data["wind_speed"]

    @property
    def wind_bearing(self):
        return self.coordinator.data["wind_bearing"]
