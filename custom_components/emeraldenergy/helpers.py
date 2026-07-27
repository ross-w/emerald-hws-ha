"""Shared helpers for the Emerald Hot Water System integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from emerald_hws.emeraldhws import EmeraldHWS

from .const import (
    CONF_CONNECTION_TIMEOUT,
    CONF_HEALTH_CHECK,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_HEALTH_CHECK,
)


def create_hws(config: Mapping[str, Any]) -> EmeraldHWS:
    """Build an EmeraldHWS client from config entry data or config flow input.

    Blocking: constructing EmeraldHWS reaches into awsiotsdk/awscrt, which imports a
    compiled extension and does blocking work, so only call this from the executor.
    """
    return EmeraldHWS(
        config.get(CONF_USERNAME),
        config.get(CONF_PASSWORD),
        connection_timeout_minutes=config.get(
            CONF_CONNECTION_TIMEOUT, DEFAULT_CONNECTION_TIMEOUT
        ),
        health_check_minutes=config.get(CONF_HEALTH_CHECK, DEFAULT_HEALTH_CHECK),
    )
