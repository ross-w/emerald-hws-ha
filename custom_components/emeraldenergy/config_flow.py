"""Config flow for Emerald Hot Water System integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from emerald_hws import EmeraldApiError, EmeraldAuthError, EmeraldConnectionError

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_CONNECTION_TIMEOUT,
    CONF_HEALTH_CHECK,
    CONF_ENABLE_ENERGY_MONITORING,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_HEALTH_CHECK,
    DEFAULT_ENABLE_ENERGY_MONITORING,
)
from .helpers import create_hws

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


def _login(config: Mapping[str, Any]) -> None:
    """Build an EmeraldHWS client and check the credentials are accepted.

    Blocking, and both halves reach into awsiotsdk/awscrt, so they run as a single
    executor job rather than two. getLoginToken returns True or raises.
    """
    create_hws(config).getLoginToken()


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    try:
        await hass.async_add_executor_job(_login, data)
    except EmeraldAuthError as err:
        # Caught before EmeraldApiError, which it subclasses.
        raise InvalidAuth from err
    except (EmeraldApiError, EmeraldConnectionError, TimeoutError) as err:
        # TimeoutError covers EmeraldTimeoutError, which derives from it rather
        # than from the two above. The steps below turn CannotConnect into a form
        # error without logging, so this is the only record of the cause.
        _LOGGER.debug("Could not reach the Emerald API: %s", err)
        raise CannotConnect from err

    # Return info that you want to store in the config entry.
    return {"title": "Emerald HWS"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Emerald Hot Water System."""

    # Bumped for the DEFAULT_HEALTH_CHECK 60->10 migration in __init__.py's
    # async_migrate_entry. Bump again (and add a version==2 branch there)
    # for the next entry-data migration.
    VERSION = 2

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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguring an existing entry, e.g. after a password change.

        Setup retries a refused sign-in rather than raising ConfigEntryAuthFailed,
        so nothing prompts the user to come here; the retry message names it.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_USERNAME] != entry.data[CONF_USERNAME]:
                # Any valid Emerald account signs in, so without this the entry
                # would quietly re-point at a different one and orphan every
                # entity built from the old account's uuids.
                errors[CONF_USERNAME] = "account_mismatch"
            else:
                try:
                    await validate_input(self.hass, user_input)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates=user_input
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA,
                # Everything but the password: that is either still correct, or
                # the reason they are here.
                {k: v for k, v in entry.data.items() if k != CONF_PASSWORD},
            ),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
