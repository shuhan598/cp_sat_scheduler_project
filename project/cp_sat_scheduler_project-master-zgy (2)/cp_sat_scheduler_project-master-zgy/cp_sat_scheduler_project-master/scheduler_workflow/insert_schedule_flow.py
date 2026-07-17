# =========================
# 文件说明：
# 这个文件负责插单排产流程。
#
# 主要职责：
# 1. 读取旧排产结果；
# 2. 构造旧计划读取所需的临时时间参数；
# 3. 读取旧计划和旧订单实际最后生产日；
# 4. 读取停电计划；
# 5. 执行插单模式下的自动跨月扩展求解；
# 6. 导出插单排产结果；
# 7. 打印插单处理方式统计。
# =========================

import pandas as pd

from config import (
    PREVIOUS_PLAN_EXCEL_FILE,
    FREEZE_DAYS_AFTER_INSERT,
    INSERT_OUTPUT_EXCEL_FILE,
)

from preprocessing.order_builder import (
    build_orders_for_insert_mode,
)

from preprocessing.date_utils import (
    add_months_to_month_end,
)

from preprocessing.schedule_context import (
    build_previous_plan_time_params,
    get_insert_extend_attempts,
    get_natural_period_end_date,
)

from scheduler_io.outage_loader import (
    read_power_outage_records,
)

from scheduler_io.previous_plan_loader import (
    find_previous_plan_file,
    load_previous_plan_with_finish_days_from_excel,
)

from scheduler_solve.schedule_runner import (
    run_single_schedule_attempt,
)

from scheduler_io.excel_exporter import (
    export_insert_to_excel,
    print_monthly_sheet_info,
)


