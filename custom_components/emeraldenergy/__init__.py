"""The Emerald Hot Water System integration."""

from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from emerald_hws.emeraldhws import EmeraldHWS

from .const import (
    DOMAIN,
    CONF_CONNECTION_TIMEOUT,
    CONF_HEALTH_CHECK,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_HEALTH_CHECK,
    CONF_USERNAME,
    CONF_PASSWORD,
)

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
            except Exception as e:
                _LOGGER.error(f"Error in callback: {e}")

    def __call__(self):
        """Make the dispatcher callable."""
        self.dispatch()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Emerald Hot Water System from a config entry."""
    config = entry.data
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    connection_timeout = config.get(CONF_CONNECTION_TIMEOUT, DEFAULT_CONNECTION_TIMEOUT)
    health_check = config.get(CONF_HEALTH_CHECK, DEFAULT_HEALTH_CHECK)

    hass.data.setdefault(DOMAIN, {})

    # Create and store the EmeraldHWS instance for shared access
    try:
        emerald_hws_instance = EmeraldHWS(
            username,
            password,
            connection_timeout_minutes=connection_timeout,
            health_check_minutes=health_check,
        )
        await hass.async_add_executor_job(emerald_hws_instance.connect)

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

    except Exception as e:
        _LOGGER.error(f"Failed to create Emerald HWS API instance: {e}")
        return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Clean up stored EmeraldHWS instance
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
