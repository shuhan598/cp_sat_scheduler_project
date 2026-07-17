import pandas as pd
from pathlib import Path

from config import (
    INPUT_JSON_FILE,
)

from scheduler_io.data_loader import (
    load_raw_orders_for_insert_from_json,
)

from scheduler_workflow.normal_schedule_flow import (
    run_normal_schedule,
)

from scheduler_workflow.insert_schedule_flow import (
    run_insert_schedule,
)

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 300)
pd.set_option("display.max_rows", None)

EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def run_schedule(input_json_file=INPUT_JSON_FILE):
    """
    Run scheduling and return the workflow result.

    The returned dict contains output_file when a feasible schedule is found.
    Backend integrations can call this function instead of parsing console output.
    """
    print("开始读取 JSON 订单数据...")

    # =========================
    # 读取普通订单和插单输入
    # =========================
    #
    # 逻辑：
    # 1. 从 input_orders.json 读取 orders 和 insert_orders；
    # 2. 暂不直接判断插单是“加量 / 新单 / 同名新批次”；
    # 3. 如果检测到插单，则进入插单排产流程；
    # 4. 插单流程内部会读取旧排产计划，并自动判断插单类型。
    base_raw_orders, inserted_raw_orders, basic_insert_info = (
        load_raw_orders_for_insert_from_json(
            input_json_file,
        )
    )

    # =========================
    # 普通排产：没有有效插单输入
    # =========================
    if not basic_insert_info["enabled"]:
        return run_normal_schedule(base_raw_orders)

    # =========================
    # 插单排产：检测到有效插单输入
    # =========================
    return run_insert_schedule(
        base_raw_orders=base_raw_orders,
        inserted_raw_orders=inserted_raw_orders,
    )


def run_schedule_and_get_excel_bytes(input_json_file=INPUT_JSON_FILE):
    """
    Run scheduling and return the generated Excel file as bytes.

    content is the binary byte stream the backend asked for.
    """
    result = run_schedule(input_json_file)

    if result is None:
        return {
            "success": False,
            "message": "未找到可行排产结果",
            "content": None,
            "filename": None,
            "content_type": None,
            "schedule_result": None,
        }

    output_file = Path(result["output_file"])

    with output_file.open("rb") as file:
        content = file.read()

    return {
        "success": True,
        "message": "排产成功",
        "content": content,
        "filename": output_file.name,
        "content_type": EXCEL_CONTENT_TYPE,
        "schedule_result": result,
    }


def main():
    result = run_schedule()

    if result is not None:
        print(f"输出文件: {result['output_file']}")


if __name__ == "__main__":
    main()
