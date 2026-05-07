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

    for extend_months in range(MAX_AUTO_EXTEND_MONTHS_FOR_OUTAGE + 1):
        if extend_months == 0:
            forced_model_end_date = None
            print("\n=== 普通停电求解尝试：不扩展月份，优先尝试在当前月份内完成 ===")
        else:
            forced_model_end_date = add_months_to_month_end(
                natural_model_end_date,
                extend_months,
            )
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

            if extend_months == 0:
                print("\n普通停电排产在当前月份内找到可行解。")
            else:
                print(f"\n普通停电排产通过自动扩展 {extend_months} 个月找到可行解。")

            break

        print("注意：当前停电扩展周期下仍无可行解，系统将尝试扩展到后续月份。")

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