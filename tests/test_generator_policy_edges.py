"""Public generator preparation regressions using real ReEDS input files."""

import shutil
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from r2x_core import PluginError
from r2x_reeds import ReEDSConfig
from r2x_reeds.models import ReEDSGenerator, ReEDSStorage, ReEDSThermalGenerator, ReEDSVariableGenerator
from tests.test_parser_current_core import build_generator_system

pytestmark = [pytest.mark.integration, pytest.mark.polars]


@pytest.fixture
def generator_run_path(reeds_run_path: Path, tmp_path: Path) -> Iterator[Path]:
    """Release each test's copied run after exercising the public parser."""
    with TemporaryDirectory(prefix="generators-", dir=tmp_path) as directory:
        run_path = Path(directory) / "run"
        shutil.copytree(reeds_run_path, run_path)
        yield run_path


def test_configured_capacity_source_selects_degradation_adjusted_values(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    outputs = generator_run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value,fuel_type\nGas-CC,init-1,p1,2032,100,gas\n"
    )
    (outputs / "cap_deg_ivrt.csv").write_text(
        "i,v,r,t,Value,fuel_type\nGas-CC,init-1,p1,2032,250,gas\n"
    )

    system = build_generator_system(
        generator_run_path,
        config=reeds_config,
        capacity_source="online_capacity_degraded",
    )

    generator = next(iter(system.get_components(ReEDSThermalGenerator)))
    assert generator.capacity == 250.0


