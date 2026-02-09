"""Logging configuration with Application Insights integration."""

import logging
import os
import sys

def configure_logging():
    """Configure structured logging with optional Application Insights.

    Call this once at application startup, before any logging occurs.
    """
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler with structured format
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Format: timestamp - level - module - message
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Configure Application Insights if connection string is set
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if connection_string:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(
                connection_string=connection_string,
                # Disable live metrics to reduce overhead
                enable_live_metrics=False,
            )
            logging.getLogger(__name__).info(
                "Application Insights configured",
                extra={"connection_string_preview": connection_string[:30] + "..."}
            )
        except ImportError:
            logging.getLogger(__name__).warning(
                "azure-monitor-opentelemetry not installed, Application Insights disabled"
            )
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Failed to configure Application Insights: {e}"
            )
    else:
        logging.getLogger(__name__).info(
            "Application Insights not configured (APPLICATIONINSIGHTS_CONNECTION_STRING not set)"
        )

    # Reduce noise from third-party libraries
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name.

    Usage:
        from .logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Something happened", extra={"user": "test@example.com"})
    """
    return logging.getLogger(name)
