"""The Emerald Hot Water System integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import partial
from typing import Any

from emerald_hws import EmeraldAuthError
from emerald_hws.emeraldhws import EmeraldHWS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import dispatcher_send

from .const import CONF_USERNAME, DOMAIN
from .helpers import create_hws, is_awscrt_straddle_error, signal_update

_LOGGER = logging.getLogger(__name__)

# TODO List the platforms that you want to support.
# For your initial PR, limit it to 1 platform.
PLATFORMS: list[Platform] = [Platform.WATER_HEATER, Platform.SENSOR]


def _auth_issue_id(entry: ConfigEntry) -> str:
    """Return the repair issue id for a rejected sign-in on this entry."""
    return f"auth_failed_{entry.entry_id}"


def _create_and_connect(config: Mapping[str, Any]) -> EmeraldHWS:
    """Build an EmeraldHWS client and open its connection.

    Blocking, and both halves reach into awsiotsdk/awscrt, so they run as a single
    executor job rather than two.
    """
    instance = create_hws(config)
    instance.connect()
    return instance


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Emerald Hot Water System from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create and store the EmeraldHWS instance for shared access
    try:
        emerald_hws_instance = await hass.async_add_executor_job(
            _create_and_connect, entry.data
        )
    except EmeraldAuthError as err:
        # Retried, not failed permanently: Emerald has refused sign-in during
        # outages with valid credentials, and ConfigEntryAuthFailed would stop the
        # entry and ask every affected user for new credentials each time that
        # happened. A repair issue gets the user's attention without giving up on
        # the retry, and is cleared again by the next successful setup.
        ir.async_create_issue(
            hass,
            DOMAIN,
            _auth_issue_id(entry),
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="auth_failed",
            translation_placeholders={
                "account": entry.data.get(CONF_USERNAME, ""),
                "error": str(err),
            },
        )
        raise ConfigEntryNotReady(
            f"Emerald refused the stored credentials ({err}). This is usually a "
            "temporary problem at their end and setup will keep retrying; if you "
            "have changed your Emerald password, update it with Reconfigure on "
            "the integration."
        ) from err
    except Exception as err:
        # emerald_hws raises bare Exceptions, and its awsiotsdk/awscrt stack can fail
        # in ways only the traceback identifies, so log the full trace rather than
        # just the message.
        _LOGGER.exception("Failed to create Emerald HWS API instance")
        if is_awscrt_straddle_error(err):
            # Unrecoverable until Home Assistant restarts, so fail permanently
            # with the remedy rather than looping. See is_awscrt_straddle_error.
            raise ConfigEntryError(
                "The installed awscrt package is a mix of two versions, so the "
                "connection to the Emerald cloud cannot be established in this "
                "Home Assistant process. Restart Home Assistant to clear it. See "
                "the integration README section 'Errors mentioning awscrt during "
                f"setup' if it persists. Underlying error: {err}"
            ) from err
        # Anything else is assumed transient, so let HA retry with backoff.
        raise ConfigEntryNotReady(
            f"Failed to connect to the Emerald cloud: {err}"
        ) from err

    # Sign-in demonstrably works, so clear a rejection raised by an earlier attempt:
    # an Emerald-side outage resolves itself without the user touching anything.
    ir.async_delete_issue(hass, DOMAIN, _auth_issue_id(entry))

    # Past this point the instance holds a live MQTT connection with its own threads
    # and timers, so anything that fails has to hand it back before HA retries setup.
    try:
        # dispatcher_send is hass.loop.call_soon_threadsafe(...) under the hood,
        # so it's safe to call from the emerald_hws MQTT thread; delivery to
        # entities' @callback listeners then runs inline on the event loop.
        emerald_hws_instance.replaceCallback(
            partial(dispatcher_send, hass, signal_update(entry.entry_id))
        )

        # Store the instance for platforms to access
        hass.data[DOMAIN][entry.entry_id] = {"instance": emerald_hws_instance}
        _LOGGER.info("Emerald HWS API instance created and stored")

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        # BaseException, not Exception: HA cancels in-flight setup tasks on shutdown
        # and when a reload races setup, and CancelledError would otherwise skip the
        # disconnect below and strand the MQTT threads. Nothing is swallowed -- the
        # bare raise at the end re-raises whatever arrived, cancellation included.
        _LOGGER.warning(
            "Emerald HWS setup did not complete after the connection was "
            "established; disconnecting so nothing is left holding MQTT threads"
        )
        # Nothing in this block may raise: hass.data[DOMAIN] is set up above, but a
        # subscript here would mask the real failure if that ever stopped holding.
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        try:
            # The executor job is submitted as soon as this is called, so disconnect
            # still runs on its thread even if cancellation interrupts the await.
            await hass.async_add_executor_job(emerald_hws_instance.disconnect)
        except Exception:
            # Cleanup must never replace the failure that triggered it, so this is
            # logged and swallowed; the bare raise below re-raises the real cause.
            _LOGGER.exception(
                "Failed to disconnect the Emerald HWS instance during cleanup"
            )
        raise

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up state that outlives the config entry.

    Called even for an entry that never loaded, which is exactly the one that may
    have left a repair issue behind.
    """
    ir.async_delete_issue(hass, DOMAIN, _auth_issue_id(entry))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Clean up stored EmeraldHWS instance and stop MQTT/timers
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if entry_data:
            instance = entry_data["instance"]
            await hass.async_add_executor_job(instance.disconnect)

    return unload_ok
