import logging
import os
import sys

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

# Optional per-module message color overrides (applied to the log message text)
MODULE_MESSAGE_COLORS = {
    "yt2md.kindle": colorama.Fore.MAGENTA + colorama.Style.BRIGHT,
}


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors based on log level, with optional per-module
    message coloring (e.g., Kindle) while keeping file logs uncolored.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Preserve originals so other handlers (e.g., file) aren't affected
        original_levelname = record.levelname
        original_msg = record.msg
        original_name = record.name

        try:
            # Color the level name if we have a mapping
            if record.levelname in LOG_COLORS:
                record.levelname = f"{LOG_COLORS[record.levelname]}{record.levelname}{colorama.Style.RESET_ALL}"

            # Build a safe version of the message (Unicode issues handled)
            raw_msg = str(record.msg)
            try:
                raw_msg.encode(sys.stdout.encoding or 'utf-8', errors='strict')
            except (UnicodeEncodeError, AttributeError):
                raw_msg = raw_msg.encode('ascii', errors='replace').decode('ascii')

            # Decide color for message body
            if original_name in MODULE_MESSAGE_COLORS:
                # Kindle (or other modules) get their own distinct color for the message body
                record.msg = f"{MODULE_MESSAGE_COLORS[original_name]}{raw_msg}{colorama.Style.RESET_ALL}"
            elif original_levelname in LOG_COLORS:
                # Default: color body by level
                record.msg = f"{LOG_COLORS[original_levelname]}{raw_msg}{colorama.Style.RESET_ALL}"
            else:
                record.msg = raw_msg

            formatted = super().format(record)
        finally:
            # Restore record attributes for any subsequent handlers
            record.levelname = original_levelname
            record.msg = original_msg
            record.name = original_name

        return formatted


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure application logging with colored console output and file output"""
    logger = logging.getLogger("yt2md")
    logger.setLevel(level)
    logger.handlers = []  # Clear any existing handlers

    # Console handler with colors - the ColoredFormatter will handle Unicode issues
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
        # Create file handler with UTF-8 encoding
        file_handler = logging.FileHandler(
            log_file, mode="w", encoding="utf-8"
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


def colored_text(text: str, color_style: str) -> str:
    """Format text with specified colorama color and style combination, handling Unicode encoding issues"""
    # Handle Unicode encoding issues by safely encoding the text
    try:
        # Test if the text can be encoded to the console encoding
        console_encoding = sys.stdout.encoding or 'utf-8'
        text.encode(console_encoding, errors='strict')
    except (UnicodeEncodeError, AttributeError):
        # If encoding fails, replace problematic characters
        text = text.encode('ascii', errors='replace').decode('ascii')
    
    return f"{color_style}{text}{colorama.Style.RESET_ALL}"
