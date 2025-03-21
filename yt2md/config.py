import os
from typing import List

import yaml

from .channel import Channel


def load_channels(category: str) -> List[Channel]:
    """
    Load channels from the configuration file for a specific category
    """
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "channels.yaml"
    )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if category not in config:
        return []

    return [
        Channel(
            id=channel["id"],
            language_code=channel["language_code"],
            output_language=channel["output_language"],
            category=category,
            name=channel["name"],
        )
        for channel in config[category]
    ]
