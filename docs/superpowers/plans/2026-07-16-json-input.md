# JSON Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace order and insert-order Excel input with `input_orders.json` and document the JSON request interface.

**Architecture:** The JSON loader will produce the same `raw_orders` list dictionaries as the existing Excel loader. `main.py` will switch to the JSON loader while downstream scheduling workflows and Excel result exports remain unchanged.

**Tech Stack:** Python standard library `json`, existing `pandas` date parsing utilities, pytest for loader tests, Markdown documentation.

---

### Task 1: JSON Loader Tests

**Files:**
- Create: `tests/test_json_data_loader.py`
- Modify: none
- Test: `tests/test_json_data_loader.py`

- [ ] **Step 1: Write failing tests**

```python
import json
from datetime import date

import pytest

from scheduler_io.data_loader import load_raw_orders_for_insert_from_json


def write_json(tmp_path, payload):
    path = tmp_path / "input_orders.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_loads_base_orders_from_json(tmp_path):
    path = write_json(tmp_path, {
        "orders": [
            {
                "order": "意诚",
                "quantity": 5700000,
                "earliest_start": "2026-05-01",
                "latest_finish": "2026-05-07",
            }
        ]
    })

    base_orders, inserted_orders, insert_info = load_raw_orders_for_insert_from_json(path)

    assert len(base_orders) == 1
    assert inserted_orders == []
    assert insert_info == {"enabled": False, "insert_date": None}
    assert base_orders[0]["name"] == "意诚"
    assert base_orders[0]["quantity"] == 5700000
    assert base_orders[0]["earliest_start_date"] == date(2026, 5, 1)
    assert base_orders[0]["latest_finish_date"] == date(2026, 5, 7)
    assert base_orders[0]["insert_process_type"] == "原订单"


def test_loads_insert_orders_from_json(tmp_path):
    path = write_json(tmp_path, {
        "orders": [
            {
                "order": "意诚",
                "quantity": "5700000",
                "earliest_start": "2026-05-01",
                "latest_finish": "2026-05-07",
            }
        ],
        "insert_orders": [
            {
                "order": "宥阳",
                "quantity": 2000000,
                "insert_date": "2026-05-10",
                "earliest_start": "2026-05-10",
                "latest_finish": "2026-05-20",
            }
        ],
    })

    _, inserted_orders, insert_info = load_raw_orders_for_insert_from_json(path)

    assert len(inserted_orders) == 1
    assert insert_info == {"enabled": True, "insert_date": date(2026, 5, 10)}
    assert inserted_orders[0]["name"] == "宥阳"
    assert inserted_orders[0]["is_inserted"] is True
    assert inserted_orders[0]["insert_date"] == date(2026, 5, 10)
    assert inserted_orders[0]["insert_process_type"] == "插单输入"


def test_missing_required_field_raises_value_error(tmp_path):
    path = write_json(tmp_path, {
        "orders": [
            {
                "order": "意诚",
                "quantity": 5700000,
                "earliest_start": "2026-05-01",
            }
        ]
    })

    with pytest.raises(ValueError, match="JSON.*latest_finish"):
        load_raw_orders_for_insert_from_json(path)


def test_invalid_date_range_raises_value_error(tmp_path):
    path = write_json(tmp_path, {
        "orders": [
            {
                "order": "意诚",
                "quantity": 5700000,
                "earliest_start": "2026-05-08",
                "latest_finish": "2026-05-07",
            }
        ]
    })

    with pytest.raises(ValueError, match="最早开工日期晚于最晚完工日期"):
        load_raw_orders_for_insert_from_json(path)
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_json_data_loader.py -q`

Expected: collection fails because `load_raw_orders_for_insert_from_json` does not exist.

### Task 2: JSON Loader Implementation

**Files:**
- Modify: `scheduler_io/data_loader.py`
- Test: `tests/test_json_data_loader.py`

- [ ] **Step 1: Add JSON parsing helpers**

Add `import json` and functions that validate JSON objects and convert each order into the existing raw order dictionary shape.

- [ ] **Step 2: Run JSON loader tests**

Run: `pytest tests/test_json_data_loader.py -q`

Expected: all tests pass.

### Task 3: Main Entry Switch

**Files:**
- Modify: `config.py`
- Modify: `main.py`
- Create: `input_orders.json`

- [ ] **Step 1: Add config constant**

Add `INPUT_JSON_FILE = "input_orders.json"` near the existing input file constants.

- [ ] **Step 2: Switch main loader**

Update `main.py` to print JSON-oriented messages and call `load_raw_orders_for_insert_from_json(INPUT_JSON_FILE)`.

- [ ] **Step 3: Add sample JSON input**

Create `input_orders.json` with the sample orders from the previous README examples and an empty `insert_orders` array.

### Task 4: Interface Documentation

**Files:**
- Create: `docs/input_json_api.md`
- Modify: `README.md`

- [ ] **Step 1: Create API document**

Document request file name, root fields, base order fields, insert order fields, validation rules, and examples.

- [ ] **Step 2: Update README**

Replace order input Excel language with JSON input language while leaving Excel output and power outage Excel notes intact.

### Task 5: Verification

**Files:**
- Test: `tests/test_json_data_loader.py`
- Runtime check: `main.py`

- [ ] **Step 1: Run unit tests**

Run: `pytest tests/test_json_data_loader.py -q`

Expected: all tests pass.

- [ ] **Step 2: Run application smoke test**

Run: `python main.py`

Expected: application reads `input_orders.json`, runs normal scheduling when `insert_orders` is empty, and exports `CP_SAT_排产结果.xlsx`.

- [ ] **Step 3: Review documentation**

Open `docs/input_json_api.md` and `README.md` to confirm they consistently describe JSON order input and Excel result output.
