# Emerald HWS

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]

_Integration with [emerald_hws_py](https://github.com/ross-w/emerald_hws_py)._

**This integration will set up the following platforms.**

| Platform       | Description                                                        |
| -------------- | ------------------------------------------------------------------ |
| `water_heater` | Creates a water heater control for all Emerald HWS on your account |
| `sensor`       | Creates daily energy usage sensors for all Emerald HWS on your account (configurable) |

## Installation

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
1. If you do not have a `custom_components` directory (folder) there, you need to create it.
1. In the `custom_components` directory (folder) create a new folder called `emeraldenergy`.
1. Download _all_ the files from the `custom_components/emeraldenergy/` directory (folder) in this repository.
1. Place the files you downloaded in the new directory (folder) you created.
1. Restart Home Assistant
1. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Emerald HWS"

## Configuration is done in the UI

The integration setup includes the following options:

- **Username**: Your Emerald HWS account username
- **Password**: Your Emerald HWS account password
- **Connection Timeout**: How long to maintain connection before reconnecting (default: 12 hours)
- **Health Check Interval**: Maximum time expected between data updates before considering the connection unhealthy (default: 1 hour)
- **Enable Energy Monitoring**: Create energy usage sensors (default: enabled)

### Energy Monitoring

When enabled, the integration creates sensors that track energy usage for each hot water system. These sensors Show cumulative energy usage in kWh for the current day, and automatically reset at midnight. They can be configured in the Home Assistant Energy dashboard.

Please note Emerald only provides hourly energy data.

## Mapping of Emerald terms to Home Assistant

To keep things consistent, the following mappings have been used between the Emerald terminology and Home Assistant's

| Emerald | HASS        |
| ------- | ----------- |
| Normal  | Heat Pump   |
| Boost   | Performance |
| Quiet   | Eco         |

## Usage in Automations

This integration provides several attributes that can be used in automations and templates. Here are some examples:

Replace `<serial>` with your water heater's serial number.

To read the current water temperature:
```yaml
{{ state_attr("water_heater.emerald_<serial>", "current_temperature") }}
```

To determine if the water heater is actively heating (not just turned on):
```yaml
{{ state_attr('water_heater.emerald_<serial>', "is_heating") }}
```

## Troubleshooting

### Login Issues
If you're unable to log in, verify your credentials using the Emerald mobile app or web portal first.

### No Data Appearing
If the integration connects but no water heater entities appear, check that your Emerald account has active devices and that you have the correct permissions.

### Integration Not Found
If you can't find "Emerald HWS" in the integrations list after installing via HACS, try restarting Home Assistant again.

<!---->

## Contributions are welcome

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

---

[license-shield]: https://img.shields.io/github/license/ross-w/emerald-hws-ha
[commits-shield]: https://img.shields.io/github/commit-activity/y/ross-w/emerald-hws-ha.svg?style=for-the-badge
[commits]: https://github.com/ross-w/emerald-hws-ha/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[releases-shield]: https://img.shields.io/github/release/ross-w/emerald-hws-ha.svg?style=for-the-badge
[releases]: https://github.com/ross-w/emerald-hws-ha/releases
[maintenance-shield]: https://img.shields.io/maintenance/yes/2025
