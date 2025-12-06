import logging
import sys
from core.config import settings

def setup_logging():
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Reduce noise from third-party libraries if needed
    logging.getLogger("aiogram").setLevel(settings.LOG_LEVEL)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

