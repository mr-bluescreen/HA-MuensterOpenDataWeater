"""Config and options flows for Münster Open Data Weather."""

from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import (
    MuensterWeatherClient,
    MuensterWeatherConnectionError,
    MuensterWeatherError,
    Station,
)
from .const import (
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
    MODE_ESTIMATE,
    MODE_STATION,
)
from .interpolation import distance_km


class MuensterWeatherConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Configure an individual station or local estimate."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="user", menu_options=["station", "estimate"]
        )

    async def _stations(self) -> list[Station]:
        return await MuensterWeatherClient(
            async_get_clientsession(self.hass)
        ).async_get_stations()

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        try:
            stations = await self._stations()
        except MuensterWeatherConnectionError:
            errors["base"] = "cannot_connect"
            stations = []
        except MuensterWeatherError:
            errors["base"] = "invalid_data"
            stations = []
        if user_input is not None and not errors:
            station = next(
                (
                    item
                    for item in stations
                    if item.station_id == user_input[CONF_STATION_ID]
                ),
                None,
            )
            if station is None:
                errors["base"] = "station_unavailable"
            else:
                await self.async_set_unique_id(f"station:{station.station_id}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=station.name,
                    data={
                        CONF_MODE: MODE_STATION,
                        CONF_STATION_ID: station.station_id,
                        CONF_STATION_NAME: station.name,
                    },
                )
        selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(
                        value=item.station_id, label=f"{item.name} ({item.station_id})"
                    )
                    for item in stations
                ],
                sort=True,
            )
        )
        return self.async_show_form(
            step_id="station",
            data_schema=vol.Schema({vol.Required(CONF_STATION_ID): selector})
            if stations
            else vol.Schema({}),
            errors=errors,
        )

    async def async_step_estimate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        latitude, longitude = self.hass.config.latitude, self.hass.config.longitude
        if user_input is not None:
            try:
                stations = await self._stations()
                if not any(
                    distance_km(latitude, longitude, item.latitude, item.longitude)
                    <= user_input[CONF_RADIUS_KM]
                    for item in stations
                ):
                    errors["base"] = "no_nearby_stations"
            except MuensterWeatherConnectionError:
                errors["base"] = "cannot_connect"
            except MuensterWeatherError:
                errors["base"] = "invalid_data"
            if not errors:
                await self.async_set_unique_id("local_estimate")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Münster Local Weather Estimate",
                    data={
                        CONF_MODE: MODE_ESTIMATE,
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                        **user_input,
                    },
                )
        return self.async_show_form(
            step_id="estimate",
            data_schema=_estimate_schema(user_input),
            errors=errors,
            description_placeholders={
                "latitude": f"{latitude:.3f}",
                "longitude": f"{longitude:.3f}",
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return MuensterWeatherOptionsFlow()


class MuensterWeatherOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self.config_entry.data[CONF_MODE] != MODE_ESTIMATE:
            return self.async_abort(reason="no_options")
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        defaults = {
            CONF_RADIUS_KM: self.config_entry.options.get(
                CONF_RADIUS_KM, self.config_entry.data[CONF_RADIUS_KM]
            ),
            CONF_MAX_STATIONS: self.config_entry.options.get(
                CONF_MAX_STATIONS, self.config_entry.data[CONF_MAX_STATIONS]
            ),
        }
        return self.async_show_form(
            step_id="init", data_schema=_estimate_schema(defaults)
        )


def _estimate_schema(defaults: dict[str, Any] | None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_RADIUS_KM, default=defaults.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.5, max=25, step=0.5, unit_of_measurement="km", mode="slider"
                )
            ),
            vol.Required(
                CONF_MAX_STATIONS,
                default=defaults.get(CONF_MAX_STATIONS, DEFAULT_MAX_STATIONS),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=10, step=1, mode="slider")
            ),
        }
    )
