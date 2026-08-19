"""Logging configuration."""

import logging
import sys


def setup_logging(level: str) -> None:
    """Configure logging with the given level."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
