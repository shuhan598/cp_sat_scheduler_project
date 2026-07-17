import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def test_run_schedule_uses_normal_flow_when_insert_is_disabled(monkeypatch):
    monkeypatch.setattr(
        main,
        "load_raw_orders_for_insert_from_json",
        lambda _: (["base-order"], [], {"enabled": False, "insert_date": None}),
    )

    def fake_normal_schedule(base_raw_orders):
        return {"output_file": "normal.xlsx", "orders": base_raw_orders}

    def fail_insert_schedule(**_kwargs):
        pytest.fail("insert schedule should not run")

    monkeypatch.setattr(main, "run_normal_schedule", fake_normal_schedule)
    monkeypatch.setattr(main, "run_insert_schedule", fail_insert_schedule)

    result = main.run_schedule()

    assert result == {"output_file": "normal.xlsx", "orders": ["base-order"]}


def test_run_schedule_uses_insert_flow_when_insert_is_enabled(monkeypatch):
    monkeypatch.setattr(
        main,
        "load_raw_orders_for_insert_from_json",
        lambda _: (
            ["base-order"],
            ["insert-order"],
            {"enabled": True, "insert_date": "2026-05-10"},
        ),
    )

    def fail_normal_schedule(_base_raw_orders):
        pytest.fail("normal schedule should not run")

    def fake_insert_schedule(base_raw_orders, inserted_raw_orders):
        return {
            "output_file": "insert.xlsx",
            "base_orders": base_raw_orders,
            "insert_orders": inserted_raw_orders,
        }

    monkeypatch.setattr(main, "run_normal_schedule", fail_normal_schedule)
    monkeypatch.setattr(main, "run_insert_schedule", fake_insert_schedule)

    result = main.run_schedule()

    assert result == {
        "output_file": "insert.xlsx",
        "base_orders": ["base-order"],
        "insert_orders": ["insert-order"],
    }


def test_run_schedule_and_get_excel_bytes_reads_generated_excel(monkeypatch):
    output_file = Path(__file__).resolve().parent / "fixtures" / "generated_result.xlsx"
    output_file.write_bytes(b"fake xlsx bytes")

    monkeypatch.setattr(
        main,
        "run_schedule",
        lambda *_args: {"output_file": str(output_file), "extra": "kept"},
    )

    try:
        response = main.run_schedule_and_get_excel_bytes()
    finally:
        output_file.unlink(missing_ok=True)

    assert response["success"] is True
    assert response["content"] == b"fake xlsx bytes"
    assert response["filename"] == "generated_result.xlsx"
    assert (
        response["content_type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response["schedule_result"] == {"output_file": str(output_file), "extra": "kept"}


def test_run_schedule_and_get_excel_bytes_returns_failure_when_no_solution(monkeypatch):
    monkeypatch.setattr(main, "run_schedule", lambda *_args: None)

    response = main.run_schedule_and_get_excel_bytes()

    assert response == {
        "success": False,
        "message": "未找到可行排产结果",
        "content": None,
        "filename": None,
        "content_type": None,
        "schedule_result": None,
    }
