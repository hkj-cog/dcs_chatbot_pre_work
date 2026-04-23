import logging
import sys
import time
from opentelemetry.exporter.cloud_logging import CloudLoggingExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from monitoring.session_processor import GlobalSessionIdProcessor 
from opentelemetry import _logs # Add this import

def setup_app_logger(name: str = "dcs_chatbot") -> logging.Logger:
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # 1. Standard Console
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(handler)

        # 2. Setup OTel Provider
        resource = Resource.create({"service.name": name})
        logger_provider = LoggerProvider(resource=resource)
        
        # Add your processors
        logger_provider.add_log_record_processor(GlobalSessionIdProcessor())
        
        # Explicitly set log_id to avoid the "temp" name issue we discussed
        exporter = CloudLoggingExporter(default_log_name=name)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

        # --- CRITICAL FIX ---
        # This makes your custom provider the "official" one for the whole app
        _logs.set_logger_provider(logger_provider)

        # 3. Bridge
        otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        logger.addHandler(otel_handler)

    return logger

logger = setup_app_logger("dcs_chatbot")
