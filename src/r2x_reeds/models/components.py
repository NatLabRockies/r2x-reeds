"""ReEDS component models."""

from __future__ import annotations

from typing import Annotated

from infrasys import SupplementalAttribute
from pydantic import Field, PositiveFloat, confloat

from r2x_core.units import HasUnits, Unit

from .base import FromTo_ToFrom, MinMax, ReEDSComponent
from .enums import EmissionSource, EmissionType, ReserveDirection, ReserveType


class ReEDSEmission(SupplementalAttribute):
    """ReEDS emission supplemental attribute."""

    rate: Annotated[float, Unit("kg/MWh"), Field(description="Emission rate for emission type in kg/MWh")]
    type: EmissionType
    source: EmissionSource = EmissionSource.COMBUSTION


class ReEDSRegion(ReEDSComponent):
    """ReEDS regional component.

    Represents a geographic region in the ReEDS model with various regional attributes and hierarchies.
    """

    state: Annotated[str | None, Field(description="State abbreviation")] = None
    nerc_region: Annotated[str | None, Field(description="NERC region")] = None
    transmission_region: Annotated[str | None, Field(description="Transmission planning region")] = None
    transmission_group: Annotated[str | None, Field(description="Transmission group")] = None
    interconnect: Annotated[
        str | None,
        Field(description="Interconnection (eastern, western, texas)"),
    ] = None
    country: Annotated[str | None, Field(description="Country code")] = None
    max_active_power: Annotated[float | None, Field(description="Peak demand in MW")] = None
    timezone: Annotated[str | None, Field(description="Time zone identifier")] = None
    cendiv: Annotated[str | None, Field(description="Census division")] = None
    usda_region: Annotated[str | None, Field(description="USDA region")] = None
    h2ptc_region: Annotated[str | None, Field(description="H2 PTC region")] = None
    hurdle_region: Annotated[str | None, Field(description="Hurdle rate region")] = None
    cc_region: Annotated[str | None, Field(description="Climate change region")] = None


class ReEDSReserveRegion(ReEDSComponent):
    """ReEDS reserve region component.

    Represents a geographic region for operating reserve requirements.
    """


class ReEDSReserve(ReEDSComponent):
    """ReEDS operating reserve component.

    Defines operating reserve requirements and parameters for the system.
    """

    time_frame: Annotated[
        PositiveFloat,
        Field(description="Timeframe in which the reserve is required in seconds"),
    ] = 1e30
    region: Annotated[
        ReEDSReserveRegion | None,
        Field(description="Reserve region where requirement applies"),
    ] = None
    vors: Annotated[
        float,
        Field(description="Value of reserve shortage in $/MW. Positive value acts as soft constraint"),
    ] = -1
    duration: Annotated[
        PositiveFloat | None,
        Field(description="Time over which the required response must be maintained in seconds"),
    ] = None
    or_load_percentage: Annotated[
        float | None,
        Field(description="Proportion of load that contributes to the reserve requirement"),
    ] = None
    or_wind_percentage: Annotated[
        float | None,
        Field(description="Proportion of wind generation that contributes to the reserve requirement"),
    ] = None
    or_pv_percentage: Annotated[
        float | None,
        Field(description="Proportion of solar generation that contributes to the reserve requirement"),
    ] = None
    season: Annotated[
        str | None,
        Field(description="Seasonal identifier for reserve requirement variations (summ/fall/wint/spri)"),
    ] = None
    reg_cost: Annotated[
        float | None,
        Field(description="Regulation reserve cost in $/MW from cost_opres files"),
    ] = None
    flex_cost: Annotated[
        float | None,
        Field(description="Flexibility reserve cost in $/MW from cost_opres files"),
    ] = None
    spin_cost: Annotated[
        float | None,
        Field(description="Spinning reserve cost in $/MW from cost_opres files"),
    ] = None
    reserve_type: Annotated[ReserveType, Field(description="Type of reserve")]
    direction: Annotated[ReserveDirection, Field(description="Direction of reserve provision")]


class ReEDSInterface(ReEDSComponent):
    """ReEDS region interface.

    Represents the connection between two regions for power transfer.
    """

    from_region: Annotated[ReEDSRegion, Field(description="Origin region")]
    to_region: Annotated[ReEDSRegion, Field(description="Destination region")]


