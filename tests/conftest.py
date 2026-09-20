"""Shared fixtures for the Münster Open Data Weather test suite."""

from __future__ import annotations

from collections.abc import Generator

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Make custom_components/muenster_weather loadable in every test."""
    yield
