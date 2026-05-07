# 负责控制台打印求解结果汇总。

from config import DAILY_CAPACITY


def _solver_value_or_int(solver, value):
    """
    兼容 CP-SAT 表达式和普通整数。

    插单模式下：
    - total_plan_change 可能是 sum(BoolVar) 形成的表达式；
    - 没有插单时可能是普通整数 0。
    """
    if value is None:
        return 0

    if isinstance(value, int):
        return value

    return solver.Value(value)


def print_solution_summary(solver, variables):
    """
    打印求解结果汇总。

    该函数只负责控制台输出，不参与结果解析、不参与 Excel 导出。

    输出内容包括：
    - 目标函数值
    - 换线次数
    - 总生产天数
    - 产线数波动
    - 超产信息
    - 插单模式下的扰动、延期、分段、空闲产线等信息
    """

    print("目标函数值:", solver.ObjectiveValue())

    has_power_outage = variables.get("has_power_outage", False)

    if "total_tardiness" in variables:
        print("总延迟天数:", solver.Value(variables["total_tardiness"]))

    print("总换线次数:", solver.Value(variables["total_changeovers"]))
    print("总生产天数:", solver.Value(variables["total_active_days"]))
    print("产线数波动:", solver.Value(variables["total_line_diff"]))

    if "load_spread" in variables and variables["load_spread"] is not None:
        print("负载波动:", solver.Value(variables["load_spread"]))

    if has_power_outage:
        if (
            "total_over_output" in variables
            and variables["total_over_output"] is not None
        ):
            print("总超产量:", solver.Value(variables["total_over_output"]))

        if (
            "total_over_output_units" in variables
            and variables["total_over_output_units"] is not None
        ):
            print("总超产量缩放单位:", solver.Value(variables["total_over_output_units"]))
    else:
        if (
            "total_over_line_days" in variables
            and variables["total_over_line_days"] is not None
        ):
            total_over_line_days = solver.Value(variables["total_over_line_days"])
            print("总超产线天数:", total_over_line_days)
            print("总超产量:", total_over_line_days * DAILY_CAPACITY)

    if "total_prod_days" in variables:
        print("连续生产阶段天数:", solver.Value(variables["total_prod_days"]))

    if variables.get("enable_insert_mode", False):
        total_plan_change = variables.get("total_plan_change", 0)
        plan_change_value = _solver_value_or_int(
            solver,
            total_plan_change
        )
        print("原计划扰动单元格数:", plan_change_value)

        if "weighted_plan_change_penalty" in variables:
            weighted_plan_change_penalty = variables.get("weighted_plan_change_penalty", 0)
            print(
                "原计划扰动加权惩罚:",
                _solver_value_or_int(solver, weighted_plan_change_penalty)
            )

        if "total_delayed_orders" in variables:
            total_delayed_orders = variables.get("total_delayed_orders", 0)
            print(
                "延期订单数量:",
                _solver_value_or_int(solver, total_delayed_orders)
            )

        if "total_weighted_tardiness" in variables:
            total_weighted_tardiness = variables.get("total_weighted_tardiness", 0)
            print(
                "紧迫度加权延期天数:",
                _solver_value_or_int(solver, total_weighted_tardiness)
            )

        if "total_quantity_continue_break" in variables:
            total_quantity_continue_break = variables.get("total_quantity_continue_break", 0)
            print(
                "加量订单原产线未延续次数:",
                _solver_value_or_int(solver, total_quantity_continue_break)
            )

        if "total_order_split" in variables:
            total_order_split = variables.get("total_order_split", 0)
            print(
                "原订单额外生产段数:",
                _solver_value_or_int(solver, total_order_split)
            )

        if "total_line_order_split" in variables:
            total_line_order_split = variables.get("total_line_order_split", 0)
            print(
                "同一产线同一订单额外分段数:",
                _solver_value_or_int(solver, total_line_order_split)
            )

        if "total_idle_lines" in variables:
            total_idle_lines = variables.get("total_idle_lines", 0)
            print(
                "插单模式空闲产线惩罚数量:",
                _solver_value_or_int(solver, total_idle_lines)
            )

        if "total_insert_line_stability" in variables:
            total_insert_line_stability = variables.get("total_insert_line_stability", 0)
            print(
                "插单/加量订单产线位置变化次数:",
                _solver_value_or_int(solver, total_insert_line_stability)
            )

        if "total_insert_prod_days" in variables:
            total_insert_prod_days = variables.get("total_insert_prod_days", 0)
            print(
                "插单模式生产日数量:",
                _solver_value_or_int(solver, total_insert_prod_days)
            )

        freeze_until_day = variables.get("freeze_until_day", None)
        if freeze_until_day is not None:
            print("冻结截止模型日:", freeze_until_day)