def run_insert_schedule(base_raw_orders, inserted_raw_orders):
    """
    执行插单排产流程。

    参数：
        base_raw_orders:
            从“订单输入”sheet 读取到的原始订单数据。

        inserted_raw_orders:
            从“插单输入”sheet 读取到的原始插单数据。

    流程：
        1. 查找旧排产结果文件；
        2. 构造旧计划读取时间参数；
        3. 读取旧计划和旧订单实际最后生产日；
        4. 读取停电计划；
        5. 自动尝试不跨月、跨 1 个月、跨 2 个月等排产范围；
        6. 找到可行解后导出插单排产结果。
    """

    # =========================
    # 插单排产：读取旧排产计划
    # =========================
    print("\n检测到插单模式，本次启用旧计划冻结、自动插单识别与最小扰动重排。")

    previous_plan_file = find_previous_plan_file(PREVIOUS_PLAN_EXCEL_FILE)

    if previous_plan_file is None:
        raise FileNotFoundError(
            "启用插单模式时需要旧排产结果文件。"
            "请先运行一次普通排产，生成 CP_SAT_排产结果.xlsx。"
        )

    print(f"读取旧排产结果文件: {previous_plan_file}")

    # =========================
    # 构造旧计划读取时间参数
    # =========================
    #
    # 关键修正：
    # 这里必须把 previous_plan_file 传入 build_previous_plan_time_params。
    #
    # 原因：
    # 普通排产阶段可能因为停电、产能不足等原因已经自动跨月，
    # 例如旧结果文件中存在：
    #     5月排产图
    #     6月排产图
    #
    # 如果这里不传 previous_plan_file，
    # build_previous_plan_time_params 就只能根据“原订单 + 插单输入”的最晚交期
    # 来构造 previous_display_dates。
    #
    # 这样会导致旧计划实际已经排到 6 月，
    # 但插单读取旧计划时只读取到 5 月。
    #
    # 后果：
    # 1. previous_order_finish_day 计算不完整；
    # 2. 插单判断“加量 / 同名新批次”可能出错；
    # 3. 旧计划扰动判断范围不完整。
    (
        previous_model_start_date,
        previous_model_end_date,
        previous_model_horizon,
        previous_display_dates,
    ) = build_previous_plan_time_params(
        base_raw_orders=base_raw_orders,
        inserted_raw_orders=inserted_raw_orders,
        previous_plan_file=previous_plan_file,
    )

    previous_plan, previous_order_finish_day = load_previous_plan_with_finish_days_from_excel(
        previous_plan_file,
        model_start_date=previous_model_start_date,
        model_horizon=previous_model_horizon,
        display_dates=previous_display_dates,
    )

    print(f"成功读取旧计划单元格数: {len(previous_plan)}")

    print("\n旧计划中各订单实际最后生产日：")
    for order_name, finish_day in sorted(previous_order_finish_day.items()):
        finish_date = previous_model_start_date + pd.Timedelta(days=finish_day)
        print(f"{order_name}: 模型日 {finish_day}, 日期 {finish_date}")

    # =========================
    # 读取停电计划
    # =========================
    power_outages, has_power_outage = read_power_outage_records()

    # =========================
    # 插单模式：自动跨月扩展求解
    # =========================
    #
    # 业务逻辑：
    # 1. 先尝试在当前月份内完成插单重排；
    # 2. 如果无解，则自动扩展到下一个月份；
    # 3. 如果仍然无解，则继续扩展；
    # 4. 最多扩展到 MAX_AUTO_EXTEND_MONTHS_FOR_INSERT；
    # 5. 一旦找到可行解，就停止继续扩展。
    natural_period_end_date = get_natural_period_end_date(
        base_raw_orders=base_raw_orders,
        inserted_raw_orders=inserted_raw_orders,
    )

    attempts = get_insert_extend_attempts()

    solved_result = None
    solved_orders = None
    solved_model_start_date = None
    solved_model_end_date = None
    solved_model_horizon = None
    solved_display_dates = None
    solved_insert_info = None
    solved_freeze_until_day = None
    solved_extend_months = None

    for extend_months in attempts:
        if extend_months == 0:
            forced_model_end_date = None
            print("\n=== 插单求解尝试：不扩展月份，优先尝试在当前月份内完成 ===")
        else:
            forced_model_end_date = add_months_to_month_end(
                natural_period_end_date,
                extend_months,
            )
            print(
                f"\n=== 插单求解尝试：自动扩展 {extend_months} 个月，"
                f"模型结束日期扩展至 {forced_model_end_date} ==="
            )

        (
            orders,
            model_start_date,
            model_end_date,
            model_horizon,
            display_dates,
            insert_info,
        ) = build_orders_for_insert_mode(
            base_raw_orders=base_raw_orders,
            inserted_raw_orders=inserted_raw_orders,
            previous_order_finish_day=previous_order_finish_day,
            forced_model_end_date=forced_model_end_date,
        )

        insert_date = insert_info["insert_date"]
        insert_day_idx = (insert_date - model_start_date).days

        # 0：只冻结插单日期之前
        # 1：冻结插单日期之前 + 插单日期当天
        freeze_until_day = insert_day_idx - 1 + FREEZE_DAYS_AFTER_INSERT

        print("\n检测到插单模式，本次启用旧计划冻结与扰动惩罚。")
        print(f"插单日期: {insert_date}")
        print(f"插单日期对应模型日: {insert_day_idx}")
        print(f"FREEZE_DAYS_AFTER_INSERT = {FREEZE_DAYS_AFTER_INSERT}")

        if freeze_until_day >= 0:
            freeze_until_date = model_start_date + pd.Timedelta(days=freeze_until_day)
            print(f"冻结截止模型日: {freeze_until_day}")
            print(f"冻结截止日期: {freeze_until_date}")
        else:
            print("冻结截止模型日: 无")
            print("冻结截止日期: 无")

        result = run_single_schedule_attempt(
            orders=orders,
            model_start_date=model_start_date,
            model_end_date=model_end_date,
            model_horizon=model_horizon,
            display_dates=display_dates,
            power_outages=power_outages,
            has_power_outage=has_power_outage,
            enable_insert_mode=True,
            previous_plan=previous_plan,
            freeze_until_day=freeze_until_day,
            insert_info=insert_info,
        )

        if result is not None:
            solved_result = result
            solved_orders = orders
            solved_model_start_date = model_start_date
            solved_model_end_date = model_end_date
            solved_model_horizon = model_horizon
            solved_display_dates = display_dates
            solved_insert_info = insert_info
            solved_freeze_until_day = freeze_until_day
            solved_extend_months = extend_months
            break

    if solved_result is None:
        print("\n所有自动扩展尝试均未找到可行解。")

        if has_power_outage:
            print("注意：停电导致产能下降，可能进一步压缩可用产能。")

        print("建议检查：")
        print("1. 插单订单需求量是否过大；")
        print("2. 冻结计划是否过多；")
        print("3. 原订单和旧排产结果是否完全对应；")
        print("4. 是否需要继续增加 MAX_AUTO_EXTEND_MONTHS_FOR_INSERT。")

        return None

    # =========================
    # 导出 Excel
    # =========================
    output_file = export_insert_to_excel(
        order_df=solved_result["order_df"],
        new_calendar_df=solved_result["calendar_df"],
        new_detail_df=solved_result["detail_df"],
        machine_df=solved_result.get("machine_df"),
        date_machine_df=solved_result.get("date_machine_df"),
        previous_plan_file=previous_plan_file,
        output_file=INSERT_OUTPUT_EXCEL_FILE,
    )

    print(f"\n插单排产结果已导出到 Excel：{output_file}")
    print("Sheet 1：表1_订单视图")
    print_monthly_sheet_info(solved_display_dates)

    if solved_extend_months == 0:
        print("\n本次插单重排未跨月扩展。")
    else:
        print(f"\n本次插单重排自动扩展了 {solved_extend_months} 个月。")
        print(f"扩展后模型结束日期: {solved_model_end_date}")

    print("\n插单处理方式统计：")
    process_type_count = {}

    for order in solved_orders:
        process_type = order.get("insert_process_type", "原订单")
        process_type_count[process_type] = process_type_count.get(process_type, 0) + 1

    for process_type, count in process_type_count.items():
        print(f"{process_type}: {count}")

    return {
        "output_file": output_file,
        "result": solved_result,
        "orders": solved_orders,
        "model_start_date": solved_model_start_date,
        "model_end_date": solved_model_end_date,
        "model_horizon": solved_model_horizon,
        "display_dates": solved_display_dates,
        "insert_info": solved_insert_info,
        "freeze_until_day": solved_freeze_until_day,
        "extend_months": solved_extend_months,
        "previous_plan_file": previous_plan_file,
        "previous_plan": previous_plan,
        "previous_order_finish_day": previous_order_finish_day,
        "power_outages": power_outages,
        "has_power_outage": has_power_outage,
    }