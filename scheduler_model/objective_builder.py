# =========================
# 文件说明：
# 这个文件负责 CP-SAT 排产模型的目标函数构建。
#
# 主要职责：
# 1. 计算换线次数；
# 2. 计算订单占线数波动；
# 3. 计算超产惩罚；
# 4. 组合普通排产、停电排产、插单排产下的目标函数；
# 5. 返回目标函数表达式以及后续导出需要使用的统计变量。
# =========================

from config import (
    NUM_LINES,
    WEIGHT_CHANGEOVER,
    WEIGHT_ACTIVE_DAYS,
    WEIGHT_LINE_STABILITY,
    WEIGHT_LOAD_SPREAD,
    WEIGHT_OVER_PRODUCTION,
    WEIGHT_PROD_DAYS,
    WEIGHT_ORDER_LINE_POSITION,
    WEIGHT_QUANTITY_INCREASE_CONTINUE,
    WEIGHT_DELAYED_ORDER_COUNT,
    WEIGHT_WEIGHTED_TARDINESS,
    WEIGHT_ORDER_SPLIT,
    WEIGHT_LINE_ORDER_SPLIT,
    WEIGHT_IDLE_LINE_INSERT,
    WEIGHT_INSERT_LINE_STABILITY,
    WEIGHT_INSERT_PROD_DAYS,
)


def build_objective(
    has_power_outage,
    num_orders,
    horizon,
    w,
    diff,
    e,
    s,
    prod_day,
    load_spread,
    over_line_days,
    over_output,
    over_output_units,
    total_order_line_position_change,
    weighted_plan_change_penalty,
    total_quantity_continue_break,
    total_delayed_orders,
    total_weighted_tardiness,
    total_order_split,
    total_line_order_split,
    total_idle_lines,
    total_insert_line_stability,
    total_insert_prod_days,
):
    """
    构建模型目标函数。

    无停电模式：
    目标函数主要考虑：
    1. 换线次数；
    2. 订单生产跨度；
    3. 订单每日占线数波动；
    4. 每日总开线数波动；
    5. 超产线天数；
    6. 插单模式下的原计划扰动、延期、分段、空闲产线等惩罚。

    停电模式：
    目标函数主要考虑：
    1. 换线次数；
    2. 订单生产跨度；
    3. 订单每日占线数波动；
    4. 订单产线位置变化；
    5. 实际产量超产；
    6. 生产天数；
    7. 插单模式下的原计划扰动、延期、分段、空闲产线等惩罚。

    返回：
        objective_expr:
            CP-SAT 目标函数表达式。

        total_changeovers:
            总换线次数。

        total_line_diff:
            订单占线数波动总量。

        total_over_line_days:
            无停电模式下为超产线天数；
            停电模式下为超产产量折算单位。

        total_over_output:
            停电模式下真实超产数量；
            无停电模式下为 None。

        total_over_output_units:
            停电模式下真实超产数量折算单位；
            无停电模式下为 None。
    """

    if not has_power_outage:
        total_changeovers = sum(
            w[i, t]
            for i in range(NUM_LINES)
            for t in range(horizon - 1)
        )

        total_line_diff = sum(
            diff[j, t]
            for j in range(num_orders)
            for t in range(horizon - 1)
        )

        total_over_line_days = sum(
            over_line_days[j]
            for j in range(num_orders)
        )

        total_over_output = None
        total_over_output_units = None

        objective_expr = (
                WEIGHT_CHANGEOVER * total_changeovers
                + WEIGHT_ACTIVE_DAYS * sum(e[j] - s[j] + 1 for j in range(num_orders))
                + WEIGHT_LINE_STABILITY * total_line_diff
                + WEIGHT_ORDER_LINE_POSITION * total_order_line_position_change
                + WEIGHT_LOAD_SPREAD * load_spread
                + WEIGHT_OVER_PRODUCTION * total_over_line_days
                + WEIGHT_PROD_DAYS * sum(prod_day[t] for t in range(horizon))
                + weighted_plan_change_penalty
                + WEIGHT_QUANTITY_INCREASE_CONTINUE * total_quantity_continue_break
                + WEIGHT_DELAYED_ORDER_COUNT * total_delayed_orders
                + WEIGHT_WEIGHTED_TARDINESS * total_weighted_tardiness
                + WEIGHT_ORDER_SPLIT * total_order_split
                + WEIGHT_LINE_ORDER_SPLIT * total_line_order_split
                + WEIGHT_IDLE_LINE_INSERT * total_idle_lines
                + WEIGHT_INSERT_LINE_STABILITY * total_insert_line_stability
                + WEIGHT_INSERT_PROD_DAYS * total_insert_prod_days
        )
    else:
        total_changeovers = sum(w.values())

        total_line_diff = sum(diff.values())

        total_over_line_days = sum(
            over_output_units[j]
            for j in range(num_orders)
        )

        total_over_output = sum(
            over_output[j]
            for j in range(num_orders)
        )

        total_over_output_units = sum(
            over_output_units[j]
            for j in range(num_orders)
        )

        objective_expr = (
            WEIGHT_CHANGEOVER * total_changeovers
            + WEIGHT_ACTIVE_DAYS * sum(e[j] - s[j] + 1 for j in range(num_orders))
            + WEIGHT_LINE_STABILITY * total_line_diff
            + WEIGHT_ORDER_LINE_POSITION * total_order_line_position_change
            + WEIGHT_OVER_PRODUCTION * total_over_output_units
            + WEIGHT_PROD_DAYS * sum(prod_day[t] for t in range(horizon))
            + weighted_plan_change_penalty
            + WEIGHT_QUANTITY_INCREASE_CONTINUE * total_quantity_continue_break
            + WEIGHT_DELAYED_ORDER_COUNT * total_delayed_orders
            + WEIGHT_WEIGHTED_TARDINESS * total_weighted_tardiness
            + WEIGHT_ORDER_SPLIT * total_order_split
            + WEIGHT_LINE_ORDER_SPLIT * total_line_order_split
            + WEIGHT_IDLE_LINE_INSERT * total_idle_lines
            + WEIGHT_INSERT_LINE_STABILITY * total_insert_line_stability
            + WEIGHT_INSERT_PROD_DAYS * total_insert_prod_days
        )

    return (
        objective_expr,
        total_changeovers,
        total_line_diff,
        total_over_line_days,
        total_over_output,
        total_over_output_units,
    )