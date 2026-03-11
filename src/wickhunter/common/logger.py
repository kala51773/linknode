import logging
import json
import sys
from typing import Any

def setup_logger(name: str = "wickhunter", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


class StructuredLogger:
    """Wrapper for JSON-structured logging suitable for event and trade logging."""
    def __init__(self, logger_name: str = "wickhunter.events") -> None:
        self._logger = setup_logger(logger_name)

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        data = {
            "event_type": event_type,
            "payload": payload
        }
        self._logger.info(json.dumps(data))
