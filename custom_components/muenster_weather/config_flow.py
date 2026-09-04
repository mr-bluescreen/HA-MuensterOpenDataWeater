"""Config flow for Münster Open Data Weather."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    MuensterWeatherApiError,
    MuensterWeatherClient,
    MuensterWeatherConnectionError,
    MuensterWeatherDataError,
)
from .const import (
    AUTOMATIC_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAX_STATIONS,
    CONF_MODE,
    CONF_RADIUS_KM,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DEFAULT_MAX_STATIONS,
    DEFAULT_RADIUS_KM,
    DOMAIN,
    MODE_AUTOMATIC,
    MODE_STATION,
)


class MuensterWeatherConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure a station or a location-based aggregate."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Offer the two supported calculation modes."""
        return self.async_show_menu(step_id="user", menu_options=["station", "automatic"])

    async def async_step_station(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure one explicit weather station."""
        errors: dict[str, str] = {}
        try:
            stations = await self._client().async_get_stations()
            options = {station.station_id: station.name for station in stations}
        except MuensterWeatherConnectionError:
            errors["base"] = "cannot_connect"
            options = {}
        except MuensterWeatherDataError:
            errors["base"] = "invalid_data"
            options = {}

        if user_input is not None and not errors:
            station_id = user_input[CONF_STATION_ID]
            await self.async_set_unique_id(station_id)
            self._abort_if_unique_id_configured()
            station = next((item for item in stations if item.station_id == station_id), None)
            if station:
                return self.async_create_entry(
                    title=station.name,
                    data={
                        CONF_MODE: MODE_STATION,
                        CONF_STATION_ID: station.station_id,
                        CONF_STATION_NAME: station.name,
                    },
                )
            errors["base"] = "station_unavailable"

        return self.async_show_form(
            step_id="station",
            data_schema=(
                vol.Schema({vol.Required(CONF_STATION_ID): vol.In(options)})
                if options
                else vol.Schema({})
            ),
            errors=errors,
        )

    async def async_step_automatic(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure an inverse-distance weighted local aggregate."""
        errors: dict[str, str] = {}
        latitude = self.hass.config.latitude
        longitude = self.hass.config.longitude
        if user_input is not None:
            try:
                await self._client().async_get_averaged_observation(
                    latitude,
                    longitude,
                    user_input[CONF_RADIUS_KM],
                    user_input[CONF_MAX_STATIONS],
                )
            except MuensterWeatherConnectionError:
                errors["base"] = "cannot_connect"
            except MuensterWeatherApiError:
                errors["base"] = "no_nearby_stations"
            else:
                await self.async_set_unique_id(AUTOMATIC_ID)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Lokaler Wetter-Mittelwert",
                    data={
                        CONF_MODE: MODE_AUTOMATIC,
                        CONF_STATION_ID: AUTOMATIC_ID,
                        CONF_STATION_NAME: "Lokaler Wetter-Mittelwert",
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                        **user_input,
                    },
                )
        return self.async_show_form(
            step_id="automatic",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): vol.All(
                        vol.Coerce(float), vol.Range(min=0.1, max=100)
                    ),
                    vol.Required(CONF_MAX_STATIONS, default=DEFAULT_MAX_STATIONS): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=20)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"latitude": str(latitude), "longitude": str(longitude)},
        )

    def _client(self) -> MuensterWeatherClient:
        return MuensterWeatherClient(async_get_clientsession(self.hass))
