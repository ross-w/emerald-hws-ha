# Emerald HWS

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

_Integration with [emerald_hws_py](https://github.com/ross-w/emerald_hws_py)._

**This integration will set up the following platforms.**

| Platform       | Description                                                        |
| -------------- | ------------------------------------------------------------------ |
| `water_heater` | Creates a water heater control for all Emerald HWS on your account |

## Installation

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
1. If you do not have a `custom_components` directory (folder) there, you need to create it.
1. In the `custom_components` directory (folder) create a new folder called `emeraldenergy`.
1. Download _all_ the files from the `custom_components/emeraldenergy/` directory (folder) in this repository.
1. Place the files you downloaded in the new directory (folder) you created.
1. Restart Home Assistant
1. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Integration blueprint"

## Configuration is done in the UI

Please note that to keep things with consistent the following mappings have been used between the Emerald terminology and Home Assistant's

| Emerald | HASS        |
| ------- | ----------- |
| Normal  | Heat Pump   |
| Boost   | Performance |
| Quiet   | Eco         |

<!---->

## Contributions are welcome

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

---

[license-shield]: https://img.shields.io/github/license/ross-w/emerald-hws-ha
[commits-shield]: https://img.shields.io/github/commit-activity/y/ross-w/emerald-hws-ha.svg?style=for-the-badge
[commits]: https://github.com/ross-w/emerald-hws-ha/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[releases-shield]: https://img.shields.io/github/release/ross-w/emerald-hws-ha.svg?style=for-the-badge
[releases]: https://github.com/ross-w/emerald-hws-ha/releases
[maintenance-shield]: https://img.shields.io/maintenance/yes/2024
