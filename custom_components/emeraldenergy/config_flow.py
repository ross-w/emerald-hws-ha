"""Config flow for Emerald Hot Water System integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from emerald_hws.emeraldhws import EmeraldHWS

from .const import (
    DOMAIN,
    CONF_CONNECTION_TIMEOUT,
    CONF_HEALTH_CHECK,
    CONF_ENABLE_ENERGY_MONITORING,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_HEALTH_CHECK,
    DEFAULT_ENABLE_ENERGY_MONITORING,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_CONNECTION_TIMEOUT, default=DEFAULT_CONNECTION_TIMEOUT): int,
        vol.Optional(CONF_HEALTH_CHECK, default=DEFAULT_HEALTH_CHECK): int,
        vol.Optional(
            CONF_ENABLE_ENERGY_MONITORING, default=DEFAULT_ENABLE_ENERGY_MONITORING
        ): bool,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # TODO validate the data can be used to set up a connection.

    # If your PyPI package is not built with async, pass your methods
    # to the executor:
    # await hass.async_add_executor_job(
    #     your_validate_func, data[CONF_USERNAME], data[CONF_PASSWORD]
    # )

    hws = EmeraldHWS(
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        connection_timeout_minutes=data.get(
            CONF_CONNECTION_TIMEOUT, DEFAULT_CONNECTION_TIMEOUT
        ),
        health_check_minutes=data.get(CONF_HEALTH_CHECK, DEFAULT_HEALTH_CHECK),
    )

    if not await hass.async_add_executor_job(hws.getLoginToken):
        raise InvalidAuth

    # If you cannot connect:
    # throw CannotConnect
    # If the authentication is wrong:
    # InvalidAuth

    # Return info that you want to store in the config entry.
    return {"title": "Emerald HWS"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Emerald Hot Water System."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
