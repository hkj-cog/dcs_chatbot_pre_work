import logging
import sys
import time
from opentelemetry.exporter.cloud_logging import CloudLoggingExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from monitoring.session_processor import GlobalSessionIdProcessor 

def setup_app_logger(name: str = "dcs_chatbot") -> logging.Logger:
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # 1. Standard Console Output
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # 2. Initialize the OTel Logger Provider
        logger_provider = LoggerProvider()
        
        # --- ENRICHMENT FIRST ---
        # This adds the session_id to the log record attributes
        logger_provider.add_log_record_processor(GlobalSessionIdProcessor())

        # --- EXPORT SECOND ---
        # This takes the enriched record and batches it for GCP
        exporter = CloudLoggingExporter()
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

        # logger.set_logger_provider(logger_provider)

        # 3. Create the OTel Bridge Handler
        # This "bridges" standard logging.info() calls into the OTel pipeline
        otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        logger.addHandler(otel_handler)

    return logger

logger = setup_app_logger()
