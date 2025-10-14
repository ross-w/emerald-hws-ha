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

    # Get the shared EmeraldHWS instance from water_heater platform data
    # The instance is stored in hass.data by the water_heater platform
    emerald_instances = hass.data[DOMAIN].get("emerald_instances", {})
    if not emerald_instances:
        _LOGGER.error("No Emerald HWS instances found in hass data")
        return True

    sensors = []
    for _entry_id, emerald_hws_instance in emerald_instances.items():
        # Fetch the list of hot water systems (UUIDs)
        hot_water_systems = await hass.async_add_executor_job(
            emerald_hws_instance.listHWS
        )

        # Create energy sensors for each hot water system
        for hws_uuid in hot_water_systems:
            sensor = EmeraldEnergySensor(hass, emerald_hws_instance, hws_uuid)
            sensors.append(sensor)

    # Add energy sensors to Home Assistant
    if sensors:
        async_add_entities(sensors, True)
        _LOGGER.info(f"Added {len(sensors)} energy monitoring sensors")

    return True


class EmeraldEnergySensor(SensorEntity):
    """Representation of an Emerald HWS energy usage sensor."""

    def __init__(
        self, hass: HomeAssistant, emerald_hws_instance: EmeraldHWS, hws_uuid: str
    ):
        """Initialize the energy sensor."""
        self._hass = hass
        self._emerald_hws = emerald_hws_instance
        self._hws_uuid = hws_uuid
        self._attr_name = None
        self._attr_unique_id = None
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:lightning-bolt"
        self._last_reset = None
        self._today = date.today()

        # Get device info for proper integration
        gi = emerald_hws_instance.getInfo(hws_uuid)
        self._serial_number = gi.get("serial_number")
        self._brand = gi.get("brand", "Emerald")

        # Set up sensor properties
        self._attr_name = f"{self._brand} {self._serial_number} Daily Energy"
        self._attr_unique_id = f"{DOMAIN}_{hws_uuid}_daily_energy"

        # Set up device info for proper grouping with water heater
        self._attr_device_info = {
            "identifiers": {(DOMAIN, hws_uuid)},
            "name": f"{self._brand} {self._serial_number}",
            "manufacturer": self._brand,
            "model": "Hot Water System",
            "serial_number": self._serial_number,
        }

        # Register for updates
        emerald_hws_instance.replaceCallback(self.update_callback)

        # Initialize energy value
        self.update_energy_value()

    @property
    def last_reset(self):
        """Return the time when the sensor was last reset (midnight)."""
        return self._last_reset

    def update_callback(self):
        """Schedules an update within HASS when data changes."""
        _LOGGER.debug(f"Energy sensor callback for {self._attr_name}")
        self.schedule_update_ha_state(True)

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

    async def async_update(self) -> None:
        """Update the sensor state asynchronously."""
        await self._hass.async_add_executor_job(self.update)
