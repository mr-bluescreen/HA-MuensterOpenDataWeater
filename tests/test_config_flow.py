"""Config and options flow tests using the real Home Assistant test harness."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.muenster_weather.const import (
    CONF_MAX_STATIONS,
    CONF_MODE,
    CONF_RADIUS_KM,
    CONF_STATION_ID,
    DOMAIN,
    MODE_ESTIMATE,
    MODE_STATION,
    STATION_PARAMS,
)

from .fixtures import STATION_CSV

API_URL = "https://geo.stadt-muenster.de/mapserv/wetterstationen_serv"


def _mock_stations(aioclient_mock, csv: str = STATION_CSV) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, text=csv)


async def _start_menu(hass: HomeAssistant, step: str) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


# --- Individual station -----------------------------------------------------


async def test_station_selector_shows_name_and_id(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_stations(aioclient_mock)
    result = await _start_menu(hass, "station")
    options = result["data_schema"].schema[CONF_STATION_ID].config["options"]
    assert {"value": "50618", "label": "Aasee (50618)"} in options
    # The selector's stored value is the stable ID, never the display label.
    assert all(len(o["value"]) < len(o["label"]) for o in options)


async def test_station_mode_creates_entry_with_stable_id(
    hass: HomeAssistant, aioclient_mock
) -> None:
    _mock_stations(aioclient_mock)
    result = await _start_menu(hass, "station")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STATION_ID: "50618"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MODE] == MODE_STATION
    assert result["data"][CONF_STATION_ID] == "50618"
    assert result["title"] == "Aasee"


async def test_duplicate_physical_station_is_rejected(
    hass: HomeAssistant, aioclient_mock
) -> None:
    _mock_stations(aioclient_mock)
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="station:50618",
        data={CONF_MODE: MODE_STATION, CONF_STATION_ID: "50618"},
    ).add_to_hass(hass)

    result = await _start_menu(hass, "station")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STATION_ID: "50618"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_station_step_cannot_connect_error(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, exc=TimeoutError())
    result = await _start_menu(hass, "station")
    assert result["errors"]["base"] == "cannot_connect"


async def test_station_step_no_stations_error(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, text="device_id;description;latitude;longitude\n")
    result = await _start_menu(hass, "station")
    assert result["errors"]["base"] == "no_stations"


async def test_station_step_malformed_data_error(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, text='{"type": "FeatureCollection"}')
    result = await _start_menu(hass, "station")
    assert result["errors"]["base"] == "invalid_data"


async def test_station_step_recovers_after_temporary_failure(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, exc=TimeoutError())
    result = await _start_menu(hass, "station")
    assert result["errors"]["base"] == "cannot_connect"

    aioclient_mock.clear_requests()
    _mock_stations(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], None)
    assert not result.get("errors")


# --- Local estimate ----------------------------------------------------------


async def test_estimate_creates_entry_with_local_coordinates(
    hass: HomeAssistant, aioclient_mock
) -> None:
    _mock_stations(aioclient_mock)
    hass.config.latitude = 51.9625
    hass.config.longitude = 7.6256
    result = await _start_menu(hass, "estimate")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RADIUS_KM: 5.0, CONF_MAX_STATIONS: 5}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MODE] == MODE_ESTIMATE
    assert result["data"]["latitude"] == 51.9625
    assert result["data"]["longitude"] == 7.6256


async def test_estimate_no_stations_in_radius(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_stations(aioclient_mock)
    hass.config.latitude = 0.0
    hass.config.longitude = 0.0
    result = await _start_menu(hass, "estimate")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RADIUS_KM: 0.5, CONF_MAX_STATIONS: 5}
    )
    assert result["errors"]["base"] == "no_stations_in_radius"


async def test_estimate_one_station_in_radius_is_sufficient(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(
        API_URL,
        params=STATION_PARAMS,
        text="device_id;description;latitude;longitude\n1;Solo;51.9625;7.6256\n",
    )
    hass.config.latitude = 51.9625
    hass.config.longitude = 7.6256
    result = await _start_menu(hass, "estimate")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RADIUS_KM: 5.0, CONF_MAX_STATIONS: 5}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_estimate_metadata_api_error(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, exc=TimeoutError())
    result = await _start_menu(hass, "estimate")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RADIUS_KM: 5.0, CONF_MAX_STATIONS: 5}
    )
    assert result["errors"]["base"] == "cannot_connect"


async def test_estimate_only_one_entry_allowed(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_stations(aioclient_mock)
    hass.config.latitude = 51.9625
    hass.config.longitude = 7.6256
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="local_estimate",
        data={CONF_MODE: MODE_ESTIMATE, CONF_RADIUS_KM: 5.0, CONF_MAX_STATIONS: 5},
    ).add_to_hass(hass)

    result = await _start_menu(hass, "estimate")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RADIUS_KM: 5.0, CONF_MAX_STATIONS: 5}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_estimate_unexpected_error_is_reported_as_unknown(
    hass: HomeAssistant, monkeypatch
) -> None:
    from custom_components.muenster_weather.api import MuensterWeatherClient

    async def _boom(self):
        raise RuntimeError("unexpected bug")

    monkeypatch.setattr(MuensterWeatherClient, "async_get_stations", _boom)
    result = await _start_menu(hass, "estimate")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RADIUS_KM: 5.0, CONF_MAX_STATIONS: 5}
    )
    assert result["errors"]["base"] == "unknown"


async def test_station_step_unexpected_error_is_reported_as_unknown(
    hass: HomeAssistant, monkeypatch
) -> None:
    from custom_components.muenster_weather.api import MuensterWeatherClient

    async def _boom(self):
        raise RuntimeError("unexpected bug")

    monkeypatch.setattr(MuensterWeatherClient, "async_get_stations", _boom)
    result = await _start_menu(hass, "station")
    assert result["errors"]["base"] == "unknown"


async def test_station_removed_between_render_and_submit_is_unavailable(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A station present in the rendered dropdown may vanish before submit."""
    _mock_stations(aioclient_mock)
    result = await _start_menu(hass, "station")

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        API_URL,
        params=STATION_PARAMS,
        text="device_id;description;latitude;longitude\n50619;Zentrum;51.9625;7.6256\n",
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STATION_ID: "50618"}
    )
    assert result["errors"]["base"] == "station_unavailable"


