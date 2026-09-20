"""Inverse-distance-weighting interpolation contract tests (spec item 50)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.muenster_weather.api import CurrentMeasurement, Station
from custom_components.muenster_weather.interpolation import (
    Contributor,
    distance_km,
    interpolate,
    select_contributors,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _measurement(
    station_id: str,
    temperature: float | None,
    humidity: float | None,
    *,
    heat_status: str | None = None,
    age_minutes: float = 0,
) -> CurrentMeasurement:
    return CurrentMeasurement(
        station_id,
        NOW - timedelta(minutes=age_minutes),
        temperature,
        humidity,
        heat_status,
        temperature is not None,
        humidity is not None,
    )


def _contributor(
    station_id: str,
    distance: float,
    temperature: float | None,
    humidity: float | None,
    **kwargs,
) -> Contributor:
    return Contributor(
        Station(station_id, station_id.upper(), 0, 0),
        _measurement(station_id, temperature, humidity, **kwargs),
        distance,
    )


def test_single_station_returns_its_own_value() -> None:
    result = interpolate([_contributor("a", 2.0, 15.0, 50.0)])
    assert result.temperature == 15.0
    assert result.humidity == 50.0


def test_two_equal_distance_stations_are_weighted_equally() -> None:
    result = interpolate(
        [_contributor("a", 1.0, 10.0, 40.0), _contributor("b", 1.0, 20.0, 60.0)]
    )
    assert result.temperature == pytest.approx(15.0)
    assert result.humidity == pytest.approx(50.0)


def test_nearby_station_dominates_over_distant_station() -> None:
    result = interpolate(
        [_contributor("near", 0.2, 10.0, 40.0), _contributor("far", 4.0, 30.0, 80.0)]
    )
    # Closer to the near station's value than the midpoint (20.0/60.0).
    assert result.temperature < 15.0
    assert result.humidity < 55.0


def test_station_at_target_location_avoids_division_by_zero() -> None:
    result = interpolate(
        [_contributor("exact", 0.0, 12.3, 45.0), _contributor("far", 3.0, 99.0, 99.0)]
    )
    assert result.temperature == 12.3
    assert result.humidity == 45.0


def test_near_zero_distance_also_dominates() -> None:
    result = interpolate(
        [_contributor("near", 0.001, 12.3, 45.0), _contributor("far", 3.0, 99.0, 99.0)]
    )
    assert result.temperature == 12.3


def test_station_outside_radius_does_not_contribute(monkeypatch=None) -> None:
    stations = [
        Station("in", "In", 0.0, 0.0),
        Station("out", "Out", 1.0, 0.0),  # ~111 km away
    ]
    values = {
        "in": _measurement("in", 10.0, 40.0),
        "out": _measurement("out", 30.0, 90.0),
    }
    contributors = select_contributors(stations, values, 0.0, 0.0, 5.0, 5, NOW, timedelta(minutes=45))
    assert [c.station.station_id for c in contributors] == ["in"]


def test_null_measurement_does_not_contribute_to_that_field() -> None:
    result = interpolate(
        [_contributor("a", 1.0, 10.0, None), _contributor("b", 1.0, 20.0, 60.0)]
    )
    assert result.temperature == pytest.approx(15.0)
    assert result.humidity == 60.0


def test_invalid_quality_excluded_before_interpolation() -> None:
    stations = [Station("a", "A", 0.0, 0.0)]
    invalid = CurrentMeasurement("a", NOW, None, None, None, False, False)
    contributors = [Contributor(stations[0], invalid, 0.5)]
    result = interpolate(contributors)
    assert result.temperature is None
    assert result.humidity is None


def test_stale_measurement_is_excluded_by_selection() -> None:
    stations = [Station("a", "A", 0.0, 0.0)]
    values = {"a": _measurement("a", 20.0, 50.0, age_minutes=60)}
    contributors = select_contributors(stations, values, 0.0, 0.0, 5.0, 5, NOW, timedelta(minutes=45))
    assert contributors == ()


def test_all_values_invalid_result_is_unavailable() -> None:
    result = interpolate([])
    assert result.temperature is None
    assert result.humidity is None
    assert result.heat_status is None
    assert result.observed_at is None


def test_different_valid_station_sets_per_measurement() -> None:
    # "a" has temperature only, "b" has humidity only, "c" has both.
    contributors = [
        _contributor("a", 1.0, 10.0, None),
        _contributor("b", 1.0, None, 60.0),
        _contributor("c", 1.0, 30.0, 40.0),
    ]
    result = interpolate(contributors)
    assert {c.station.station_id for c in result.temperature_contributors} == {"a", "c"}
    assert {c.station.station_id for c in result.humidity_contributors} == {"b", "c"}


def test_maximum_station_count_limits_participants() -> None:
    stations = [Station(str(i), str(i), float(i) * 0.01, 0.0) for i in range(10)]
    values = {str(i): _measurement(str(i), float(i), float(i)) for i in range(10)}
    contributors = select_contributors(stations, values, 0.0, 0.0, 50.0, 3, NOW, timedelta(minutes=45))
    assert len(contributors) == 3
    assert [c.station.station_id for c in contributors] == ["0", "1", "2"]


def test_distance_km_coordinate_order_lat_lon_not_lon_lat() -> None:
    # Münster (51.9625, 7.6256) to Berlin (52.5200, 13.4050) is ~398 km, not the
    # much larger value you would get by swapping latitude and longitude.
    result = distance_km(51.9625, 7.6256, 52.5200, 13.4050)
    assert 380 < result < 420


def test_distance_km_zero_for_identical_points() -> None:
    assert distance_km(51.9625, 7.6256, 51.9625, 7.6256) == 0