class ReEDSGenerator(HasUnits, ReEDSComponent):
    """Base generator component with fields common to all generation types."""

    region: Annotated[ReEDSRegion, Field(description="ReEDS region")]
    technology: Annotated[str, Field(description="ReEDS technology type")]
    capacity: Annotated[PositiveFloat, Unit("MW"), Field(description="Installed capacity", ge=0)]
    heat_rate: Annotated[PositiveFloat | None, Unit("MMBtu/MWh"), Field(description="Heat rate")] = None
    fuel_type: Annotated[str | None, Field(description="Fuel type")] = None
    fuel_price: Annotated[PositiveFloat | None, Unit("$/MMBtu"), Field(description="Fuel price")] = None
    forced_outage_rate: Annotated[confloat(ge=0, le=1) | None, Field(description="Forced outage rate")] = None
    planned_outage_rate: Annotated[confloat(ge=0, le=1) | None, Field(description="Planned outage rate")] = (
        None
    )
    max_age: Annotated[int | None, Unit("years"), Field(description="Maximum age")] = None
    vom_cost: Annotated[PositiveFloat | None, Unit("$/MWh"), Field(description="Variable O&M")] = None
    fom_cost: Annotated[PositiveFloat | None, Unit("$/MW/year"), Field(description="Fixed O&M")] = None
    capital_cost: Annotated[PositiveFloat | None, Unit("$/MW"), Field(description="Capital cost")] = None
    vintage: Annotated[str | None, Field(description="Vintage bin identifier")] = None
    retirement_year: Annotated[int | None, Field(description="Planned retirement year")] = None


class ReEDSThermalGenerator(ReEDSGenerator):
    """Thermal generators with fuel combustion and heat rates."""

    heat_rate: Annotated[PositiveFloat, Unit("MMBtu/MWh"), Field(description="Heat rate")]
    fuel_type: Annotated[str, Field(description="Fuel type")]
    fuel_price: Annotated[PositiveFloat | None, Unit("$/MMBtu"), Field(description="Fuel price")] = None
    min_stable_level: Annotated[confloat(ge=0, le=1) | None, Field(description="Min load fraction")] = None
    ramp_rate: Annotated[PositiveFloat | None, Unit("fraction/hour"), Field(description="Ramp rate")] = None
    capacity_factor_range: MinMax | None = None
    startup_cost: Annotated[PositiveFloat | None, Unit("$/MW"), Field(description="Startup cost")] = None
    min_up_time: Annotated[PositiveFloat | None, Unit("hours"), Field(description="Min up time")] = None
    min_down_time: Annotated[PositiveFloat | None, Unit("hours"), Field(description="Min down time")] = None


class ReEDSVariableGenerator(ReEDSGenerator):
    """Renewable generators with capacity factor profiles."""

    resource_class: Annotated[str | None, Field(description="Resource class identifier")] = None
    inverter_loading_ratio: Annotated[PositiveFloat | None, Field(description="ILR for PV")] = None
    capacity_factor_adjustment: Annotated[PositiveFloat | None, Field(description="CF adjustment")] = None
    max_capacity_factor: Annotated[confloat(ge=0, le=1) | None, Field(description="Max CF")] = None
    supply_curve_cost: Annotated[
        PositiveFloat | None, Unit("$/MW"), Field(description="Supply curve cost")
    ] = None
    transmission_adder: Annotated[
        PositiveFloat | None, Unit("$/MW"), Field(description="Transmission adder")
    ] = None


class ReEDSStorage(ReEDSGenerator):
    """Storage technologies with energy/power characteristics."""

    storage_duration: Annotated[PositiveFloat, Unit("hours"), Field(description="Storage duration")]
    round_trip_efficiency: Annotated[confloat(ge=0, le=1), Field(description="Round-trip efficiency")]
    energy_capacity: Annotated[PositiveFloat | None, Unit("MWh"), Field(description="Energy capacity")] = None
    max_charge_rate: Annotated[PositiveFloat | None, Unit("MW"), Field(description="Max charge")] = None
    max_discharge_rate: Annotated[PositiveFloat | None, Unit("MW"), Field(description="Max discharge")] = None
    capital_cost_energy: Annotated[
        PositiveFloat | None, Unit("$/MWh"), Field(description="Energy capital cost")
    ] = None
    fom_cost_energy: Annotated[PositiveFloat | None, Unit("$/MWh/year"), Field(description="Energy FOM")] = (
        None
    )
    energy_vom_cost: Annotated[PositiveFloat | None, Unit("$/MWh"), Field(description="Energy VOM")] = None
    inverter_loading_ratio: Annotated[PositiveFloat | None, Field(description="ILR for hybrid")] = None


class ReEDSHydroGenerator(ReEDSGenerator):
    """Hydroelectric generators with monthly/daily energy budgets."""

    is_dispatchable: Annotated[bool, Field(description="Whether hydro is dispatchable")]
    flow_range: Annotated[MinMax | None, Unit("MW"), Field(description="Flow range")] = None
    ramp_rate: Annotated[PositiveFloat | None, Unit("fraction/hour"), Field(description="Ramp rate")] = None


