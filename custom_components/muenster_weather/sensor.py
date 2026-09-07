"""Sensor entities for Münster Open Data Weather."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfLength,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MuensterWeatherConfigEntry
from .const import CONF_MODE, MODE_ESTIMATE
from .coordinator import CoordinatorData
from .entity import MuensterWeatherEntity

Value = float | int | str | datetime | None


@dataclass(frozen=True, kw_only=True)
class Description(SensorEntityDescription):
    value_fn: Callable[[CoordinatorData], Value]
    estimate_only: bool = False


DESCRIPTIONS = (
    Description(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: (
            data.estimate.temperature
            if data.estimate
            else data.measurement.temperature
            if data.measurement
            else None
        ),
    ),
    Description(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: (
            data.estimate.humidity
            if data.estimate
            else data.measurement.humidity
            if data.measurement
            else None
        ),
    ),
    Description(
        key="heat_status",
        translation_key="heat_status",
        value_fn=lambda data: (
            data.estimate.heat_status
            if data.estimate
            else data.measurement.heat_status
            if data.measurement
            else None
        ),
    ),
    Description(
        key="observed_at",
        translation_key="observed_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: (
            data.estimate.observed_at
            if data.estimate
            else data.measurement.observed_at
            if data.measurement
            else None
        ),
    ),
    Description(
        key="station_count",
        translation_key="station_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: len(data.contributors),
        estimate_only=True,
    ),
    Description(
        key="nearest_distance",
        translation_key="nearest_distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
        value_fn=lambda data: min(
            (item.distance_km for item in data.contributors), default=None
        ),
        estimate_only=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MuensterWeatherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    estimate = entry.data[CONF_MODE] == MODE_ESTIMATE
    async_add_entities(
        MuensterWeatherSensor(entry.runtime_data, description)
        for description in DESCRIPTIONS
        if estimate or not description.estimate_only
    )


class MuensterWeatherSensor(MuensterWeatherEntity, SensorEntity):
    entity_description: Description

    def __init__(self, coordinator, description: Description) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self.identity}_{description.key}"

    @property
    def native_value(self) -> Value:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None
