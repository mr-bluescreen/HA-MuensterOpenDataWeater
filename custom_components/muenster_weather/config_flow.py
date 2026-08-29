"""Config flow for Münster Open Data Weather."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MuensterWeatherApiError, MuensterWeatherClient
from .const import CONF_STATION_ID, CONF_STATION_NAME, DOMAIN


class MuensterWeatherConfigFlow(ConfigFlow, domain=DOMAIN):
    """Let users select an advertised weather station."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            station_id = user_input[CONF_STATION_ID]
            await self.async_set_unique_id(station_id)
            self._abort_if_unique_id_configured()
            try:
                stations = await MuensterWeatherClient(
                    async_get_clientsession(self.hass)
                ).async_get_stations()
            except MuensterWeatherApiError:
                errors["base"] = "cannot_connect"
            else:
                station = next((item for item in stations if item.station_id == station_id), None)
                if station:
                    return self.async_create_entry(
                        title=station.name,
                        data={CONF_STATION_ID: station.station_id, CONF_STATION_NAME: station.name},
                    )
                errors["base"] = "station_unavailable"
        try:
            stations = await MuensterWeatherClient(async_get_clientsession(self.hass)).async_get_stations()
            options = {station.station_id: station.name for station in stations}
        except MuensterWeatherApiError:
            if not errors:
                errors["base"] = "cannot_connect"
            options = {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_STATION_ID): vol.In(options)}),
            errors=errors,
        )
