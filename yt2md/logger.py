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

    def format(self, record: logging.LogRecord):
        levelname = record.levelname
        if levelname in LOG_COLORS:
            record.levelname = (
                f"{LOG_COLORS[levelname]}{levelname}{colorama.Style.RESET_ALL}"
            )
            record.msg = (
                f"{LOG_COLORS[levelname]}{record.msg}{colorama.Style.RESET_ALL}"
            )
        return super().format(record)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure application logging with colored console output and file output"""
    logger = logging.getLogger("yt2md")
    logger.setLevel(level)
    logger.handlers = []  # Clear any existing handlers

    # Console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    console_handler.setFormatter(ColoredFormatter(console_format, datefmt="%H:%M:%S"))
    logger.addHandler(console_handler)

    # Use fixed log file path - no longer reading from environment variables
    log_file = os.path.abspath(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "yt2md.log")
    )

    try:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)
        # Create file handler
        file_handler = logging.FileHandler(
            log_file, mode="w"
        )  # 'w' mode to overwrite the file each run
        file_handler.setLevel(logging.DEBUG)
        file_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        file_handler.setFormatter(logging.Formatter(file_format))
        logger.addHandler(file_handler)
        console_handler.setFormatter(ColoredFormatter(file_format, datefmt="%H:%M:%S"))
        logger.info(f"Logging to file: {log_file}")
    except Exception as e:
        # Don't fail if logging setup has issues
        print(f"Warning: Could not set up file logging: {str(e)}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name"""
    return logging.getLogger(f"yt2md.{name}")


def colored_text(text: str, color: str) -> str:
    """Format text with specified colorama color"""
    return f"{color}{text}{colorama.Style.RESET_ALL}"
