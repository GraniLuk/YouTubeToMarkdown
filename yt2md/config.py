import os
from typing import Any, Dict, List, Optional

import yaml

from .channel import Channel
from .logger import get_logger

# Get logger for this module
logger = get_logger("config")


def _get_config_path() -> str:
    """Return the path to the channels configuration file."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "yt2md/config", "channels.yaml"
    )
    logger.debug(f"Config path: {config_path}")
    return config_path


def _load_config() -> Dict[str, Any]:
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
        title_filters=channel_data.get("title_filters", []),
    )


def load_channels_by_category(category: str) -> List[Channel]:
    """Load channels from the configuration file for a specific category"""
    logger.debug(f"Loading channels for category: {category}")
    config = _load_config()

    if category not in config:
        logger.warning(f"Category '{category}' not found in configuration")
        return []

    channels = [_create_channel(channel, category) for channel in config[category]]
    logger.debug(f"Loaded {len(channels)} channels for category '{category}'")
    return channels


def load_all_channels() -> List[Channel]:
    """Load channels from the configuration file for all categories"""
    logger.info("Loading all channels from configuration")
    config = _load_config()

    all_channels = []
    for category, channels_in_category in config.items():
        # Skip non-list entries (like llm_strategies)
        if not isinstance(channels_in_category, list):
            continue

        logger.debug(
            f"Loading {len(channels_in_category)} channels from category '{category}'"
        )
        for channel in channels_in_category:
            all_channels.append(_create_channel(channel, category))
    logger.info(f"Loaded {len(all_channels)} channels in total")
    return all_channels


def get_llm_strategy_config(category: str = None) -> Dict[str, Any]:
    """
    Get LLM strategy configuration based on category.

    Args:
        category: The content category to get LLM strategy for (if None, returns default config)

    Returns:
        Dict containing LLM strategy configuration
    """
    config = _load_config()
    strategies_config = config.get("llm_strategies", {})

    # Get default config
    default_config = strategies_config.get("default", {})

    # If no category provided or category not found, return default
    if not category or category not in strategies_config:
        return default_config

    # Get category-specific config
    category_config = strategies_config.get(category, {})

    # Merge with default config (category overrides default)
    merged_config = {}

    # Deep merge strategy_by_length
    if "strategy_by_length" in default_config:
        merged_config["strategy_by_length"] = default_config[
            "strategy_by_length"
        ].copy()
        if "strategy_by_length" in category_config:
            for length_key, length_strategies in category_config[
                "strategy_by_length"
            ].items():
                if length_key in merged_config["strategy_by_length"]:
                    # Override existing length strategy
                    merged_config["strategy_by_length"][length_key] = length_strategies
                else:
                    # Add new length strategy
                    merged_config["strategy_by_length"][length_key] = length_strategies

    # Copy length thresholds from default
    if "length_thresholds" in default_config:
        merged_config["length_thresholds"] = default_config["length_thresholds"].copy()
        if "length_thresholds" in category_config:
            # Override with category-specific thresholds
            merged_config["length_thresholds"].update(
                category_config["length_thresholds"]
            )

    # Deep merge model_configs
    if "model_configs" in default_config:
        merged_config["model_configs"] = default_config["model_configs"].copy()
        if "model_configs" in category_config:
            for model, model_config in category_config["model_configs"].items():
                if model in merged_config["model_configs"]:
                    # Merge model configs
                    merged_config["model_configs"][model].update(model_config)
                else:
                    # Add new model config
                    merged_config["model_configs"][model] = model_config

    return merged_config


def get_llm_model_config(model_type: str, category: str = None) -> Dict[str, Any]:
    """
    Get configuration for a specific LLM model type based on category.

    Args:
        model_type: Type of the model ('gemini', 'perplexity', 'ollama')
        category: The content category (if None, uses default config)

    Returns:
        Dict containing model configuration
    """
    strategy_config = get_llm_strategy_config(category)
    model_configs = strategy_config.get("model_configs", {})

    return model_configs.get(model_type, {})


def get_transcript_length_category(transcript_length: int, category: str = None) -> str:
    """
    Determine length category of transcript based on its length and content category.

    Args:
        transcript_length: Length of the transcript in characters
        category: Content category to get thresholds for

    Returns:
        str: 'short', 'medium', or 'long'
    """
    strategy_config = get_llm_strategy_config(category)
    thresholds = strategy_config.get("length_thresholds", {})

    short_max = thresholds.get("short_max", 1000)
    medium_max = thresholds.get("medium_max", 3000)

    if transcript_length <= short_max:
        return "short"
    elif transcript_length <= medium_max:
        return "medium"
    else:
        return "long"


def get_llm_strategy_for_transcript(
    transcript: str, category: str = None
) -> Dict[str, str]:
    """
    Get recommended LLM strategy based on transcript length and category.

    Args:
        transcript: The transcript text
        category: Content category

    Returns:
        Dict containing 'primary' and 'fallback' model names
    """
    transcript_length = len(transcript)
    length_category = get_transcript_length_category(transcript_length, category)

    strategy_config = get_llm_strategy_config(category)
    length_strategies = strategy_config.get("strategy_by_length", {})

    # Get strategy by length category
    strategy = length_strategies.get(length_category, {})

    # Default to empty dict if not found
    if not strategy:
        logger.warning(
            f"No LLM strategy found for {length_category} transcripts in category {category}"
        )
        strategy = {"primary": "gemini", "fallback": "perplexity"}

    return strategy
