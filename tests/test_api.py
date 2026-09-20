"""Parser and client contract tests for the Münster WFS API layer."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.muenster_weather.api import (
    MuensterWeatherClient,
    MuensterWeatherConnectionError,
    MuensterWeatherNoStationsError,
    MuensterWeatherResponseError,
    parse_measurements,
    parse_stations,
)
from custom_components.muenster_weather.const import (
    API_URL,
    LATEST_PARAMS,
    STATION_PARAMS,
)

from .fixtures import LATEST_JSON, STATION_CSV

# --- Station parser --------------------------------------------------------


def test_valid_station_csv_multiple_stations() -> None:
    stations = parse_stations(STATION_CSV)
    assert [s.station_id for s in stations] == ["50618", "50620", "50619"]  # name-sorted
    aasee = next(s for s in stations if s.station_id == "50618")
    assert aasee.name == "Aasee"
    assert aasee.latitude == pytest.approx(51.9403)
    assert aasee.longitude == pytest.approx(7.6046)


def test_station_name_field_variants_are_recognised() -> None:
    stations = parse_stations(
        [
            {"device_id": "1", "device_name": "Via device_name", "latitude": 51.9, "longitude": 7.6},
            {"device_id": "2", "description": "Via description", "latitude": 51.9, "longitude": 7.6},
        ]
    )
    names = {s.station_id: s.name for s in stations}
    assert names == {"1": "Via device_name", "2": "Via description"}


def test_station_coordinate_ordering_geojson_vs_flat() -> None:
    """GeoJSON coordinates are [lon, lat]; flat lat/lon fields are lat, lon."""
    geojson = parse_stations(
        [{"properties": {"device_id": "1"}, "geometry": {"coordinates": [7.626, 51.962]}}]
    )[0]
    flat = parse_stations(
        [{"device_id": "2", "latitude": 51.962, "longitude": 7.626}]
    )[0]
    assert (geojson.latitude, geojson.longitude) == (51.962, 7.626)
    assert (flat.latitude, flat.longitude) == (51.962, 7.626)


def test_station_missing_optional_metadata_falls_back_to_id() -> None:
    stations = parse_stations([{"device_id": "42", "latitude": 51.9, "longitude": 7.6}])
    assert stations[0].name == "42"


def test_station_malformed_coordinates_are_skipped() -> None:
    stations = parse_stations(
        [
            {"device_id": "bad", "latitude": "not-a-number", "longitude": 7.6},
            {"device_id": "ok", "latitude": 51.9, "longitude": 7.6},
        ]
    )
    assert [s.station_id for s in stations] == ["ok"]


def test_station_malformed_individual_record_is_skipped_not_fatal() -> None:
    stations = parse_stations(
        [
            "not an object",
            {"device_id": "ok", "latitude": 51.9, "longitude": 7.6},
        ]
    )
    assert [s.station_id for s in stations] == ["ok"]


def test_station_duplicate_ids_resolve_to_one_station() -> None:
    stations = parse_stations(
        [
            {"device_id": "7", "description": "First", "latitude": 51.9, "longitude": 7.6},
            {"device_id": "7", "description": "Second", "latitude": 51.91, "longitude": 7.61},
        ]
    )
    assert len(stations) == 1
    assert stations[0].name == "Second"


def test_station_empty_response_raises_no_stations() -> None:
    with pytest.raises(MuensterWeatherNoStationsError):
        parse_stations([])
    with pytest.raises(MuensterWeatherNoStationsError):
        parse_stations("device_id;description;latitude;longitude\n")


def test_station_invalid_top_level_type_raises_response_error() -> None:
    with pytest.raises(MuensterWeatherResponseError):
        parse_stations({"type": "FeatureCollection"})


def test_station_id_is_normalised_to_string() -> None:
    stations = parse_stations([{"device_id": 50618, "latitude": 51.9, "longitude": 7.6}])
    assert stations[0].station_id == "50618"
    assert isinstance(stations[0].station_id, str)


# --- Measurement parser ------------------------------------------------------


def test_valid_measurement_response_one_station() -> None:
    values = parse_measurements([LATEST_JSON[0]])
    assert values["50618"].temperature == 21.3
    assert values["50618"].humidity == 58.0


def test_valid_measurement_response_multiple_stations() -> None:
    values = parse_measurements(LATEST_JSON)
    assert set(values) == {"50618", "50619"}


def test_measurement_station_id_normalisation_matches_station_id() -> None:
    station = parse_stations([{"device_id": "50618", "latitude": 51.9, "longitude": 7.6}])[0]
    measurement = parse_measurements([{**LATEST_JSON[0], "device_id": 50618}])["50618"]
    assert station.station_id == measurement.station_id


def test_measurement_timestamp_and_timezone_conversion() -> None:
    values = parse_measurements(
        [{"device_id": "1", "timestamp": "2026-09-07T09:30:00+02:00", "temperature": 20, "humidity": 50}]
    )
    assert values["1"].observed_at == datetime(2026, 9, 7, 7, 30, tzinfo=UTC)


def test_measurement_naive_timestamp_assumed_europe_berlin() -> None:
    values = parse_measurements(
        [{"device_id": "1", "timestamp": "2026-01-01T12:00:00", "temperature": 20, "humidity": 50}]
    )
    # CET is UTC+1 in January.
    assert values["1"].observed_at == datetime(2026, 1, 1, 11, 0, tzinfo=UTC)


def test_measurement_quality_flags_reject_invalid_values() -> None:
    values = parse_measurements(
        [
            {
                "device_id": "1",
                "timestamp": "2026-09-07T09:30:00+02:00",
                "temperature": 19,
                "temperature_quality": "bad",
                "humidity": 55,
                "humidity_quality": 0,
            }
        ]
    )
    assert values["1"].temperature is None
    assert values["1"].temperature_valid is False
    assert values["1"].humidity == 55
    assert values["1"].humidity_valid is True


def test_measurement_null_and_out_of_range_values_become_none() -> None:
    values = parse_measurements(
        [{"device_id": "1", "timestamp": "2026-01-01T00:00:00Z", "temperature": None, "humidity": 150}]
    )
    assert values["1"].temperature is None
    assert values["1"].humidity is None


def test_measurement_partially_valid_record_keeps_valid_field() -> None:
    values = parse_measurements(
        [{"device_id": "1", "timestamp": "2026-01-01T00:00:00Z", "temperature": 18, "humidity": "n/a"}]
    )
    assert values["1"].temperature == 18
    assert values["1"].humidity is None


def test_measurement_duplicate_station_keeps_newest_timestamp() -> None:
    values = parse_measurements(
        [
            {"device_id": "1", "timestamp": "2026-01-01T00:00:00Z", "temperature": 10, "humidity": 40},
            {"device_id": "1", "timestamp": "2026-01-01T00:15:00Z", "temperature": 12, "humidity": 42},
        ]
    )
    assert values["1"].temperature == 12


def test_measurement_malformed_record_raises_response_error() -> None:
    with pytest.raises(MuensterWeatherResponseError):
        parse_measurements([{"device_id": "1", "timestamp": "not-a-timestamp"}])


def test_measurement_empty_valid_response() -> None:
    assert parse_measurements([]) == {}


def test_measurement_unexpected_structure_raises_response_error() -> None:
    with pytest.raises(MuensterWeatherResponseError):
        parse_measurements({"error": "bad"})


def test_measurement_indexed_object_shape() -> None:
    values = parse_measurements(
        {
            "50618": {
                "timestamp": "2026-09-07T09:30:00+02:00",
                "air_temperature": 21.3,
                "relative_humidity": None,
            }
        }
    )
    assert values["50618"].temperature == 21.3
    assert values["50618"].humidity is None


# --- Client -------------------------------------------------------------


async def test_client_requests_station_master_data(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, text=STATION_CSV)
    client = MuensterWeatherClient(async_get_clientsession(hass))
    stations = await client.async_get_stations()
    assert len(stations) == 3


async def test_client_requests_filtered_current_measurements(
    hass: HomeAssistant, aioclient_mock
) -> None:
    params = dict(LATEST_PARAMS)
    params["device_ids"] = "50618"
    aioclient_mock.get(API_URL, params=params, json=[LATEST_JSON[0]])
    client = MuensterWeatherClient(async_get_clientsession(hass))
    values = await client.async_get_latest(["50618"])
    assert set(values) == {"50618"}


async def test_client_requests_multiple_station_ids_comma_joined(
    hass: HomeAssistant, aioclient_mock
) -> None:
    params = dict(LATEST_PARAMS)
    params["device_ids"] = "50618,50619"
    aioclient_mock.get(API_URL, params=params, json=LATEST_JSON)
    client = MuensterWeatherClient(async_get_clientsession(hass))
    values = await client.async_get_latest(["50618", "50619"])
    assert set(values) == {"50618", "50619"}


async def test_client_no_filter_requests_all_current_measurements(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(API_URL, params=LATEST_PARAMS, json=LATEST_JSON)
    client = MuensterWeatherClient(async_get_clientsession(hass))
    values = await client.async_get_latest([])
    assert set(values) == {"50618", "50619"}


async def test_client_connection_error_wraps_transport_failure(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(API_URL, params=STATION_PARAMS, exc=TimeoutError())
    client = MuensterWeatherClient(async_get_clientsession(hass))
    with pytest.raises(MuensterWeatherConnectionError):
        await client.async_get_stations()


async def test_client_http_error_status_raises_response_error(
    hass: HomeAssistant, aioclient_mock
) -> None:
    params = dict(LATEST_PARAMS)
    params["device_ids"] = "50618"
    aioclient_mock.get(
        API_URL,
        params=params,
        status=400,
        text="<ServiceExceptionReport>unknown parameter device_ids</ServiceExceptionReport>",
    )
    client = MuensterWeatherClient(async_get_clientsession(hass))
    with pytest.raises(MuensterWeatherResponseError):
        await client.async_get_latest(["50618"])


async def test_client_invalid_json_raises_response_error(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(
        API_URL,
        params=LATEST_PARAMS,
        text="not json",
        headers={"content-type": "application/json"},
    )
    client = MuensterWeatherClient(async_get_clientsession(hass))
    with pytest.raises(MuensterWeatherResponseError):
        await client.async_get_latest([])
