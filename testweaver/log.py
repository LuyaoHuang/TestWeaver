"""Logging utilities for TestWeaver.

Provides a custom TRACE level (more granular than DEBUG) and a
convenience ``get_logger()`` that returns a logger with a ``.trace()``
method already attached.

Usage::

    from testweaver.log import get_logger

    logger = get_logger(__name__)
    logger.debug("Filtering cases...")
    logger.trace("env state: %s", env.to_flat_set())
"""

from __future__ import annotations

import logging
import os
import sys

TRACE = 5
logging.addLevelName(TRACE, "TRACE")

_ROOT = "testweaver"


def get_logger(name: str) -> logging.Logger:
    """Return a logger whose ``.trace(msg, *args)`` method logs at level 5.

    The *name* is passed to ``logging.getLogger`` unchanged so the usual
    hierarchical naming convention (``__name__`` per module) still works.
    """
    logger = logging.getLogger(name)

    def trace(msg: str, *args: object, **kwargs: object) -> None:
        logger.log(TRACE, msg, *args, **kwargs)

    logger.trace = trace  # type: ignore[attr-defined]
    return logger


def configure(
    level: int | str = logging.WARNING,
    log_file: str | None = None,
    workers: int = 1,
    force: bool = False,
) -> None:
    """Configure the ``testweaver`` root logger.

    Args:
        level: One of the standard Python log levels (int or name).
        log_file: If given, also write log lines to this file.
        workers: When > 1, include the thread name in log lines.
        force: If True, replace any existing handlers (useful for tests).
    """
    if isinstance(level, str):
        level_name = level.upper()
        if level_name == "TRACE":
            level = TRACE
        else:
            level = getattr(logging, level_name, logging.WARNING)

    root = logging.getLogger(_ROOT)
    root.setLevel(level)

    if root.handlers:
        if not force:
            return
        for h in list(root.handlers):
            root.removeHandler(h)

    if workers > 1:
        fmt = "%(asctime)s %(levelname)-5s [%(name)s] [%(threadName)s] %(message)s"
    else:
        fmt = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"

    formatter = logging.Formatter(fmt)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(level)
    root.addHandler(stderr_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)

    root.debug("Logging configured: level=%s", logging.getLevelName(level))


def _env_level() -> int | None:
    """Return the log level from ``TESTWEAVER_LOG`` env var, if set."""
    raw = os.environ.get("TESTWEAVER_LOG", "").strip().upper()
    if not raw:
        return None
    if raw == "TRACE":
        return TRACE
    try:
        return int(raw)
    except ValueError:
        return getattr(logging, raw, None)
