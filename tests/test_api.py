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
MuensterWeatherDataError = sys.modules[f"{PACKAGE}.api"].MuensterWeatherDataError
STATIONS_URL = sys.modules[f"{PACKAGE}.const"].STATIONS_URL


class TestApi(unittest.IsolatedAsyncioTestCase):
    async def test_station_registry_uses_dedicated_wfs_csv(self):
        client = MuensterWeatherClient(None)
        client._request = AsyncMock(
            return_value="Station;Standort\n1;Aasee\n",
        )

        stations = await client.async_get_stations()

        self.assertEqual([station.station_id for station in stations], ["1"])
        client._request.assert_awaited_once_with(STATIONS_URL)

    async def test_station_registry_accepts_punctuated_wfs_headers(self):
        client = MuensterWeatherClient(None)
        client._request = AsyncMock(
            return_value=(
                "Stations-ID;Bezeichnung;Breitengrad;Längengrad\n"
                "17;Coerde;51,99;7,64\n"
            )
        )

        stations = await client.async_get_stations()

        self.assertEqual(stations[0].station_id, "17")
        self.assertEqual(stations[0].name, "Coerde")
        self.assertEqual(stations[0].latitude, 51.99)
        self.assertEqual(stations[0].longitude, 7.64)

    async def test_resource_list_response_exposes_resources(self):
        client = MuensterWeatherClient(None)
        client._request = AsyncMock(
            return_value={
                "result": [
                    {"format": "CSV", "url": "https://example.test/weather.csv"},
                    "invalid resource",
                ]
            }
        )

        urls = await client._resource_urls()

        self.assertEqual(urls, ["https://example.test/weather.csv"])

    async def test_invalid_metadata_raises_data_error(self):
        client = MuensterWeatherClient(None)
        client._request = AsyncMock(return_value={"result": "invalid"})

        with self.assertRaises(MuensterWeatherDataError):
            await client._resource_urls()

    async def test_broken_latest_resource_falls_back_to_previous_resource(self):
        client = MuensterWeatherClient(None)
        client._request = AsyncMock(side_effect=[
            {
                "result": {
                    "resources": [
                        {"format": "CSV", "url": "https://example.test/working.csv"},
                        {"format": "CSV", "url": "https://example.test/broken.csv"},
                    ]
                }
            },
            "failed to download zipball",
            "Station;Standort;Temperatur\n1;Aasee;19,5\n",
        ])

        rows = await client._rows()

        self.assertEqual(rows[0]["Station"], "1")
        self.assertEqual(client._data_url, "https://example.test/working.csv")
        self.assertEqual(client._request.await_count, 3)

    async def test_stations_are_deduplicated_and_sorted(self):
        client = MuensterWeatherClient(None)
        client._rows_from_url = AsyncMock(return_value=[
            {"Station": "2", "Standort": "Zentrum"},
            {"Station": "1", "Standort": "Aasee"},
            {"Station": "1", "Standort": "Aasee"},
        ])
        stations = await client.async_get_stations()
        self.assertEqual([station.station_id for station in stations], ["1", "2"])

    async def test_surplus_csv_columns_do_not_break_station_loading(self):
        client = MuensterWeatherClient(None)
        client._rows_from_url = AsyncMock(return_value=[
            {"Station": "1", "Standort": "Aasee", None: ["unexpected"]}
        ])

        stations = await client.async_get_stations()

        self.assertEqual(stations[0].station_id, "1")
        self.assertEqual(stations[0].name, "Aasee")

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

    async def test_distance_weighted_average_uses_nearby_stations(self):
        client = MuensterWeatherClient(None)
        client._rows = AsyncMock(return_value=[
            {"Station": "near", "Standort": "Nah", "Breitengrad": "51,9600", "Längengrad": "7,6300", "Temperatur": "10", "Windrichtung": "350"},
            {"Station": "far", "Standort": "Fern", "Breitengrad": "51,9600", "Längengrad": "7,6600", "Temperatur": "20", "Windrichtung": "10"},
            {"Station": "outside", "Breitengrad": "52,1000", "Längengrad": "7,6300", "Temperatur": "99"},
        ])

        observation = await client.async_get_averaged_observation(51.96, 7.63, 5, 2)

        self.assertLess(observation["temperature"], 11)
        self.assertTrue(observation["wind_bearing"] < 10 or observation["wind_bearing"] > 350)
        self.assertEqual([item["station_id"] for item in observation["stations"]], ["near", "far"])

    async def test_average_limits_number_of_stations(self):
        client = MuensterWeatherClient(None)
        client._rows = AsyncMock(return_value=[
            {"Station": "one", "lat": "51.96", "lon": "7.63", "Temperatur": "12"},
            {"Station": "two", "lat": "51.97", "lon": "7.63", "Temperatur": "24"},
        ])

        observation = await client.async_get_averaged_observation(51.96, 7.63, 10, 1)

        self.assertEqual(observation["temperature"], 12)
        self.assertEqual(len(observation["stations"]), 1)
