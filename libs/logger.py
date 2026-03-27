import logging
import sys


def setup_app_logger(name: str = "dcs_chatbot") -> logging.Logger:
    # 1. Create a logger instance
    logger = logging.getLogger(name)

    # 2. Avoid duplicate logs if the logger is already configured
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # 3. Create a handler (GCP loves JSON or structured text on stdout)
        handler = logging.StreamHandler(sys.stdout)

        # 4. Define a clean format
        # Note: GCP automatically adds timestamps, so we keep it concise
        formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger


# Initialize the shared instance
logger = setup_app_logger()
