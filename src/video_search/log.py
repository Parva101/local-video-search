import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname,
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("video_search")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
