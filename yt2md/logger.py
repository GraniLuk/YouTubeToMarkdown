import logging
import os

import colorama

# Initialize colorama for Windows terminals
colorama.init()

# Define color codes for different log levels
LOG_COLORS = {
    "DEBUG": colorama.Fore.BLUE,
    "INFO": colorama.Fore.GREEN,
    "WARNING": colorama.Fore.YELLOW,
    "ERROR": colorama.Fore.RED,
    "CRITICAL": colorama.Fore.RED + colorama.Style.BRIGHT,
}


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors based on log level"""

    def format(self, record):
        levelname = record.levelname
        if levelname in LOG_COLORS:
            record.levelname = (
                f"{LOG_COLORS[levelname]}{levelname}{colorama.Style.RESET_ALL}"
            )
            record.msg = (
                f"{LOG_COLORS[levelname]}{record.msg}{colorama.Style.RESET_ALL}"
            )
        return super().format(record)


def setup_logging(level=logging.INFO, log_file=None):
    """Configure application logging with colored console output"""
    logger = logging.getLogger("yt2md")
    logger.setLevel(level)
    logger.handlers = []  # Clear any existing handlers

    # Console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    console_handler.setFormatter(ColoredFormatter(console_format, datefmt="%H:%M:%S"))
    logger.addHandler(console_handler)

    # File handler if requested
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        file_handler.setFormatter(logging.Formatter(file_format))
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name"""
    return logging.getLogger(f"yt2md.{name}")


def colored_text(text: str, color: str) -> str:
    """Format text with specified colorama color"""
    return f"{color}{text}{colorama.Style.RESET_ALL}"
