"""Executable limits of the ReEDS parser's actual configuration loader."""

import json
import shutil
from pathlib import Path

import pytest

from r2x_core import Rule
from r2x_reeds import ReEDSConfig

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "operation,exception,error",
    [
        ("join", TypeError, "unexpected keyword argument 'joins'"),
        ("multi-field", ValueError, "requires a getter function"),
        ("coalesce", Exception, "Invalid getter type"),
    ],
)
def test_reeds_rule_loader_requires_supported_operations(
    tmp_path: Path, operation: str, exception: type[Exception], error: str
) -> None:
    original = ReEDSConfig(solve_year=2032, weather_year=2012)
    config_path = tmp_path / "config"
    shutil.copytree(original.config_path, config_path)
    path = config_path / "parser_rules.json"
    records = json.loads(path.read_text())
    if operation == "join":
        records[0]["joins"] = [{"dataset": "fom_hydro", "on": ["technology", "region"]}]
    elif operation == "multi-field":
        records[0]["field_map"]["fom_cost"] = ["fom_cost", "hydro_fom_cost"]
        records[0]["getters"].pop("fom_cost", None)
    else:
        records[0]["getters"]["fom_cost"] = {"coalesce": ["hydro_fom_cost", "fom_cost"]}
    path.write_text(json.dumps(records))
    assets = ReEDSConfig.load_config(config_path=config_path)
    with pytest.raises(exception, match=error):
        Rule.from_records(assets["parser_rules"])
