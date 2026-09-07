"""Config-flow regressions with lightweight Home Assistant protocol doubles."""

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).parents[1] / "custom_components/muenster_weather"

vol = types.ModuleType("voluptuous")
vol.Schema = lambda value: value
vol.Required = lambda value, **kwargs: value
sys.modules["voluptuous"] = vol

ha = types.ModuleType("homeassistant")
entries = types.ModuleType("homeassistant.config_entries")


class _Flow:
    def __init_subclass__(cls, **kwargs):
        return super().__init_subclass__()

    def async_show_menu(self, **kwargs):
        return {"type": "menu", **kwargs}

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    async def async_set_unique_id(self, value):
        self.unique_id = value

    def _abort_if_unique_id_configured(self):
        return None

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}


entries.ConfigFlow = entries.OptionsFlow = _Flow
entries.ConfigFlowResult = dict
helpers = types.ModuleType("homeassistant.helpers")
aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
aiohttp_client.async_get_clientsession = lambda hass: hass.session
selector = types.ModuleType("homeassistant.helpers.selector")


class _Config:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Selector:
    def __init__(self, config):
        self.config = config


selector.NumberSelector = selector.SelectSelector = _Selector
selector.NumberSelectorConfig = selector.SelectSelectorConfig = _Config
selector.SelectOptionDict = lambda **kwargs: kwargs
sys.modules.update(
    {
        "homeassistant": ha,
        "homeassistant.config_entries": entries,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.helpers.selector": selector,
    }
)

pkg_name = "custom_components.muenster_weather"
pkg = sys.modules.get(pkg_name) or types.ModuleType(pkg_name)
pkg.__path__ = [str(ROOT)]
sys.modules[pkg_name] = pkg
for name in ("const", "api", "interpolation", "config_flow"):
    full_name = f"{pkg_name}.{name}"
    if name == "config_flow":
        sys.modules.pop(full_name, None)
    if full_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(full_name, ROOT / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)

api = sys.modules[f"{pkg_name}.api"]
flow_module = sys.modules[f"{pkg_name}.config_flow"]
const = sys.modules[f"{pkg_name}.const"]


class _Hass:
    session = object()
    config = types.SimpleNamespace(latitude=51.962, longitude=7.626)


class ConfigFlowRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.flow = flow_module.MuensterWeatherConfigFlow()
        self.flow.hass = _Hass()

    async def test_individual_mode_displays_real_station_options_and_creates_entry(self):
        stations = [api.Station("50618", "Zentrum", 51.962, 7.626)]
        self.flow._stations = AsyncMock(return_value=stations)

        result = await self.flow.async_step_station()
        station_selector = result["data_schema"][const.CONF_STATION_ID]
        self.assertEqual(
            station_selector.config.options,
            [{"value": "50618", "label": "Zentrum (50618)"}],
        )

        result = await self.flow.async_step_station({const.CONF_STATION_ID: "50618"})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"][const.CONF_STATION_ID], "50618")

    async def test_estimate_submit_validates_current_measurements_and_creates_entry(self):
        station = api.Station("50618", "Zentrum", 51.962, 7.626)
        measurement = api.Measurement(
            "50618", datetime.now(UTC), 20.4, 61.0, None, True, True
        )
        self.flow._stations = AsyncMock(return_value=[station])
        client = types.SimpleNamespace(
            async_get_latest=AsyncMock(return_value={"50618": measurement})
        )
        flow_module.MuensterWeatherClient = lambda session: client

        result = await self.flow.async_step_estimate(
            {const.CONF_RADIUS_KM: 5.0, const.CONF_MAX_STATIONS: 5}
        )
        self.assertEqual(result["type"], "create_entry")
        client.async_get_latest.assert_awaited_once_with(["50618"])

    async def test_estimate_errors_are_distinct(self):
        self.flow._stations = AsyncMock(return_value=[api.Station("far", "Far", 0, 0)])
        result = await self.flow.async_step_estimate(
            {const.CONF_RADIUS_KM: 0.5, const.CONF_MAX_STATIONS: 1}
        )
        self.assertEqual(result["errors"]["base"], "no_nearby_stations")

        for exception, expected in (
            (api.MuensterWeatherConnectionError(), "cannot_connect"),
            (api.MuensterWeatherResponseError(), "invalid_data"),
        ):
            self.flow._stations = AsyncMock(side_effect=exception)
            result = await self.flow.async_step_estimate(
                {const.CONF_RADIUS_KM: 5.0, const.CONF_MAX_STATIONS: 1}
            )
            self.assertEqual(result["errors"]["base"], expected)

        station = api.Station("50618", "Zentrum", 51.962, 7.626)
        self.flow._stations = AsyncMock(return_value=[station])
        client = types.SimpleNamespace(
            async_get_latest=AsyncMock(
                side_effect=api.MuensterWeatherConnectionError()
            )
        )
        flow_module.MuensterWeatherClient = lambda session: client
        result = await self.flow.async_step_estimate(
            {const.CONF_RADIUS_KM: 5.0, const.CONF_MAX_STATIONS: 1}
        )
        self.assertEqual(result["errors"]["base"], "cannot_connect")
