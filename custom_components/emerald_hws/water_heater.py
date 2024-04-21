"""Implementation of the Water Heater type for Emerald HWS."""

from .const import DOMAIN

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.components.water_heater import (
    WaterHeaterEntityFeature, WaterHeaterEntity,
    STATE_HEAT_PUMP, STATE_OFF, STATE_PERFORMANCE, STATE_ECO)
from homeassistant.const import (
    CONF_USERNAME, CONF_PASSWORD, TEMP_CELSIUS, PRECISION_WHOLE)
from emerald_hws.emeraldhws import EmeraldHWS

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
}, extra=vol.ALLOW_EXTRA)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Set up the Emerald HWS and populate all units on the account."""
    config = config_entry.data
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)

    # Initialize the EmeraldHWS class from the emerald_hws module
    emerald_hws_instance = EmeraldHWS(username, password)
    await hass.async_add_executor_job(emerald_hws_instance.connect)

    # Fetch the list of hot water systems (UUIDs)
    hot_water_systems = await hass.async_add_executor_job(emerald_hws_instance.listHWS)

    # Create water heater entities for each hot water system
    water_heaters = [EmeraldWaterHeater(hass, emerald_hws_instance, hws_uuid) for hws_uuid in hot_water_systems]

    # Add water heater entities to Home Assistant
    async_add_entities(water_heaters, True)

    return True

class EmeraldWaterHeater(WaterHeaterEntity):
    """Representation of a water heater."""

    def __init__(self, hass, emerald_hws_instance, hws_uuid):
        """Initialize the water heater."""
        self._emerald_hws = emerald_hws_instance
        self._hass = hass
        self._hws_uuid = hws_uuid
        gi = emerald_hws_instance.getInfo(hws_uuid)
        status = emerald_hws_instance.getFullStatus(hws_uuid)
        self._serial_number = gi.get("serial_number")
        self._brand = gi.get("brand")
        self._name = f"{self._brand} {self._serial_number}"
        self._current_temperature = status.get("last_state").get("temp_current")
        self._target_temperature = status.get("last_state").get("temp_set")
        self._running = emerald_hws_instance.isOn(hws_uuid)
        self._current_mode = emerald_hws_instance.currentMode(hws_uuid)
        self._operation_list = [
            STATE_HEAT_PUMP,
            STATE_PERFORMANCE,
            STATE_ECO,
            STATE_OFF,
        ]
        self._attr_icon = "mdi:water-boiler"
        self._attr_precision = PRECISION_WHOLE
        emerald_hws_instance.replaceCallback(self.update_callback)

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return WaterHeaterEntityFeature.OPERATION_MODE

    @property
    def name(self) -> str:
        """Return the name of the water heater."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return a unique ID for the water heater."""
        return f"{DOMAIN}_{self._hws_uuid}"

    @property
    def current_operation(self):
        """Return current operating mode."""
        if not self._running:
            return STATE_OFF
        else:
            return self.modeToOpState(self._current_mode)

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self) -> float:
        """Return the target temperature."""
        return self._target_temperature

    @property
    def operation_list(self) -> list[str]:
        """Return list of possible operation modes."""
        return self._operation_list

    @property
    def temperature_unit(self) -> str:
        """Return the temperature unit."""
        return TEMP_CELSIUS

    def modeToOpState(self, mode):
        """Return the HASS state given an Emerald internal int state."""
        if mode==1:
            return STATE_HEAT_PUMP
        elif mode==0:
            return STATE_PERFORMANCE
        elif mode==2:
            return STATE_ECO

    def set_operation_mode(self, operation_mode: str) -> None:
        """Set the internal state given a HASS state."""
        _LOGGER.info(f"emeraldhws: setting operation mode to {operation_mode}")
        if self._running:
            if operation_mode == STATE_OFF:
                self._emerald_hws.turnOff(self._hws_uuid)
        else:
            if operation_mode != STATE_OFF:
                self._emerald_hws.turnOn(self._hws_uuid)

        if operation_mode == STATE_PERFORMANCE:
            self._emerald_hws.setBoostMode(self._hws_uuid)
        if operation_mode == STATE_ECO:
            self._emerald_hws.setQuietMode(self._hws_uuid)
        if operation_mode == STATE_HEAT_PUMP:
            self._emerald_hws.setNormalMode(self._hws_uuid)

    async def async_set_operation_mode(self, operation_mode):
        """Schedule the sync function to set the operation mode."""
        await self._hass.async_add_executor_job(self.set_operation_mode, operation_mode)

    async def async_turn_on(self):
        """Turn on the Emerald unit."""
        await self._hass.async_add_executor_job(self._emerald_hws.turnOn, self._hws_uuid)
        #await self._emerald_hws.turnOn(self._hws_uuid)

    async def async_turn_off(self):
        """Turn off the Emerald unit."""
        await self._hass.async_add_executor_job(self._emerald_hws.turnOff, self._hws_uuid)
        #await self._emerald_hws.turnOff(self._hws_uuid)

    def update_callback(self):
        """Schedules an update within HASS."""
        _LOGGER.info("emeraldhws: callback called")
        self.schedule_update_ha_state()

    def update(self):
        """Update with values from HWS."""
        _LOGGER.info("emeraldhws: updating internal state from module")
        state = self._emerald_hws.getFullStatus(self._hws_uuid)

        if state is not None:
            self._current_temperature = state.get("last_state").get("temp_current")
            self._target_temperature = state.get("last_state").get("temp_set")
            self._running = self._emerald_hws.isOn(self._hws_uuid)
            self._current_mode = self._emerald_hws.currentMode(self._hws_uuid)

        return

    async def async_update(self) -> None:
        """Update the water heater state."""
        await self._hass.async_add_executor_job(self.update)
