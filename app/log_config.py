"""Persistent file logging for the L7R app.

Logs go to two sinks:

  1. ``stderr`` — preserves ``fly logs`` live-tail behavior.
  2. ``$LOG_DIR/app.log`` on the persistent volume, rotated at UTC
     midnight, 15 days retained — gives a window for diagnosing bug
     reports after the fact.

Without this, ``logging.getLogger(...)`` calls scattered across the
app land in Fly's short-lived live buffer and disappear within hours,
which means even a same-day bug report ("when I hit save it gave me
an error") is impossible to investigate.

The file handler is best-effort: if ``LOG_DIR`` can't be created
(read-only mount, disk full) the failure is logged via stderr and
startup continues. Logging-disabled is never a reason to fail the
machine.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s %(message)s"

# Handlers we've added to the root (or to uvicorn loggers). Tracked
# here so a second call to ``configure_logging`` can tear them down
# rather than stacking duplicates - matters mostly for tests, but
# also for any hot-reload path during dev.
_INSTALLED_HANDLERS: list[logging.Handler] = []

# Uvicorn ships logs through these named loggers. Both have their
# parent's propagation configured such that attaching our handler at
# each leaf gives exactly one emission per record - attaching to
# ``uvicorn`` as well duplicates ``uvicorn.error`` lines because that
# child propagates up to it.
_UVICORN_LOGGERS = ("uvicorn.access", "uvicorn.error")


def _remove_previously_installed() -> None:
    root = logging.getLogger()
    for h in list(_INSTALLED_HANDLERS):
        root.removeHandler(h)
        for name in _UVICORN_LOGGERS:
            logging.getLogger(name).removeHandler(h)
        try:
            h.close()
        except Exception:  # pragma: no cover - close() failure is non-fatal
            pass
    _INSTALLED_HANDLERS.clear()


def configure_logging() -> None:
    """Install stderr + rotating-file handlers on the root logger.

    Idempotent: subsequent calls remove our previously installed
    handlers before re-adding fresh ones, so test fixtures (and the
    rare hot-reload) don't duplicate output."""
    _remove_previously_installed()

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)
    _INSTALLED_HANDLERS.append(stderr_handler)

    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_dir / "app.log",
            when="midnight",
            backupCount=15,
            encoding="utf-8",
            utc=True,
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        _INSTALLED_HANDLERS.append(file_handler)

        # Uvicorn configures its own loggers and does not propagate to
        # root, so attach our file handler directly. Without this its
        # access/error lines never make it to the persistent file -
        # and those are exactly the lines you want when chasing "what
        # request did the user make right before the bug?".
        for name in _UVICORN_LOGGERS:
            logging.getLogger(name).addHandler(file_handler)
    except OSError as e:
        root.error("Persistent file logging disabled: %s", e)


__all__ = ["configure_logging"]
