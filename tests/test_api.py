"""Tests for the portal data normalisation."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock

# Load the transport module without importing optional runtime dependencies.
aiohttp = types.ModuleType("aiohttp")
aiohttp.ClientError = type("ClientError", (Exception,), {})
aiohttp.ClientSession = type("ClientSession", (), {})
sys.modules["aiohttp"] = aiohttp

# Load the transport module without importing the Home Assistant-dependent package root.
PACKAGE = "custom_components.muenster_weather"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).parents[1] / "custom_components/muenster_weather")]
sys.modules[PACKAGE] = package
for module_name in ("const", "api"):
    path = Path(package.__path__[0]) / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{module_name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
MuensterWeatherClient = sys.modules[f"{PACKAGE}.api"].MuensterWeatherClient


class TestApi(unittest.IsolatedAsyncioTestCase):
    async def test_stations_are_deduplicated_and_sorted(self):
        client = MuensterWeatherClient(None)
        client._rows = AsyncMock(return_value=[
            {"Station": "2", "Standort": "Zentrum"},
            {"Station": "1", "Standort": "Aasee"},
            {"Station": "1", "Standort": "Aasee"},
        ])
        stations = await client.async_get_stations()
        self.assertEqual([station.station_id for station in stations], ["1", "2"])

    async def test_latest_observation_is_normalised(self):
        client = MuensterWeatherClient(None)
        client._rows = AsyncMock(return_value=[
            {"Station": "1", "Temperatur": "18,4"},
            {"Station": "1", "Temperatur": "19,5", "Luftfeuchtigkeit": "72", "Luftdruck": "1012.3"},
        ])
        observation = await client.async_get_observation("1")
        self.assertEqual(observation["temperature"], 19.5)
        self.assertEqual(observation["humidity"], 72)
        self.assertEqual(observation["pressure"], 1012.3)
        self.assertIsNone(observation["wind_speed"])
