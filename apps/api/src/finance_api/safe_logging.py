import json
import logging


class SafeFormatter(logging.Formatter):
    """Allowlist output; even third-party exception messages may contain credentials."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"event": "service_event", "level": record.levelname})


LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {"safe": {"()": SafeFormatter}},
    "handlers": {"safe": {"class": "logging.StreamHandler", "formatter": "safe"}},
    "root": {"handlers": ["safe"], "level": "WARNING"},
    "loggers": {
        "uvicorn": {"handlers": ["safe"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO", "propagate": True},
        "uvicorn.access": {"handlers": [], "propagate": False},
    },
}
