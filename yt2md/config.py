import os
import time
from typing import Any, Dict, List

import yaml

from .channel import Channel
from .logger import get_logger

# Get logger for this module
logger = get_logger("config")

# In-memory cache for configuration
_config_cache = None
_config_last_modified = 0
_cache_max_age = 300  # Maximum age of cache in seconds (5 minutes)

# Cache statistics
_cache_stats = {"hits": 0, "misses": 0, "last_hit": None, "last_miss": None}


def _get_config_path() -> str:
    """Return the path to the channels configuration file."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "yt2md/config", "channels.yaml"
    )
    logger.debug(f"Config path: {config_path}")
    return config_path


def _is_cache_valid() -> bool:
    """Check if the cache is still valid based on file modification time and cache age."""
    if _config_cache is None:
        return False

    config_path = _get_config_path()

    try:
        # Check if file was modified after our cache was created
        current_mtime = os.path.getmtime(config_path)
        if current_mtime > _config_last_modified:
            logger.debug("Cache invalid: config file has been modified")
            return False

        # Check if cache has exceeded its maximum age (if max age is enabled)
        if _cache_max_age > 0:
            cache_age = time.time() - _config_last_modified
            if cache_age > _cache_max_age:
                logger.debug(
                    f"Cache invalid: exceeded max age ({cache_age:.1f} > {_cache_max_age} seconds)"
                )
                return False

        return True
    except Exception as e:
        logger.warning(f"Error checking cache validity: {str(e)}")
        return False


def _load_config() -> Dict[str, Any]:
    """Load and return the channels configuration."""
    global _config_cache, _config_last_modified, _cache_stats

    # Return cached config if available and valid
    if _is_cache_valid() and _config_cache is not None:
        # Update cache hit statistics
        _cache_stats["hits"] += 1
        _cache_stats["last_hit"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return _config_cache

    # Update cache miss statistics
    _cache_stats["misses"] += 1
    _cache_stats["last_miss"] = time.strftime("%Y-%m-%d %H:%M:%S")

    config_path = _get_config_path()
    logger.debug(f"Loading configuration from {config_path}")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            if not config:
                logger.error("Loaded config is empty")
                # Return empty dict instead of raising an error
                return {}

            logger.debug(f"Loaded {len(config)} categories")
            # Cache the loaded configuration and update last modified time
            _config_cache = config
            _config_last_modified = time.time()
            return config
    except Exception as e:
        logger.error(f"Failed to load config: {str(e)}")
        # Return empty dict instead of re-raising the exception
        return {}


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


def get_category_colors() -> Dict[str, Dict[str, str]]:
    """Load and return the category color configurations with support for colors and styles."""
    config = _load_config()
    category_colors = config.get("category_colors", {})
    
    # Convert old format to new format for backward compatibility
    processed_colors = {}
    for category, color_config in category_colors.items():
        if isinstance(color_config, str):
            # Old format: just a color string
            processed_colors[category] = {"color": color_config, "style": "NORMAL"}
        elif isinstance(color_config, dict):
            # New format: dict with color and style
            processed_colors[category] = {
                "color": color_config.get("color", "WHITE"),
                "style": color_config.get("style", "NORMAL")
            }
        else:
            # Fallback
            processed_colors[category] = {"color": "WHITE", "style": "NORMAL"}
    
    logger.debug(f"Loaded category colors: {processed_colors}")
    return processed_colors


def get_llm_strategy_config(category: str) -> Dict[str, Any]:
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


def get_llm_model_config(model_type: str, category: str) -> Dict[str, Any]:
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


def get_transcript_length_category(transcript_length: int, category: str) -> str:
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


def get_llm_strategy_for_transcript(transcript: str, category: str) -> Dict[str, str]:
    """
    Get recommended LLM strategy based on transcript length and category.

    Args:
        transcript: The transcript text
        category: Content category

    Returns:
        Dict containing 'primary' and 'fallback' model names
    """
    transcript_word_count = len(transcript.split())
    length_category = get_transcript_length_category(transcript_word_count, category)

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


def reset_config_cache(reset_stats: bool = False) -> None:
    """
    Reset the configuration cache to force reloading from disk on next access.

    Args:
        reset_stats: If True, also reset cache statistics
    """
    global _config_cache, _config_last_modified, _cache_stats
    _config_cache = None
    _config_last_modified = 0

    if reset_stats:
        _cache_stats = {"hits": 0, "misses": 0, "last_hit": None, "last_miss": None}
        logger.debug("Configuration cache and statistics have been reset")
    else:
        logger.debug("Configuration cache has been reset")


def configure_config_cache(max_age_seconds: int = 300) -> None:
    """
    Configure cache parameters.

    Args:
        max_age_seconds: Maximum age of cache in seconds before forced refresh (default: 300s/5min)
                         Set to 0 to disable age-based invalidation.
    """
    global _cache_max_age
    _cache_max_age = max_age_seconds
    logger.debug(f"Config cache max age set to {max_age_seconds} seconds")


def get_config_cache_stats() -> Dict[str, Any]:
    """
    Get statistics about the configuration cache.

    Returns:
        Dict containing cache statistics: hits, misses, hit ratio, last hit time, last miss time
    """
    total = _cache_stats["hits"] + _cache_stats["misses"]
    hit_ratio = _cache_stats["hits"] / total if total > 0 else 0

    return {
        "hits": _cache_stats["hits"],
        "misses": _cache_stats["misses"],
        "hit_ratio": f"{hit_ratio:.2f}",
        "last_hit": _cache_stats["last_hit"],
        "last_miss": _cache_stats["last_miss"],
        "cache_age": time.time() - _config_last_modified
        if _config_last_modified > 0
        else None,
        "max_age": _cache_max_age,
        "is_cached": _config_cache is not None,
    }


def get_category_color_style(category: str) -> str:
    """Get the combined colorama color and style for a specific category.
    
    Args:
        category: The category name to get color/style for
        
    Returns:
        str: Combined colorama color and style codes
    """
    import colorama
    
    category_colors = get_category_colors()
    default_config = category_colors.get("default", {"color": "WHITE", "style": "NORMAL"})
    
    # Get config for the specific category, fallback to Uncategorized, then default
    color_config = category_colors.get(
        category, 
        category_colors.get("Uncategorized", default_config)
    )
    
    # Get colorama attributes
    color = getattr(colorama.Fore, color_config["color"].upper(), colorama.Fore.WHITE)
    style = getattr(colorama.Style, color_config["style"].upper(), colorama.Style.NORMAL)
    
    return color + style
