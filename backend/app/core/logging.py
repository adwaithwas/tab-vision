"""Centralised logging configuration using Python's standard library."""

from __future__ import annotations

import logging
import sys

FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once. Safe to call multiple times."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Avoid stacking duplicate handlers across app reloads/tests.
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(handler)

    # Keep third-party libraries quiet unless they really have something to say.
    for noisy in ("uvicorn.access", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger configured with the shared format."""
    return logging.getLogger(name)