"""Implementation of the Sensor platform for Emerald HWS energy monitoring."""

from __future__ import annotations

import logging
from datetime import datetime, date

from homeassistant import config_entries
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from emerald_hws.emeraldhws import EmeraldHWS

from .const import (
    DOMAIN,
    CONF_ENABLE_ENERGY_MONITORING,
)
from .helpers import CallbackDrivenEntityMixin, device_info_for

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Set up the energy monitoring sensors for Emerald HWS."""
    # Check if energy monitoring is enabled in config
    if not config_entry.data.get(CONF_ENABLE_ENERGY_MONITORING, True):
        _LOGGER.info("Energy monitoring is disabled in configuration")
        return True

    # Get the shared EmeraldHWS data from hass.data
    entry_data = hass.data[DOMAIN].get(config_entry.entry_id)
    if not entry_data:
        _LOGGER.error("No Emerald HWS data found in hass data")
        return False

    emerald_hws_instance = entry_data["instance"]
    callback_dispatcher = entry_data["dispatcher"]

    sensors = []
    # Fetch the list of hot water systems (UUIDs)
    hot_water_systems = await hass.async_add_executor_job(emerald_hws_instance.listHWS)

    # Create energy sensors for each hot water system
    for hws_uuid in hot_water_systems:
        sensor = EmeraldEnergySensor(
            hass, emerald_hws_instance, hws_uuid, callback_dispatcher
        )
        sensors.append(sensor)

    # Add energy sensors to Home Assistant
    if sensors:
        async_add_entities(sensors, True)
        _LOGGER.info(f"Added {len(sensors)} energy monitoring sensors")

    return True


class EmeraldEnergySensor(CallbackDrivenEntityMixin, SensorEntity):
    """Representation of an Emerald HWS energy usage sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        emerald_hws_instance: EmeraldHWS,
        hws_uuid: str,
        callback_dispatcher,
    ):
        """Initialize the energy sensor."""
        self._hass = hass
        self._emerald_hws = emerald_hws_instance
        self._hws_uuid = hws_uuid
        self._callback_dispatcher = callback_dispatcher
        self._attr_name = None
        self._attr_unique_id = None
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:lightning-bolt"
        self._last_reset = None
        self._today = date.today()

        # Get device info for proper integration
        gi = emerald_hws_instance.getInfo(hws_uuid)
        # Fall back rather than leaving these None: they land in the device
        # registry, which is last-write-wins across this entity and the water
        # heater sharing the same device -- a None from either would blank out
        # a value the other successfully set.
        self._serial_number = gi.get("serial_number") or hws_uuid
        self._brand = gi.get("brand") or "Emerald"

        # Set up sensor properties
        self._attr_name = f"{self._brand} {self._serial_number} Daily Energy"
        self._attr_unique_id = f"{DOMAIN}_{hws_uuid}_daily_energy"

        # Set up device info for proper grouping with water heater
        self._attr_device_info = device_info_for(
            hws_uuid, self._brand, self._serial_number
        )

        # Register for updates with callback dispatcher
        callback_dispatcher.register_callback(self.update_callback)

        # Initialize energy value
        self.update_energy_value()

    @property
    def last_reset(self):
        """Return the time when the sensor was last reset (midnight)."""
        return self._last_reset

    def update_energy_value(self):
        """Update the energy value from the API."""
        try:
            # Check if we need to reset (new day)
            today = date.today()
            if today != self._today:
                self._today = today
                self._last_reset = datetime.combine(today, datetime.min.time())
                _LOGGER.info(f"Daily energy sensor reset for {self._attr_name}")

            # Get daily energy usage
            daily_energy = self._emerald_hws.getDailyEnergyUsage(self._hws_uuid)
            if daily_energy is not None:
                self._attr_native_value = round(
                    daily_energy, 3
                )  # Round to 3 decimal places
            else:
                _LOGGER.warning(f"Failed to get daily energy for {self._hws_uuid}")
                self._attr_native_value = None
        except Exception as e:
            _LOGGER.error(f"Error updating energy value for {self._hws_uuid}: {e}")
            self._attr_native_value = None

    def update(self):
        """Update the sensor state."""
        _LOGGER.debug(f"Updating energy sensor {self._attr_name}")
        self.update_energy_value()
