"""Unit types for ReEDS model components.

Uses r2x_core.units for unit annotations.
"""

from typing import Annotated

from pydantic import Field

# Legacy type aliases for backward compatibility
EmissionRate = Annotated[float, Field(description="Emission rate in kg/MWh", ge=0)]
Percentage = Annotated[float, Field(description="Percentage value (0-100)", ge=0, le=100)]
