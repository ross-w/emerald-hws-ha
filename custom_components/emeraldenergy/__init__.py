"""The Emerald Hot Water System integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from emerald_hws.emeraldhws import EmeraldHWS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .const import DOMAIN
from .helpers import create_hws, is_awscrt_straddle_error

_LOGGER = logging.getLogger(__name__)

# TODO List the platforms that you want to support.
# For your initial PR, limit it to 1 platform.
PLATFORMS: list[Platform] = [Platform.WATER_HEATER, Platform.SENSOR]


class CallbackDispatcher:
    """Dispatcher to handle multiple callbacks for the same Emerald HWS instance."""

    def __init__(self):
        """Initialize the callback dispatcher."""
        self._callbacks = []

    def register_callback(self, callback):
        """Register a callback function."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)
            _LOGGER.debug(
                f"Registered callback. Total callbacks: {len(self._callbacks)}"
            )

    def unregister_callback(self, callback):
        """Unregister a callback function."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            _LOGGER.debug(
                f"Unregistered callback. Total callbacks: {len(self._callbacks)}"
            )

    def dispatch(self):
        """Dispatch the callback to all registered listeners."""
        _LOGGER.debug(f"Dispatching callback to {len(self._callbacks)} listeners")
        for callback in self._callbacks:
            try:
                callback()
            except Exception:
                _LOGGER.exception("Error in callback %r", callback)

    def __call__(self):
        """Make the dispatcher callable."""
        self.dispatch()


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

    # Past this point the instance holds a live MQTT connection with its own threads
    # and timers, so anything that fails has to hand it back before HA retries setup.
    try:
        # Create and store callback dispatcher for this instance
        callback_dispatcher = CallbackDispatcher()
        emerald_hws_instance.replaceCallback(callback_dispatcher)

        # Store both the instance and dispatcher for platforms to access
        hass.data[DOMAIN][entry.entry_id] = {
            "instance": emerald_hws_instance,
            "dispatcher": callback_dispatcher,
        }
        _LOGGER.info(
            "Emerald HWS API instance and callback dispatcher created and stored"
        )

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await hass.async_add_executor_job(emerald_hws_instance.disconnect)
        raise

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Clean up stored EmeraldHWS instance and stop MQTT/timers
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if entry_data:
            instance = entry_data["instance"]
            await hass.async_add_executor_job(instance.disconnect)

    return unload_ok
