"""Helper functions for using r2x-core rules in parsing."""

from __future__ import annotations

from typing import Any

from r2x_core import ParserContext, System
from r2x_reeds.plugin_config import ReEDSConfig


def create_parser_context(
    system: System,
    config: ReEDSConfig,
    defaults: dict[str, Any],
) -> ParserContext:
    """Create a ParserContext for use with rules.

    Parameters
    ----------
    system : System
        The infrasys System being populated
    config : ReEDSConfig
        ReEDS configuration
    defaults : dict[str, Any]
        Loaded defaults (tech_categories, etc.)

    Returns
    -------
    ParserContext
        Context ready for use with parsing rules
    """
    return ParserContext(
        system=system,
        config=config,
        metadata={
            "tech_categories": defaults.get("tech_categories", {}),
            "category_class_mapping": defaults.get("category_class_mapping", {}),
        },
    )