class ReEDSConsumingTechnology(HasUnits, ReEDSComponent):
    """Technologies that consume electricity to produce other products."""

    region: Annotated[ReEDSRegion, Field(description="ReEDS region")]
    technology: Annotated[str, Field(description="Technology type")]
    capacity: Annotated[PositiveFloat, Unit("MW"), Field(description="Consumption capacity")]
    capital_cost: Annotated[PositiveFloat | None, Unit("$/kW"), Field(description="Capital cost")] = None
    fom_cost: Annotated[PositiveFloat | None, Unit("$/kW/year"), Field(description="Fixed O&M")] = None
    vom_cost: Annotated[PositiveFloat | None, Unit("$/MWh"), Field(description="Variable O&M")] = None
    electricity_efficiency: Annotated[
        PositiveFloat, Unit("kWh/kg"), Field(description="Electricity consumption rate")
    ]
    gas_efficiency: Annotated[
        PositiveFloat | None, Unit("MMBtu/kg"), Field(description="Gas consumption rate")
    ] = None
    storage_transport_adder: Annotated[
        PositiveFloat | None, Unit("$/kW"), Field(description="Infrastructure costs")
    ] = None
    vintage: Annotated[str | None, Field(description="Vintage bin identifier")] = None


class ReEDSH2Storage(HasUnits, ReEDSComponent):
    """H2 storage infrastructure."""

    region: Annotated[ReEDSRegion, Field(description="ReEDS region")]
    storage_type: Annotated[str, Field(description="Storage type")]
    capacity: Annotated[PositiveFloat, Unit("tonnes"), Field(description="Storage capacity")]
    capital_cost: Annotated[PositiveFloat | None, Unit("$/tonne"), Field(description="Capital cost")] = None
    fom_cost: Annotated[PositiveFloat | None, Unit("$/tonne/year"), Field(description="FOM")] = None
    parasitic_load: Annotated[PositiveFloat | None, Unit("kWh/kg"), Field(description="Parasitic load")] = (
        None
    )


class ReEDSH2Pipeline(HasUnits, ReEDSComponent):
    """H2 transmission pipeline."""

    from_region: Annotated[ReEDSRegion, Field(description="Origin region")]
    to_region: Annotated[ReEDSRegion, Field(description="Destination region")]
    capacity: Annotated[PositiveFloat, Unit("tonnes"), Field(description="Pipeline capacity")]
    distance_km: Annotated[PositiveFloat, Unit("km"), Field(description="Distance")]
    capital_cost_per_km: Annotated[
        PositiveFloat | None, Unit("$/tonne/km"), Field(description="Capital cost")
    ] = None
    fom_cost_per_km: Annotated[PositiveFloat | None, Unit("$/tonne/year/km"), Field(description="FOM")] = None


class ReEDSTransmissionLine(ReEDSComponent):
    """ReEDS transmission line component.

    Represents a transmission line connection between two regions.
    """

    interface: Annotated[ReEDSInterface, Field(description="Interface connecting two regions")]
    max_active_power: Annotated[FromTo_ToFrom, Field(description="Transfer capacity limit in MW")]
    losses: Annotated[
        float | None,
        Field(description="Transmission losses (fraction)"),
    ] = None
    line_type: Annotated[str | None, Field(description="Line type (AC/DC)")] = None
    voltage: Annotated[float | None, Field(description="Voltage level in kV")] = None
    distance_miles: Annotated[float | None, Field(description="Distance in miles")] = None
    line_cost_per_mw_mile: Annotated[
        float | None,
        Field(description="Cost per MW-mile"),
    ] = None
    hurdle_rate: Annotated[
        float | None,
        Field(description="Hurdle rate forward direction"),
    ] = None


class ReEDSDemand(ReEDSComponent):
    """ReEDS electrical demand component.

    Represents load/demand in a region.
    """

    region: Annotated[ReEDSRegion, Field(description="ReEDS region")]
    max_active_power: Annotated[
        float | None,
        Field(description="Maximum active power demand in MW"),
    ] = None


class ReEDSResourceClass(ReEDSComponent):
    """ReEDS supply curve resource component.

    Represents renewable resource potential in a region with
    associated costs and capacity factors.
    """

    technology: Annotated[str, Field(description="Technology type (e.g., 'upv', 'wind-ons')")]
    region: Annotated[ReEDSRegion, Field(description="ReEDS region")]
    resource_class: Annotated[str, Field(description="Resource class identifier")]
    capacity: Annotated[float, Field(description="Available capacity in MW")]
    capacity_factor: Annotated[
        float | None,
        Field(description="Average capacity factor"),
    ] = None
    cost_per_mw: Annotated[float | None, Field(description="Cost per MW")] = None
    fixed_om_per_mw: Annotated[
        float | None,
        Field(description="Fixed O&M per MW-year"),
    ] = None
    variable_om_per_mwh: Annotated[
        float | None,
        Field(description="Variable O&M per MWh"),
    ] = None
