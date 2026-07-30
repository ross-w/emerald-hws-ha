"""Shared helpers for the Emerald Hot Water System integration."""

from __future__ import annotations

import re
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


# A compiled awscrt function rejecting its own wrapper's call, e.g.
# "function takes exactly 43 arguments (45 given)". This is the C-extension
# wording; a pure-Python arity error reads "takes N positional arguments but M
# were given" instead, so this does not match ordinary bugs in our own code.
_NATIVE_ARITY_ERROR = re.compile(
    r"takes (?:exactly |at most |at least )?\d+ arguments? \(\d+ given\)"
)


def is_awscrt_straddle_error(err: BaseException) -> bool:
    """Report whether a failure came from awscrt being loaded at two versions.

    This docstring is the canonical explanation for this integration; callers
    refer here rather than repeating it. The README covers the same ground for
    users, under "Errors mentioning awscrt during setup".

    awscrt is a compiled extension whose Python files and native library have to
    match. Home Assistant imports it during startup, long before this integration
    is set up: `cloud` is a Stage 1 integration, and hass_nabucasa reaches
    botocore, whose compat module imports awscrt.auth unconditionally, which pulls
    in awscrt.io and the _awscrt extension. If Home Assistant then upgrades awscrt
    on disk while installing our requirements, the modules we import afterwards
    come from the new version while the ones already in sys.modules stay old, and
    the two halves meet inside connect().

    Two ways that surfaces, both from awscrt's IoT usage-metrics feature:
      - AttributeError on _certificate_source, a slot only awscrt >=0.35.0's
        awscrt.io declares but which >=0.35.0's metrics code always reads.
      - TypeError on argument count, from the two metrics arguments that awscrt
        0.32.2 added to the native mqtt5_client_new binding.

    Neither is retryable. The stale modules stay in sys.modules for the lifetime
    of the process, so only restarting Home Assistant can clear it -- which is why
    this is reported as a permanent error rather than left to HA's retry backoff.
    """
    seen: set[int] = set()
    while err is not None and id(err) not in seen:
        seen.add(id(err))
        message = str(err)
        if isinstance(err, AttributeError) and "_certificate_source" in message:
            return True
        if isinstance(err, TypeError) and _NATIVE_ARITY_ERROR.search(message):
            return True
        err = err.__cause__ or err.__context__
    return False


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
