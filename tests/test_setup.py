"""End-to-end setup tests: config entry -> first refresh -> device -> entities."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.muenster_weather.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAX_STATIONS,
    CONF_MODE,
    CONF_RADIUS_KM,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DOMAIN,
    LATEST_PARAMS,
    MODE_ESTIMATE,
    MODE_STATION,
    STATION_PARAMS,
)

from .fixtures import LATEST_JSON, STATION_CSV

API_URL = "https://geo.stadt-muenster.de/mapserv/wetterstationen_serv"


@pytest.fixture(autouse=True)
def _freeze_to_fixture_time(freezer):
    """Keep LATEST_JSON's fixed timestamps fresh relative to "now"."""
    freezer.move_to("2026-09-07T10:00:00+02:00")


def _mock_stations(aioclient_mock, csv: str = STATION_CSV) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, text=csv)


async def _setup_station_entry(hass: HomeAssistant, aioclient_mock) -> MockConfigEntry:
    _mock_stations(aioclient_mock)
    aioclient_mock.get(API_URL, params=LATEST_PARAMS, json=[LATEST_JSON[0]])
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="station:50618",
        title="Aasee",
        data={
            CONF_MODE: MODE_STATION,
            CONF_STATION_ID: "50618",
            CONF_STATION_NAME: "Aasee",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _setup_estimate_entry(hass: HomeAssistant, aioclient_mock) -> MockConfigEntry:
    _mock_stations(aioclient_mock)
    aioclient_mock.get(API_URL, params=LATEST_PARAMS, json=LATEST_JSON)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="local_estimate",
        title="Münster Local Weather Estimate",
        data={
            CONF_MODE: MODE_ESTIMATE,
            CONF_LATITUDE: 51.9625,
            CONF_LONGITUDE: 7.6256,
            CONF_RADIUS_KM: 5.0,
            CONF_MAX_STATIONS: 5,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_station_setup_succeeds_and_creates_entities(
    hass: HomeAssistant, aioclient_mock
) -> None:
    entry = await _setup_station_entry(hass, aioclient_mock)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.aasee_temperature").state == "21.3"
    assert hass.states.get("sensor.aasee_humidity").state == "58.0"


async def test_station_setup_creates_device(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup_station_entry(hass, aioclient_mock)
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, "50618")})
    assert device is not None
    assert device.manufacturer == "Stadt Münster"
    assert device.name == "Aasee"
    assert entry.entry_id in device.config_entries


async def test_station_entity_unique_ids_are_stable(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup_station_entry(hass, aioclient_mock)
    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("sensor.aasee_temperature")
    assert entity is not None
    assert entity.unique_id == "50618_temperature"


async def test_station_disappearing_creates_repair_issue_and_fails_setup(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(
        API_URL,
        params=STATION_PARAMS,
        text="device_id;description;latitude;longitude\n99999;Other;51.9;7.6\n",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="station:50618",
        data={CONF_MODE: MODE_STATION, CONF_STATION_ID: "50618", CONF_STATION_NAME: "Aasee"},
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    issue_registry = ir.async_get(hass)
    assert issue_registry.async_get_issue(DOMAIN, f"station_removed_{entry.entry_id}") is not None


async def test_station_all_measurements_unavailable_entity_becomes_unavailable(
    hass: HomeAssistant, aioclient_mock
) -> None:
    _mock_stations(aioclient_mock)
    params = dict(LATEST_PARAMS)
    params["device_ids"] = "50618"
    aioclient_mock.get(API_URL, params=params, json=[])
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="station:50618",
        title="Aasee",
        data={CONF_MODE: MODE_STATION, CONF_STATION_ID: "50618", CONF_STATION_NAME: "Aasee"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.aasee_temperature").state == "unavailable"


async def test_station_stale_measurement_becomes_unavailable(
    hass: HomeAssistant, aioclient_mock
) -> None:
    _mock_stations(aioclient_mock)
    stale = dict(LATEST_JSON[0])
    stale["timestamp"] = "2026-09-07T08:00:00+02:00"  # 2 hours before frozen "now"
    aioclient_mock.get(API_URL, params=LATEST_PARAMS, json=[stale])
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="station:50618",
        title="Aasee",
        data={CONF_MODE: MODE_STATION, CONF_STATION_ID: "50618", CONF_STATION_NAME: "Aasee"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.aasee_temperature").state == "unavailable"


async def test_unload_entry(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup_station_entry(hass, aioclient_mock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


# --- Local estimate -------------------------------------------------------


async def test_estimate_setup_succeeds_and_interpolates(
    hass: HomeAssistant, aioclient_mock
) -> None:
    entry = await _setup_estimate_entry(hass, aioclient_mock)
    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get("sensor.munster_local_weather_estimate_temperature")
    assert state is not None
    assert state.state != "unavailable"


async def test_estimate_setup_creates_virtual_device(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup_estimate_entry(hass, aioclient_mock)
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, "local_estimate")})
    assert device is not None
    assert device.model == "Local weather estimate"


async def test_estimate_exposes_diagnostic_station_count(
    hass: HomeAssistant, aioclient_mock
) -> None:
    await _setup_estimate_entry(hass, aioclient_mock)
    state = hass.states.get("sensor.munster_local_weather_estimate_contributing_stations")
    assert state is not None
    assert state.state == "2"


async def test_estimate_temporary_outage_then_recovery(
    hass: HomeAssistant, aioclient_mock
) -> None:
    entry = await _setup_estimate_entry(hass, aioclient_mock)
    coordinator = entry.runtime_data

    aioclient_mock.clear_requests()
    _mock_stations(aioclient_mock)
    aioclient_mock.get(API_URL, params=LATEST_PARAMS, exc=TimeoutError())
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    aioclient_mock.clear_requests()
    _mock_stations(aioclient_mock)
    aioclient_mock.get(API_URL, params=LATEST_PARAMS, json=LATEST_JSON)
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
