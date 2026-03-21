"""Structured JSON logging for production (CloudWatch)."""
import logging
import os
import sys

from pythonjsonlogger import jsonlogger


def setup_logging():
    """Configure logging. JSON in production, standard format locally."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    is_production = os.getenv("SERVICE_TYPE") is not None  # Set in Docker

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if is_production:
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
    else:
        formatter = logging.Formatter(
            "%(levelname)-5.5s [%(name)s] %(message)s"
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
