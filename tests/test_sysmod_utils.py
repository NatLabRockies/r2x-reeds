from __future__ import annotations


def test_deduplicate_records_warns_and_keeps_first(caplog):
    from r2x_reeds.sysmod.utils import _deduplicate_records

    records = [
        {"name": "battery", "avg_capacity_MW": 10},
        {"name": "battery", "avg_capacity_MW": 12},
        {"name": "wind", "avg_capacity_MW": 40},
    ]

    result = _deduplicate_records(records, key="name")

    assert len(result) == 2
    assert result[0]["avg_capacity_MW"] == 10
    assert "Duplicate entries found for key 'name'" in caplog.text
