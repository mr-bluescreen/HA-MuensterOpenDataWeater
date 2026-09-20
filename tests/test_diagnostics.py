"""Diagnostics tests: useful information without leaking private coordinates."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.muenster_weather.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAX_STATIONS,
    CONF_MODE,
    CONF_RADIUS_KM,
    DOMAIN,
    LATEST_PARAMS,
    MODE_ESTIMATE,
    STATION_PARAMS,
)
from custom_components.muenster_weather.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .fixtures import LATEST_JSON, STATION_CSV

API_URL = "https://geo.stadt-muenster.de/mapserv/wetterstationen_serv"

# Coordinates the diagnostics output must never contain, no matter how they
# are formatted (float repr, rounded, etc.).
PRIVATE_LATITUDE = 51.9625
PRIVATE_LONGITUDE = 7.6256


@pytest.fixture(autouse=True)
def _freeze_to_fixture_time(freezer):
    freezer.move_to("2026-09-07T10:00:00+02:00")


async def test_diagnostics_omit_private_coordinates(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, text=STATION_CSV)
    aioclient_mock.get(API_URL, params=LATEST_PARAMS, json=LATEST_JSON)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="local_estimate",
        title="Münster Local Weather Estimate",
        data={
            CONF_MODE: MODE_ESTIMATE,
            CONF_LATITUDE: PRIVATE_LATITUDE,
            CONF_LONGITUDE: PRIVATE_LONGITUDE,
            CONF_RADIUS_KM: 5.0,
            CONF_MAX_STATIONS: 5,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    serialised = repr(diagnostics)
    assert str(PRIVATE_LATITUDE) not in serialised
    assert str(PRIVATE_LONGITUDE) not in serialised
    assert "latitude" not in diagnostics
    assert "longitude" not in diagnostics


async def test_diagnostics_report_useful_information(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, text=STATION_CSV)
    aioclient_mock.get(API_URL, params=LATEST_PARAMS, json=LATEST_JSON)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="local_estimate",
        title="Münster Local Weather Estimate",
        data={
            CONF_MODE: MODE_ESTIMATE,
            CONF_LATITUDE: PRIVATE_LATITUDE,
            CONF_LONGITUDE: PRIVATE_LONGITUDE,
            CONF_RADIUS_KM: 5.0,
            CONF_MAX_STATIONS: 5,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["mode"] == MODE_ESTIMATE
    assert diagnostics["radius_km"] == 5.0
    assert diagnostics["maximum_stations"] == 5
    assert diagnostics["last_update_success"] is True
    assert diagnostics["known_station_count"] == 3
    assert set(diagnostics["contributing_station_ids"]) == {"50618", "50619"}
    assert "observed_at" in diagnostics
