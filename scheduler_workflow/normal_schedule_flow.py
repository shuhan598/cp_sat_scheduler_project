# =========================
# 文件说明：
# 这个文件负责普通排产流程。
#
# 主要职责：
# 1. 将原始订单数据构建成模型订单；
# 2. 读取停电计划；
# 3. 执行普通排产求解；
# 4. 普通停电排产无解时，支持自动扩展月份并启用软交期；
# 5. 导出普通排产 Excel；
# 6. 打印导出的 Sheet 信息。
# =========================

from config import (
    ENABLE_SOFT_DUE_FOR_OUTAGE,
    MAX_AUTO_EXTEND_MONTHS_FOR_OUTAGE,
)

from preprocessing.order_builder import (
    build_orders_from_raw_orders,
)

from preprocessing.date_utils import (
    add_months_to_month_end,
)

from scheduler_io.outage_loader import (
    read_power_outage_records,
)

from scheduler_solve.schedule_runner import (
    run_single_schedule_attempt,
)

from scheduler_io.excel_exporter import (
    export_to_excel,
    print_monthly_sheet_info,
)


def run_normal_schedule(base_raw_orders):
    """
    执行普通排产流程。

    参数：
        base_raw_orders:
            从“订单输入”sheet 读取到的原始订单数据。

    流程：
        1. 读取停电计划；
        2. 如果没有停电，执行普通硬交期排产；
        3. 如果有停电，启用软交期；
        4. 停电排产无解时，自动扩展月份继续尝试；
        5. 导出普通排产结果。
    """

    print("\n未启用插单模式，本次执行普通排产。")

    power_outages, has_power_outage = read_power_outage_records()

    # =========================
    # 无停电，或者配置中不启用停电软交期：
    # 保持原普通排产逻辑
    # =========================
    if not has_power_outage or not ENABLE_SOFT_DUE_FOR_OUTAGE:
        (
            orders,
            model_start_date,
            model_end_date,
            model_horizon,
            display_dates,
        ) = build_orders_from_raw_orders(
            raw_orders=base_raw_orders,
            forced_model_end_date=None,
            global_insert_date=None,
        )

        result = run_single_schedule_attempt(
            orders=orders,
            model_start_date=model_start_date,
            model_end_date=model_end_date,
            model_horizon=model_horizon,
            display_dates=display_dates,
            power_outages=power_outages,
            has_power_outage=has_power_outage,
            enable_insert_mode=False,
            enable_soft_due=False,
        )

        if result is None:
            return None

        # =========================
        # 导出 Excel
        # =========================
        output_file = export_to_excel(
            result["order_df"],
            result["calendar_df"],
            result["detail_df"],
        )

        print(f"\n排产结果已全部导出到 Excel：{output_file}")
        print("Sheet 1：表1_订单视图")
        print_monthly_sheet_info(display_dates)

        return {
            "output_file": output_file,
            "result": result,
            "orders": orders,
            "model_start_date": model_start_date,
            "model_end_date": model_end_date,
            "model_horizon": model_horizon,
            "display_dates": display_dates,
            "power_outages": power_outages,
            "has_power_outage": has_power_outage,
            "enable_soft_due": False,
            "extend_months": 0,
        }

    # =========================
    # 有停电：
    # 启用软交期 + 自动扩展月份
    # =========================
    print("\n检测到停电计划，普通排产启用软交期与自动跨月扩展。")

    (
        base_orders,
        base_model_start_date,
        natural_model_end_date,
        base_model_horizon,
        base_display_dates,
    ) = build_orders_from_raw_orders(
        raw_orders=base_raw_orders,
        forced_model_end_date=None,
        global_insert_date=None,
    )

    solved_result = None
    solved_orders = None
    solved_model_start_date = None
    solved_model_end_date = None
    solved_model_horizon = None
    solved_display_dates = None
    solved_extend_months = None
    solved_attempt_type = None

    # =========================
    # 普通停电模式下的分阶段求解尝试
    # =========================
    #
    # 业务逻辑：
    # 1. 先尝试在原交期内完成；
    # 2. 如果原交期内无解，再尝试在当前月份月末前完成；
    # 3. 如果当前月份内仍无解，再继续自动扩展到后续月份；
    # 4. 这样可以避免原交期无解后，直接从 5 月 8 日跳到 6 月 30 日。
    outage_attempts = [
        {
            "attempt_type": "original_due",
            "forced_model_end_date": None,
            "extend_months": 0,
        },
        {
            "attempt_type": "current_month",
            "forced_model_end_date": add_months_to_month_end(
                natural_model_end_date,
                0,
            ),
            "extend_months": 0,
        },
    ]

    for extend_months in range(1, MAX_AUTO_EXTEND_MONTHS_FOR_OUTAGE + 1):
        outage_attempts.append({
            "attempt_type": "extended_month",
            "forced_model_end_date": add_months_to_month_end(
                natural_model_end_date,
                extend_months,
            ),
            "extend_months": extend_months,
        })

    for attempt in outage_attempts:
        attempt_type = attempt["attempt_type"]
        forced_model_end_date = attempt["forced_model_end_date"]
        extend_months = attempt["extend_months"]

        if attempt_type == "original_due":
            print("\n=== 普通停电求解尝试：优先尝试在原交期内完成 ===")
        elif attempt_type == "current_month":
            print(
                f"\n=== 普通停电求解尝试：原交期内无解，"
                f"继续尝试在当前月份月末 {forced_model_end_date} 前完成 ==="
            )
        else:
            print(
                f"\n=== 普通停电求解尝试：自动扩展 {extend_months} 个月，"
                f"模型结束日期扩展至 {forced_model_end_date} ==="
            )

        (
            orders,
            model_start_date,
            model_end_date,
            model_horizon,
            display_dates,
        ) = build_orders_from_raw_orders(
            raw_orders=base_raw_orders,
            forced_model_end_date=forced_model_end_date,
            global_insert_date=None,
        )

        result = run_single_schedule_attempt(
            orders=orders,
            model_start_date=model_start_date,
            model_end_date=model_end_date,
            model_horizon=model_horizon,
            display_dates=display_dates,
            power_outages=power_outages,
            has_power_outage=has_power_outage,
            enable_insert_mode=False,
            enable_soft_due=True,
        )

        if result is not None:
            solved_result = result
            solved_orders = orders
            solved_model_start_date = model_start_date
            solved_model_end_date = model_end_date
            solved_model_horizon = model_horizon
            solved_display_dates = display_dates
            solved_extend_months = extend_months
            solved_attempt_type = attempt_type

            if attempt_type == "original_due":
                print("\n普通停电排产在原交期内找到可行解。")
            elif attempt_type == "current_month":
                print("\n普通停电排产通过当前月份内软交期找到可行解。")
            else:
                print(f"\n普通停电排产通过自动扩展 {extend_months} 个月找到可行解。")

            break

        if attempt_type == "original_due":
            print("注意：原交期内无可行解，系统将继续尝试在当前月份月末前完成。")
        elif attempt_type == "current_month":
            print("注意：当前月份内仍无可行解，系统将尝试扩展到后续月份。")
        else:
            print("注意：当前停电扩展周期下仍无可行解，系统将尝试继续扩展到后续月份。")

    if solved_result is None:
        print("\n所有普通停电自动扩展尝试均未找到可行解。")
        print("建议检查：")
        print("1. 停电时间是否过长；")
        print("2. 停电影响产线是否过多；")
        print("3. 订单总需求是否超过扩展周期内最大产能；")
        print("4. 是否需要继续增加 MAX_AUTO_EXTEND_MONTHS_FOR_OUTAGE。")
        return None

    # =========================
    # 导出 Excel
    # =========================
    output_file = export_to_excel(
        solved_result["order_df"],
        solved_result["calendar_df"],
        solved_result["detail_df"],
    )

    print(f"\n排产结果已全部导出到 Excel：{output_file}")
    print("Sheet 1：表1_订单视图")
    print_monthly_sheet_info(solved_display_dates)

    return {
        "output_file": output_file,
        "result": solved_result,
        "orders": solved_orders,
        "model_start_date": solved_model_start_date,
        "model_end_date": solved_model_end_date,
        "model_horizon": solved_model_horizon,
        "display_dates": solved_display_dates,
        "power_outages": power_outages,
        "has_power_outage": has_power_outage,
        "enable_soft_due": True,
        "extend_months": solved_extend_months,
    }