import os
from typing import List, Dict, Any

import yaml

from .channel import Channel
from .logger import get_logger

# Get logger for this module
logger = get_logger('config')


def _get_config_path() -> str:
    """Return the path to the channels configuration file."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "yt2md/config", "channels.yaml"
    )
    logger.debug(f"Config path: {config_path}")
    return config_path


def _load_config() -> Dict[str, List[Dict[str, Any]]]:
    """Load and return the channels configuration."""
    config_path = _get_config_path()
    logger.debug(f"Loading configuration from {config_path}")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            logger.debug(f"Loaded {len(config)} categories")
            return config
    except Exception as e:
        logger.error(f"Failed to load config: {str(e)}")
        raise


def _create_channel(channel_data: Dict[str, Any], category: str) -> Channel:
    """Create a Channel object from raw data."""
    return Channel(
        id=channel_data["id"],
        language_code=channel_data["language_code"],
        output_language=channel_data["output_language"],
        category=category,
        name=channel_data["name"],
    )


def load_channels_by_category(category: str) -> List[Channel]:
    """Load channels from the configuration file for a specific category"""
    logger.info(f"Loading channels for category: {category}")
    config = _load_config()

    if category not in config:
        logger.warning(f"Category '{category}' not found in configuration")
        return []

    channels = [_create_channel(channel, category) for channel in config[category]]
    logger.info(f"Loaded {len(channels)} channels for category '{category}'")
    return channels


def load_all_channels() -> List[Channel]:
    """Load channels from the configuration file for all categories"""
    logger.info("Loading all channels from configuration")
    config = _load_config()
    
    all_channels = []
    for category, channels_in_category in config.items():
        logger.debug(f"Loading {len(channels_in_category)} channels from category '{category}'")
        for channel in channels_in_category:
            all_channels.append(_create_channel(channel, category))
    logger.info(f"Loaded {len(all_channels)} channels in total")
    return all_channels
