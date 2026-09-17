"""Constants for the Emerald Hot Water System integration."""

DOMAIN = "emeraldenergy"

# Configuration constants
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_CONNECTION_TIMEOUT = "connection_timeout"
CONF_HEALTH_CHECK = "health_check"
CONF_ENABLE_ENERGY_MONITORING = "enable_energy_monitoring"

# Default values
DEFAULT_CONNECTION_TIMEOUT = 720  # 12 hours in minutes
DEFAULT_HEALTH_CHECK = 10  # minutes.
# emerald_hws.getFullStatus() serves a local cache updated only by inbound
# MQTT pushes -- it never hits the network in steady state. If the MQTT
# connection to the Emerald cloud goes silently idle (no error, just stops
# receiving), this health-check timer is the only thing that notices and
# forces a reconnect. A generous interval here directly bounds how long a
# stale reading (temperature, mode, energy) can sit in HA before it's caught.
DEFAULT_ENABLE_ENERGY_MONITORING = True
