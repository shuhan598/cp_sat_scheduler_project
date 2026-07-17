import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scheduler_io import outage_loader
from scheduler_io.outage_loader import (
    load_power_outages_from_json,
    read_power_outage_records,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def fixture_path(name):
    return FIXTURES_DIR / name


def test_loads_power_outages_from_json():
    records = load_power_outages_from_json(fixture_path("power_outages.json"))

    assert records == [
        {
            "start_date": date(2026, 5, 8),
            "end_date": date(2026, 5, 10),
            "lines": [0, 1, 2],
            "pre_outage_ratio": 0.8,
        }
    ]


def test_missing_power_outages_defaults_to_empty_list():
    assert load_power_outages_from_json(fixture_path("base_orders.json")) == []


def test_invalid_power_outage_date_range_raises_value_error():
    with pytest.raises(ValueError, match="停电开始日期晚于停电结束日期"):
        load_power_outages_from_json(fixture_path("invalid_power_outage_range.json"))


def test_read_power_outage_records_uses_input_json(monkeypatch):
    monkeypatch.setattr(outage_loader, "INPUT_JSON_FILE", fixture_path("power_outages.json"))

    records, enabled = read_power_outage_records()

    assert enabled is True
    assert records[0]["lines"] == [0, 1, 2]
