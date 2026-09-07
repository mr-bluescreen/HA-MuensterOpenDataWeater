"""Parser contract tests using captured representative WFS shapes."""

from datetime import UTC
import importlib.util
from pathlib import Path
import sys
import types
import pytest

aiohttp = types.ModuleType("aiohttp")
for n in ("ClientError", "ClientResponseError"):
    setattr(aiohttp, n, type(n, (Exception,), {}))
aiohttp.ClientSession = type("ClientSession", (), {})
sys.modules["aiohttp"] = aiohttp
pkg = types.ModuleType("custom_components.muenster_weather")
pkg.__path__ = [str(Path(__file__).parents[1] / "custom_components/muenster_weather")]
sys.modules[pkg.__name__] = pkg
for name in ("const", "api", "interpolation"):
    spec = importlib.util.spec_from_file_location(
        f"{pkg.__name__}.{name}", Path(pkg.__path__[0]) / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
api = sys.modules[f"{pkg.__name__}.api"]
geo = sys.modules[f"{pkg.__name__}.interpolation"]


def test_geojson_coordinate_order_and_station_sorting():
    stations = api.parse_stations(
        {
            "features": [
                {
                    "properties": {"device_id": 50618, "name": "Zentrum"},
                    "geometry": {"coordinates": [7.626, 51.962]},
                },
                {
                    "properties": {
                        "device_id": "2",
                        "name": "Aasee",
                        "latitude": 51.95,
                        "longitude": 7.61,
                    }
                },
            ]
        }
    )
    assert stations[0].name == "Aasee"
    assert stations[1].latitude == 51.962
    assert stations[1].longitude == 7.626


def test_invalid_station_payloads():
    with pytest.raises(api.MuensterWeatherResponseError):
        api.parse_stations({"type": "FeatureCollection"})
    with pytest.raises(api.MuensterWeatherResponseError):
        api.parse_stations({"features": [{"properties": {"name": "missing id"}}]})


def test_measurement_quality_null_range_timezone_and_newest():
    payload = [
        {
            "device_id": "1",
            "timestamp": "2026-08-01T12:00:00+02:00",
            "temperature": 19,
            "humidity": 101,
        },
        {
            "device_id": "1",
            "timestamp": "2026-08-01T12:15:00+02:00",
            "temperature": 20.5,
            "humidity": 55,
            "temperature_quality": "bad",
            "humidity_quality": 0,
            "heat_notification": "none",
        },
        {
            "device_id": "2",
            "timestamp": "2026-01-01T12:00:00",
            "temperature": None,
            "humidity": "x",
        },
    ]
    values = api.parse_measurements(payload)
    assert values["1"].temperature is None and values["1"].humidity == 55
    assert values["1"].observed_at.tzinfo is UTC and values["1"].observed_at.hour == 10
    assert values["2"].observed_at.hour == 11 and values["2"].humidity is None


def test_malformed_measurements():
    with pytest.raises(api.MuensterWeatherResponseError):
        api.parse_measurements({"error": "bad"})
    with pytest.raises(api.MuensterWeatherResponseError):
        api.parse_measurements([{"device_id": "1", "timestamp": "not-a-time"}])


def measurement(i, temp, humidity, minute=0):
    from datetime import datetime

    return api.Measurement(
        i,
        datetime(2026, 1, 1, 12, minute, tzinfo=UTC),
        temp,
        humidity,
        None,
        True,
        True,
    )


def test_distance_zero_and_known_pair():
    assert geo.distance_km(51.96, 7.63, 51.96, 7.63) == 0
    assert geo.distance_km(51.96, 7.63, 52.96, 7.63) == pytest.approx(111.2, rel=0.01)


def test_selection_radius_stale_and_limit():
    from datetime import datetime, timedelta

    stations = [
        api.Station("a", "A", 51.96, 7.63),
        api.Station("b", "B", 51.97, 7.63),
        api.Station("old", "Old", 51.96, 7.63),
    ]
    values = {
        "a": measurement("a", 10, 40),
        "b": measurement("b", 20, 60, minute=15),
        "old": measurement("old", 99, 99, minute=0),
    }
    selected = geo.select_contributors(
        stations,
        values,
        51.96,
        7.63,
        2,
        2,
        datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
        timedelta(minutes=20),
    )
    assert [x.station.station_id for x in selected] == ["b"]


def test_interpolation_exact_equal_weight_and_partial_fields():
    a = geo.Contributor(api.Station("a", "A", 0, 0), measurement("a", 10, None), 1)
    b = geo.Contributor(api.Station("b", "B", 0, 0), measurement("b", 20, 60), 1)
    result = geo.interpolate([a, b])
    assert result.temperature == 15
    assert result.humidity == 60
    exact = geo.Contributor(api.Station("x", "X", 0, 0), measurement("x", 7, 44), 0)
    assert geo.interpolate([exact, b]).temperature == 7


def test_idw_near_station_dominates_and_empty_unavailable():
    near = geo.Contributor(api.Station("n", "N", 0, 0), measurement("n", 10, 40), 0.1)
    far = geo.Contributor(api.Station("f", "F", 0, 0), measurement("f", 30, 80), 2)
    assert geo.interpolate([near, far]).temperature < 10.1
    result = geo.interpolate([])
    assert result.temperature is None and result.humidity is None
