"""Config flow for Emerald Hot Water System integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

import voluptuous as vol
from emerald_hws import EmeraldApiError, EmeraldAuthError, EmeraldConnectionError

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

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

_T = TypeVar("_T")

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


def _login_and_list_heat_pumps(config: Mapping[str, Any]) -> set[str]:
    """Sign in and return the ids of every heat pump the login can see.

    Own and shared properties alike. One executor job, like _login: getAllHWS signs
    in by itself on a fresh client, so the credentials are checked exactly once. It
    is a REST call only -- listHWS would open an MQTT connection just to answer this.
    """
    hws = create_hws(config)
    hws.getAllHWS()
    return {
        heat_pump["id"]
        for prop in hws.properties
        for heat_pump in prop.get("heat_pump", [])
    }


def _normalise_username(username: str) -> str:
    """Return a username in the form used to compare two of them.

    Comparison only: what is stored keeps the case the user typed, in case Emerald
    ever treats it as significant.
    """
    return username.strip().casefold()


def _known_heat_pumps(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> set[str]:
    """Return the ids of the heat pumps this entry has created devices for.

    Read from the device registry, which outlives a failed setup, so this still
    answers while the entry cannot sign in -- the usual reason to reconfigure.
    """
    registry = dr.async_get(hass)
    return {
        identifier
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
        for domain, identifier in device.identifiers
        if domain == DOMAIN
    }


async def _run_sign_in(
    hass: HomeAssistant,
    job: Callable[[Mapping[str, Any]], _T],
    data: Mapping[str, Any],
) -> _T:
    """Run a blocking sign-in job, turning the library's errors into the flow's."""
    try:
        return await hass.async_add_executor_job(job, data)
    except EmeraldAuthError as err:
        # Caught before EmeraldApiError, which it subclasses.
        raise InvalidAuth from err
    except (EmeraldApiError, EmeraldConnectionError, TimeoutError) as err:
        # TimeoutError covers EmeraldTimeoutError, which derives from it rather
        # than from the two above. The steps below turn CannotConnect into a form
        # error without logging, so this is the only record of the cause.
        _LOGGER.debug("Could not reach the Emerald API: %s", err)
        raise CannotConnect from err


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    await _run_sign_in(hass, _login, data)

    # Return info that you want to store in the config entry.
    return {"title": "Emerald HWS"}


async def list_heat_pumps(hass: HomeAssistant, data: dict[str, Any]) -> set[str]:
    """Sign in with the user input and return the heat pump ids the login can see.

    Raises InvalidAuth and CannotConnect exactly as validate_input does.
    """
    return await _run_sign_in(hass, _login_and_list_heat_pumps, data)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Emerald Hot Water System."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_USERNAME] = user_input[CONF_USERNAME].strip()
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

        Also takes a new username, for an Emerald account whose email address has
        changed, provided the new login still sees this entry's heat pumps.

        Setup retries a refused sign-in rather than raising ConfigEntryAuthFailed,
        so nothing prompts the user to come here; the retry message names it.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_USERNAME] = user_input[CONF_USERNAME].strip()
            username_changed = _normalise_username(
                user_input[CONF_USERNAME]
            ) != _normalise_username(entry.data[CONF_USERNAME])
            if username_changed and self._username_in_use(
                user_input[CONF_USERNAME], entry
            ):
                # Checked before signing in: there is no point asking Emerald about
                # a login that could not be saved anyway.
                errors[CONF_USERNAME] = "account_in_use"
            else:
                try:
                    if username_changed:
                        other_account = await self._is_other_account(entry, user_input)
                    else:
                        await validate_input(self.hass, user_input)
                        other_account = False
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    if other_account:
                        errors[CONF_USERNAME] = "account_mismatch"
                    else:
                        return self.async_update_reload_and_abort(
                            entry, data_updates=user_input
                        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA,
                # Everything but the password: that is either still correct, or
                # the reason they are here. After an error, what they just typed,
                # so a new email address isn't swapped back for the old one.
                {
                    k: v
                    for k, v in (user_input or entry.data).items()
                    if k != CONF_PASSWORD
                },
            ),
            errors=errors,
        )

    def _username_in_use(
        self, username: str, entry: config_entries.ConfigEntry
    ) -> bool:
        """Report whether another entry of this integration signs in as username.

        Only asked when the username is changing, so entries that already share an
        account keep working through a password-only reconfigure.
        """
        wanted = _normalise_username(username)
        return any(
            other.entry_id != entry.entry_id
            and _normalise_username(other.data.get(CONF_USERNAME, "")) == wanted
            for other in self._async_current_entries(include_ignore=False)
        )

    async def _is_other_account(
        self, entry: config_entries.ConfigEntry, user_input: dict[str, Any]
    ) -> bool:
        """Sign in with a changed username and report whether it is another account.

        Any valid Emerald account signs in, and Emerald exposes no account id, so a
        changed username is only accepted when the login still sees one of this
        entry's heat pumps. Otherwise the entry would quietly re-point at a different
        account and orphan every device and entity built from the old one's uuids.

        Any overlap rather than all of them: a unit since removed from the account is
        already a stale device and must not block an email change. An entry with no
        devices has nothing to orphan, so any login is accepted for it.

        Raises InvalidAuth and CannotConnect as validate_input does.
        """
        visible = await list_heat_pumps(self.hass, user_input)
        known = _known_heat_pumps(self.hass, entry)
        return bool(known) and known.isdisjoint(visible)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