async def test_estimate_recovers_after_temporary_failure(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, exc=TimeoutError())
    result = await _start_menu(hass, "estimate")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RADIUS_KM: 5.0, CONF_MAX_STATIONS: 5}
    )
    assert result["errors"]["base"] == "cannot_connect"

    aioclient_mock.clear_requests()
    _mock_stations(aioclient_mock)
    hass.config.latitude = 51.9625
    hass.config.longitude = 7.6256
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RADIUS_KM: 5.0, CONF_MAX_STATIONS: 5}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY


# --- Options flow --------------------------------------------------------


async def test_options_flow_updates_estimate_settings(
    hass: HomeAssistant, aioclient_mock
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="local_estimate",
        data={
            CONF_MODE: MODE_ESTIMATE,
            "latitude": 51.9625,
            "longitude": 7.6256,
            CONF_RADIUS_KM: 5.0,
            CONF_MAX_STATIONS: 5,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_RADIUS_KM: 8.0, CONF_MAX_STATIONS: 3}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_RADIUS_KM] == 8.0
    assert result["data"][CONF_MAX_STATIONS] == 3


async def test_options_flow_init_tolerates_read_only_config_entry_property(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Regression test: current Home Assistant exposes OptionsFlow.config_entry
    as a read-only property (no setter), resolved from self.handler. Older
    cores expose no such property at all. __init__ must not crash either way.
    """
    from homeassistant.config_entries import OptionsFlow as BaseOptionsFlow

    from custom_components.muenster_weather.config_flow import (
        MuensterWeatherOptionsFlow,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="local_estimate",
        data={CONF_MODE: MODE_ESTIMATE, CONF_RADIUS_KM: 5.0, CONF_MAX_STATIONS: 5},
    )
    monkeypatch.setattr(
        BaseOptionsFlow,
        "config_entry",
        property(lambda self: entry),
        raising=False,
    )

    flow = MuensterWeatherOptionsFlow(entry)
    assert flow.config_entry is entry


async def test_options_flow_unavailable_for_station_entries(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="station:50618",
        data={CONF_MODE: MODE_STATION, CONF_STATION_ID: "50618"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_options"
