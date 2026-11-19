"""Idempotent console/file logger setup."""

from __future__ import annotations

import logging
from pathlib import Path


def get_logger(
    name: str = "gold_entry_engine",
    *,
    log_file: str | Path | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not any(getattr(handler, "_gold_engine_console", False) for handler in logger.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        stream._gold_engine_console = True  # type: ignore[attr-defined]
        logger.addHandler(stream)
    if log_file is not None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        resolved = str(path.resolve())
        if not any(getattr(handler, "baseFilename", None) == resolved for handler in logger.handlers):
            file_handler = logging.FileHandler(path, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    return logger