def test_missing_configured_capacity_source_does_not_fall_back(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    (generator_run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n"
    )
    (generator_run_path / "outputs" / "cap_deg_ivrt.csv").unlink(missing_ok=True)

    with pytest.raises(PluginError) as captured:
        build_generator_system(
            generator_run_path,
            config=reeds_config,
            capacity_source="online_capacity_degraded",
            required_capacity_source=True,
        )

    assert isinstance(captured.value.__cause__, FileNotFoundError)
    assert "cap_deg_ivrt.csv" in str(captured.value.__cause__)


def test_inline_fuel_type_satisfies_thermal_mapping_without_fuel_map(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    outputs = generator_run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value,fuel_type\nGas-CC,init-1,p1,2032,100,GAS\n"
    )
    (outputs / "fuel2tech.csv").unlink(missing_ok=True)

    system = build_generator_system(generator_run_path, config=reeds_config)

    generator = next(iter(system.get_components(ReEDSThermalGenerator)))
    assert generator.fuel_type == "gas"


def test_unresolved_thermal_fuel_requires_the_physical_mapping(generator_run_path: Path) -> None:
    (generator_run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n"
    )
    (generator_run_path / "outputs" / "fuel2tech.csv").unlink(missing_ok=True)

    with pytest.raises(PluginError) as captured:
        build_generator_system(generator_run_path, config=ReEDSConfig(solve_year=2032, weather_year=2012))

    assert isinstance(captured.value.__cause__, FileNotFoundError)
    assert "fuel2tech.csv" in str(captured.value.__cause__)


def test_present_empty_fuel_mapping_is_valid_and_uses_other_fallback(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    (generator_run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n"
    )
    (generator_run_path / "outputs" / "fuel2tech.csv").write_text("f,i,Value\n")

    system = build_generator_system(generator_run_path, config=reeds_config)

    generator = next(iter(system.get_components(ReEDSThermalGenerator)))
    assert generator.fuel_type == "OTHER"


def test_generator_category_patterns_are_case_insensitive(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    (generator_run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n"
    )
    category_patterns: list[dict[str, object]] = [
        {
            "priority": 0,
            "category": "thermal",
            "match_kind": "prefix",
            "pattern": "GAS-CC",
            "is_dispatchable": False,
            "unsupported": False,
        }
    ]

    system = build_generator_system(
        generator_run_path, config=reeds_config, generator_category_patterns=category_patterns
    )

    thermal = list(system.get_components(ReEDSThermalGenerator))
    assert [(generator.technology, generator.capacity) for generator in thermal] == [("gas-cc", 100.0)]


def test_category_classification_keeps_all_repeated_technology_capacity_rows(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    (generator_run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\nGas-CC,init-2,p3,2032,200\n"
    )

    system = build_generator_system(generator_run_path, config=reeds_config)

    generators = sorted(
        system.get_components(ReEDSThermalGenerator),
        key=lambda generator: generator.name,
    )
    assert [(generator.name, generator.region.name, generator.vintage, generator.capacity) for generator in generators] == [
        ("gas-cc_init-1_p1", "p1", "init-1", 100.0),
        ("gas-cc_init-2_p3", "p3", "init-2", 200.0),
    ]


def test_only_the_highest_priority_generator_category_controls_unsupported_policy(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    (generator_run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\ngas-cc,init-1,p1,2032,100\n"
    )
    category_patterns: list[dict[str, object]] = [
        {
            "priority": 0,
            "category": "wind",
            "match_kind": "prefix",
            "pattern": "gas-cc",
            "is_dispatchable": False,
            "unsupported": False,
        },
        {
            "priority": 1,
            "category": "hydrogen",
            "match_kind": "prefix",
            "pattern": "gas",
            "is_dispatchable": False,
            "unsupported": True,
        },
    ]

    system = build_generator_system(
        generator_run_path, config=reeds_config, generator_category_patterns=category_patterns
    )

    variable = list(system.get_components(ReEDSVariableGenerator))
    assert [(generator.technology, generator.capacity) for generator in variable] == [("gas-cc", 100.0)]


def test_thermal_heat_rate_fill_is_grouped_by_vintage_and_does_not_fill_renewables(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    """Known rates, same-vintage means, and the thermal default stay distinct."""
    outputs = generator_run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\n"
        "Gas-CC,init-1,p1,2032,100\n"
        "Gas-CC,init-1,p3,2032,200\n"
        "Gas-CC,init-2,p1,2032,50\n"
        "upv_1,new1,p1,2032,25\n"
    )
    (outputs / "heat_rate.csv").write_text(
        "i,v,r,t,Value\n"
        "Gas-CC,init-1,p1,2032,12\n"
        "Gas-CC,init-1,p3,2032,\n"
        "Gas-CC,init-2,p1,2032,\n"
        "upv_1,new1,p1,2032,\n"
    )
    (generator_run_path / "inputs_case" / "ramprate.csv").write_text("Gas-CC,0.25\n")

    system = build_generator_system(generator_run_path, config=reeds_config)

    thermal = {generator.name: generator for generator in system.get_components(ReEDSThermalGenerator)}
    assert set(thermal) == {"gas-cc_init-1_p1", "gas-cc_init-1_p3", "gas-cc_init-2_p1"}
    assert thermal["gas-cc_init-1_p1"].heat_rate == 12.0
    assert thermal["gas-cc_init-1_p3"].heat_rate == 12.0
    assert thermal["gas-cc_init-2_p1"].heat_rate == 10.0
    assert all(generator.ramp_rate == 0.25 for generator in thermal.values())
    assert sum(generator.capacity for generator in thermal.values()) == 350.0
    renewable = list(system.get_components(ReEDSVariableGenerator))
    assert len(renewable) == 1
    assert renewable[0].technology == "upv_1"
    assert renewable[0].capacity == 25.0
    assert renewable[0].heat_rate is None
    assert len(list(system.get_components(ReEDSGenerator))) == 4


def test_configured_default_heat_rate_fills_missing_thermal_values(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    """The instance defaults override the thermal heat-rate fallback."""
    outputs = generator_run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n")
    (outputs / "heat_rate.csv").unlink()

    system = build_generator_system(generator_run_path, config=reeds_config, default_heat_rate=14.5)

    generator = next(iter(system.get_components(ReEDSThermalGenerator)))
    assert generator.heat_rate == 14.5


@pytest.mark.parametrize(
    "efficiency_available", [True, False], ids=["known-efficiency", "default-efficiency"]
)
def test_storage_duration_uses_technology_value_then_unit_value_and_omits_unknowns(
    generator_run_path: Path, reeds_config: ReEDSConfig, efficiency_available: bool
) -> None:
    """The detailed output fills missing duration without overwriting known duration."""
    outputs = generator_run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\n"
        "battery_4,init-1,p1,2032,100\n"
        "battery_6,init-1,p1,2032,200\n"
        "battery_8,init-1,p1,2032,300\n"
    )
    (outputs / "storage_duration.csv").write_text("i,value\nbattery_4,4\nbattery_6,\nbattery_8,\n")
    (outputs / "storage_duration_out.csv").write_text(
        "i,v,r,t,Value\nbattery_4,init-1,p1,2032,9\nbattery_6,init-1,p1,2032,6\nbattery_8,init-1,p1,2032,\n"
    )
    if efficiency_available:
        (outputs / "storage_eff.csv").write_text(
            "i,t,Value\nbattery_4,2032,0.8\nbattery_6,2032,0.7\nbattery_8,2032,0.9\n"
        )
    else:
        (outputs / "storage_eff.csv").unlink()

    system = build_generator_system(generator_run_path, config=reeds_config)

    storage = {generator.technology: generator for generator in system.get_components(ReEDSStorage)}
    assert set(storage) == {"battery_4", "battery_6"}
    assert storage["battery_4"].storage_duration == 4.0
    assert storage["battery_6"].storage_duration == 6.0
    assert storage["battery_4"].round_trip_efficiency == (0.8 if efficiency_available else 1.0)
    assert storage["battery_6"].round_trip_efficiency == (0.7 if efficiency_available else 1.0)
    assert storage["battery_4"].capacity == 100.0
    assert storage["battery_6"].capacity == 200.0


def test_exact_fuel_mapping_precedes_base_technology_fallback(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    """An exact technology match takes precedence over conflicting base mappings."""
    outputs = generator_run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC_case,init-1,p1,2032,100\n")
    (outputs / "heat_rate.csv").write_text("i,v,r,t,Value\nGas-CC_case,init-1,p1,2032,10\n")
    (outputs / "fuel2tech.csv").write_text(
        "f,i,Value\nNATURALGAS,Gas-CC,True\nOIL,Gas-CC_z,True\nGAS,Gas-CC_case,True\n"
    )

    system = build_generator_system(generator_run_path, config=reeds_config)

    generator = next(iter(system.get_components(ReEDSThermalGenerator)))
    assert generator.technology == "gas-cc_case"
    assert generator.fuel_type == "gas"


def test_fuel_base_mapping_sort_can_be_overridden_by_instance_config(
    generator_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    """The instance file mapping controls the tie-breaker for base technology matches."""
    outputs = generator_run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC_case,init-1,p1,2032,100\n")
    (outputs / "fuel2tech.csv").write_text("f,i,Value\nNATURALGAS,Gas-CC,True\nH2CT,Gas-CC_H2-CT,True\n")

    system = build_generator_system(generator_run_path, config=reeds_config, fuel_base_sort="asc")

    generator = next(iter(system.get_components(ReEDSThermalGenerator)))
    assert generator.fuel_type == "naturalgas"


@pytest.mark.parametrize(
    ("source_fuel", "mapped_technology", "expected_fuel"),
    [("NATURALGAS", "Gas-CC", "naturalgas"), ("COAL", "coal", "OTHER")],
    ids=["base-technology-fuel", "unmapped-thermal-fuel"],
)
def test_fuel_mapping_uses_base_technology_and_defaults_only_unmapped_thermal_rows(
    generator_run_path: Path,
    reeds_config: ReEDSConfig,
    source_fuel: str,
    mapped_technology: str,
    expected_fuel: str,
) -> None:
    """Suffixes do not break fuel matching or change exact-technology fuel prices."""
    outputs = generator_run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC_case,init-1,p1,2032,100\n")
    (outputs / "heat_rate.csv").write_text("i,v,r,t,Value\nGas-CC_case,init-1,p1,2032,10\n")
    (outputs / "fuel_price.csv").write_text("i,r,t,Value\nGas-CC_case,p1,2032,7\n")
    (outputs / "fuel2tech.csv").write_text(f"f,i,Value\n{source_fuel},{mapped_technology},c_bool(True)\n")

    system = build_generator_system(generator_run_path, config=reeds_config)

    generators = list(system.get_components(ReEDSThermalGenerator))
    assert len(generators) == 1
    assert generators[0].technology == "gas-cc_case"
    assert generators[0].name == "gas-cc_case_init-1_p1"
    assert generators[0].fuel_type == expected_fuel
    assert generators[0].fuel_price == 7.0
    assert generators[0].capacity == 100.0
