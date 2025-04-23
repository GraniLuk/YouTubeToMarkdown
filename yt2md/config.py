import os
from typing import List, Dict, Any

import yaml

from .channel import Channel


def _get_config_path() -> str:
    """Return the path to the channels configuration file."""
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "yt2md/config", "channels.yaml"
    )


def _load_config() -> Dict[str, List[Dict[str, Any]]]:
    """Load and return the channels configuration."""
    config_path = _get_config_path()
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
    """
    Load channels from the configuration file for a specific category
    """
    config = _load_config()

    if category not in config:
        return []

    return [_create_channel(channel, category) for channel in config[category]]


def load_all_channels() -> List[Channel]:
    """
    Load channels from the configuration file for all categories
    """
    config = _load_config()
    
    all_channels = []
    for category, channels_in_category in config.items():
        for channel in channels_in_category:
            all_channels.append(_create_channel(channel, category))
    return all_channels
