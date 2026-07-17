import pandas as pd

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


def main():
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
    base_raw_orders, inserted_raw_orders, basic_insert_info = load_raw_orders_for_insert_from_json(
        INPUT_JSON_FILE,
    )

    # =========================
    # 普通排产：没有有效插单输入
    # =========================
    if not basic_insert_info["enabled"]:
        run_normal_schedule(base_raw_orders)
        return

    # =========================
    # 插单排产：检测到有效插单输入
    # =========================
    run_insert_schedule(
        base_raw_orders=base_raw_orders,
        inserted_raw_orders=inserted_raw_orders,
    )


if __name__ == "__main__":
    main()
