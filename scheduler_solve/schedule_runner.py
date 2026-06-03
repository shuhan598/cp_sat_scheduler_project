# =========================
# 文件说明：
# 这个文件负责执行一次完整的排产求解尝试。
#
# 主要职责：
# 1. 根据停电计划构建当前模型周期的产能矩阵；
# 2. 调用 model_builder 构建 CP-SAT 模型；
# 3. 调用 solver_runner 求解模型；
# 4. 调用 result_parser 解析求解结果；
# 5. 返回订单视图、产线日历、日产量明细等结果。
#
# 不负责：
# 1. 不负责读取 Excel 订单；
# 2. 不负责读取旧排产计划；
# 3. 不负责判断插单类型；
# 4. 不负责导出 Excel。
# =========================

from preprocessing.capacity_builder import (
    build_line_capacity_matrix,
)

from scheduler_model.model_builder import build_model
from scheduler_solve.solver_runner import solve_model, is_solution_found, get_status_name
from scheduler_results.result_parser import parse_all_results
from scheduler_results.solution_summary import print_solution_summary


def _build_power_capacity_inputs(
    power_outages,
    has_power_outage,
    model_start_date,
    model_horizon,
):
    """
    根据当前模型周期构造停电影响后的产能矩阵。

    为什么这里要单独封装：
    插单模式下可能会自动扩展到 6 月、7 月，
    每次扩展后的 model_horizon 不同，
    因此 line_capacity、line_available 等矩阵也需要按当前 horizon 重新生成。
    """
    if has_power_outage:
        line_capacity, line_available, available_lines, full_outage_days = build_line_capacity_matrix(
            power_outages,
            model_start_date,
            model_horizon
        )
    else:
        line_capacity = None
        line_available = None
        available_lines = None
        full_outage_days = None

    return line_capacity, line_available, available_lines, full_outage_days


def run_single_schedule_attempt(
    orders,
    model_start_date,
    model_end_date,
    model_horizon,
    display_dates,
    power_outages,
    has_power_outage,
    enable_insert_mode=False,
    enable_soft_due=False,
    previous_plan=None,
    freeze_until_day=None,
    insert_info=None,
):
    """
    构建模型、求解模型并解析结果。

    该函数同时服务：
    1. 普通排产；
    2. 普通停电软交期排产；
    3. 插单排产某一次自动跨月扩展尝试。

    参数：
        enable_insert_mode:
            是否启用插单模式。

        enable_soft_due:
            是否启用软交期。
            普通停电排产自动扩展月份时，可以启用该参数，
            允许订单超过原交期继续生产，但产生延期惩罚。

    返回：
        如果找到可行解：
            solver, variables, order_df, calendar_df, detail_df, capacity_inputs

        如果无可行解：
            None
    """

    line_capacity, line_available, available_lines, full_outage_days = _build_power_capacity_inputs(
        power_outages=power_outages,
        has_power_outage=has_power_outage,
        model_start_date=model_start_date,
        model_horizon=model_horizon,
    )

    # =========================
    # 构建模型
    # =========================
    print("\n开始构建 CP-SAT 排产模型...")
    print(f"模型起始日期: {model_start_date}")
    print(f"模型结束日期: {model_end_date}")
    print(f"模型 HORIZON: {model_horizon}")
    print(f"展示日期范围: {display_dates[0]} ~ {display_dates[-1]}")

    if enable_soft_due:
        print("当前求解启用软交期：允许超过原交期继续生产，但会产生延期惩罚。")

    if insert_info is None:
        insert_info = {
            "old_order_names": set(),
            "inserted_order_names": set(),
            "quantity_increased_order_names": set(),
        }

    model, variables = build_model(
        orders,
        model_horizon,
        line_capacity=line_capacity,
        line_available=line_available,
        available_lines=available_lines,
        full_outage_days=full_outage_days,
        has_power_outage=has_power_outage,

        # 插单模式参数
        previous_plan=previous_plan,
        freeze_until_day=freeze_until_day,
        old_order_names=insert_info.get("old_order_names", set()),
        inserted_order_names=insert_info.get("inserted_order_names", set()),
        quantity_increased_order_names=insert_info.get("quantity_increased_order_names", set()),
        enable_insert_mode=enable_insert_mode,

        # 软交期参数
        enable_soft_due=enable_soft_due,
    )

    # =========================
    # 求解模型
    # =========================
    print("模型构建完成，开始求解...")

    solver, status = solve_model(model)

    print("求解状态:", get_status_name(status))

    if not is_solution_found(status):
        print("没有找到可行解。")

        if has_power_outage:
            print("注意：停电导致产能下降，可能无法满足订单交期。")

        if enable_soft_due:
            print("注意：当前软交期扩展周期下仍无可行解，系统可继续尝试扩展到后续月份。")

        if enable_insert_mode:
            print("注意：当前插单扩展周期下仍无可行解，系统将尝试扩展到后续月份。")

        return None

    # =========================
    # 解析结果
    # =========================
    print("\n找到可行解！")
    print_solution_summary(solver, variables)

    order_df, calendar_df, detail_df, machine_df, date_machine_df = parse_all_results(
        solver,
        orders,
        variables,
        model_start_date,
        model_horizon,
        display_dates,
        line_capacity=line_capacity,
        has_power_outage=has_power_outage,
    )

    return {
        "solver": solver,
        "variables": variables,
        "order_df": order_df,
        "calendar_df": calendar_df,
        "detail_df": detail_df,
        "machine_df": machine_df,
        "date_machine_df": date_machine_df,
        "line_capacity": line_capacity,
        "line_available": line_available,
        "available_lines": available_lines,
        "full_outage_days": full_outage_days,
    }