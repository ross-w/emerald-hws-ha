"""Shared helpers for the Emerald Hot Water System integration."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from pathlib import PurePath
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


# A compiled function rejecting its caller's argument count, e.g. "function takes
# exactly 43 arguments (45 given)". Both wordings below come from CPython's C API
# (PyArg_ParseTuple and argument clinic respectively); a pure-Python arity error
# reads "takes N positional arguments but M were given" instead. Small counts are
# spelled as words by METH_NOARGS/METH_O, hence "no" and "one".
#
# Matching this message is necessary but NOT sufficient: every compiled extension
# raises it, so an ordinary bug elsewhere in the stack looks identical. Callers
# must also confirm the frame it came from with _raised_inside_awscrt().
_NATIVE_ARITY_ERROR = re.compile(
    r"takes (?:exactly |at most |at least )?(?:\d+|no|one) arguments? \(\d+ given\)"
    r"|expected (?:exactly |at most |at least )?\d+ arguments?, got \d+"
)


def _raised_inside_awscrt(err: BaseException) -> bool:
    """Report whether any frame in err's traceback belongs to the awscrt package.

    Walks the raw traceback rather than using traceback.extract_tb, which reads the
    source files off disk through linecache -- unwanted work on a failure path.

    Frames are identified by module name, falling back to the file path for the rare
    frame whose globals carry no __name__ (exec'd or embedded code). Missing a real
    awscrt frame would put setup back into an endless retry loop, so the fallback is
    worth the extra line.
    """
    tb = err.__traceback__
    while tb is not None:
        module = tb.tb_frame.f_globals.get("__name__")
        if module is not None:
            if module == "awscrt" or module.startswith("awscrt."):
                return True
        elif "awscrt" in PurePath(tb.tb_frame.f_code.co_filename).parts:
            return True
        tb = tb.tb_next
    return False


def _exception_chain(err: BaseException) -> Iterator[BaseException]:
    """Yield err and every exception behind it, outermost first.

    The walk order is: prefer __cause__ ("raise X from Y", an explicit statement of
    what really went wrong); otherwise stop at a suppressed context ("raise X from
    None" deliberately hides it); otherwise follow __context__, the error that was
    being handled when this one was raised. A chain that loops back on itself ends
    the walk. The caller holds a reference to the head throughout, so no link can be
    collected mid-walk and have its id() reused.
    """
    seen: set[int] = set()
    while err is not None and id(err) not in seen:
        seen.add(id(err))
        yield err
        if err.__cause__ is not None:
            err = err.__cause__
        elif err.__suppress_context__:
            return
        else:
            err = err.__context__


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
      - AttributeError on _certificate_source, an attribute the newer awscrt.io
        sets on ClientTlsContext and the newer metrics code reads back, and which
        is therefore missing whenever the ClientTlsContext was built by the older
        awscrt.io still sitting in sys.modules.
      - TypeError on argument count, from the two metrics arguments that awscrt
        0.32.2 added to the native mqtt5_client_new binding.

    Neither is retryable. The stale modules stay in sys.modules for the lifetime
    of the process, so only restarting Home Assistant can clear it -- which is why
    this is reported as a permanent error rather than left to HA's retry backoff.
    """
    for link in _exception_chain(err):
        message = str(link)
        if isinstance(link, AttributeError) and "_certificate_source" in message:
            return True
        if (
            isinstance(link, TypeError)
            and _NATIVE_ARITY_ERROR.search(message)
            and _raised_inside_awscrt(link)
        ):
            return True
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
