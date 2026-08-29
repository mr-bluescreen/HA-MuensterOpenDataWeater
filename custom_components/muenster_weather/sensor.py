"""Sensors for Münster Open Data Weather."""
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfIlluminance, UnitOfLength, UnitOfPressure, UnitOfSpeed, UnitOfTemperature, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MuensterWeatherConfigEntry
from .entity import MuensterWeatherEntity


@dataclass(frozen=True, kw_only=True)
class Description(SensorEntityDescription):
    """Describe a measurement."""
    value_fn: Callable[[dict], float | None]


DESCRIPTIONS = (
    Description(key="temperature", translation_key="temperature", device_class=SensorDeviceClass.TEMPERATURE,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda x: x["temperature"]),
    Description(key="humidity", translation_key="humidity", device_class=SensorDeviceClass.HUMIDITY,
                native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda x: x["humidity"]),
    Description(key="pressure", translation_key="pressure", device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
                native_unit_of_measurement=UnitOfPressure.HPA, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda x: x["pressure"]),
    Description(key="wind_speed", translation_key="wind_speed", device_class=SensorDeviceClass.WIND_SPEED,
                native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda x: x["wind_speed"]),
    Description(key="precipitation", translation_key="precipitation", device_class=SensorDeviceClass.PRECIPITATION,
                native_unit_of_measurement=UnitOfLength.MILLIMETERS, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda x: x["precipitation"]),
    Description(key="illuminance", translation_key="illuminance", device_class=SensorDeviceClass.ILLUMINANCE,
                native_unit_of_measurement=UnitOfIlluminance.LUX, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda x: x["illuminance"]),
)


async def async_setup_entry(hass: HomeAssistant, entry: MuensterWeatherConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """Set up available station sensors."""
    async_add_entities(Measurement(entry.runtime_data, description) for description in DESCRIPTIONS)


class Measurement(MuensterWeatherEntity, SensorEntity):
    """A published station measurement."""
    entity_description: Description

    def __init__(self, coordinator, description: Description) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.station_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the latest measurement."""
        return self.entity_description.value_fn(self.coordinator.data)
