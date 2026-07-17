import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scheduler_io.data_loader import load_raw_orders_for_insert_from_json


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def fixture_path(name):
    return FIXTURES_DIR / name


def test_loads_base_orders_from_json():
    base_orders, inserted_orders, insert_info = load_raw_orders_for_insert_from_json(
        fixture_path("base_orders.json")
    )

    assert len(base_orders) == 1
    assert inserted_orders == []
    assert insert_info == {"enabled": False, "insert_date": None}
    assert base_orders[0]["name"] == "意诚"
    assert base_orders[0]["quantity"] == 5700000
    assert base_orders[0]["earliest_start_date"] == date(2026, 5, 1)
    assert base_orders[0]["latest_finish_date"] == date(2026, 5, 7)
    assert base_orders[0]["insert_process_type"] == "原订单"


def test_loads_insert_orders_from_json():
    _, inserted_orders, insert_info = load_raw_orders_for_insert_from_json(
        fixture_path("insert_orders.json")
    )

    assert len(inserted_orders) == 1
    assert insert_info == {"enabled": True, "insert_date": date(2026, 5, 10)}
    assert inserted_orders[0]["name"] == "宥阳"
    assert inserted_orders[0]["is_inserted"] is True
    assert inserted_orders[0]["insert_date"] == date(2026, 5, 10)
    assert inserted_orders[0]["insert_process_type"] == "插单输入"


def test_missing_required_field_raises_value_error():
    with pytest.raises(ValueError, match="JSON.*latest_finish"):
        load_raw_orders_for_insert_from_json(fixture_path("missing_required_field.json"))


def test_invalid_date_range_raises_value_error():
    with pytest.raises(ValueError, match="最早开工日期晚于最晚完工日期"):
        load_raw_orders_for_insert_from_json(fixture_path("invalid_date_range.json"))
