# 负责把 solver 结果解析成订单视图、产线日历、产量明细。

import pandas as pd

from config import NUM_LINES, DAILY_CAPACITY


def day_to_date(day_idx, start_date):
    """
    将模型内部的 day index 转成真实日期字符串。
    """
    if day_idx is None:
        return ""
    return str(start_date + pd.Timedelta(days=int(day_idx)))


def _get_line_capacity(variables, line_capacity=None):
    """
    获取产线-日期产能矩阵。

    优先使用函数传入的 line_capacity；
    如果没有传入，则尝试从 variables 中读取。
    """
    if line_capacity is not None:
        return line_capacity

    return variables.get("line_capacity", None)


def _get_has_power_outage(variables, has_power_outage=False):
    """
    获取是否启用停电模式。
    """
    if "has_power_outage" in variables:
        return variables["has_power_outage"]

    return has_power_outage


def _get_order_display_name(order):
    """
    获取订单展示名称。

    新版插单逻辑中：
    - order["name"] 是模型内部订单名；
    - order["display_name"] 是导出到 Excel 给用户看的名称。

    例如：
    同名新批次订单内部名可能是：
        A_插单批次_20260510

    但展示名称可以是：
        A（插单批次）
    """
    return order.get("display_name", order.get("name", ""))


def _get_order_internal_name(order):
    """
    获取订单内部名称。

    主要用于表1中辅助查看同名新批次订单的内部区分。
    """
    return order.get("name", "")


def _get_yes_no(value):
    """
    将布尔值转成“是 / 否”。
    """
    return "是" if value else "否"


def _get_insert_affected_flag(order):
    """
    判断订单是否受到插单影响。

    包括：
    1. 新插单订单；
    2. 同名新批次插单；
    3. 原订单加量。
    """
    return (
        order.get("is_inserted", False)
        or order.get("is_quantity_increased", False)
        or order.get("insert_process_type", "原订单") != "原订单"
    )


def parse_order_view(
    solver,
    orders,
    variables,
    model_start_date,
    model_horizon,
    line_capacity=None,
    has_power_outage=False
):
    y = variables["y"]
    l = variables["l"]
    x = variables["x"]

    has_power_outage = _get_has_power_outage(
        variables,
        has_power_outage
    )

    line_capacity = _get_line_capacity(
        variables,
        line_capacity
    )

    tardiness = variables.get("tardiness", None)
    is_delayed = variables.get("is_delayed", None)

    over_line_days_var = variables.get("over_line_days", None)
    actual_output_var = variables.get("actual_output", None)
    over_output_var = variables.get("over_output", None)

    order_rows = []

    for j, order in enumerate(orders):
        active_days = [
            t for t in range(model_horizon)
            if solver.Value(y[j, t]) == 1
        ]

        if active_days:
            start_day = min(active_days)
            end_day = max(active_days)
            production_days = len(active_days)
        else:
            start_day = None
            end_day = None
            production_days = 0

        total_line_days = sum(
            solver.Value(l[j, t]) for t in range(model_horizon)
        )

        if has_power_outage and line_capacity is not None:
            if actual_output_var and j in actual_output_var:
                actual_output = solver.Value(actual_output_var[j])
            else:
                actual_output = sum(
                    line_capacity[i][t] * solver.Value(x[i, j, t])
                    for i in range(NUM_LINES)
                    for t in range(model_horizon)
                )

            if over_output_var and j in over_output_var:
                over_output = solver.Value(over_output_var[j])
            else:
                over_output = max(0, actual_output - order["quantity"])

            # 停电模式下，超产主要按实际产量计算。
            # 这里仍保留“超产线天数”列，但不再作为核心指标。
            over_line_days = ""
        else:
            actual_output = total_line_days * DAILY_CAPACITY

            if over_line_days_var is not None and j in over_line_days_var:
                over_line_days = solver.Value(over_line_days_var[j])
            else:
                over_line_days = 0

            over_output = over_line_days * DAILY_CAPACITY

        # =========================
        # 插单模式：延期结果解析
        # =========================
        #
        # 新版插单模型中，最晚完工日期是软交期：
        # - 超过原交期仍然可以继续生产；
        # - 但会产生 tardiness[j] 延期天数；
        # - is_delayed[j] 表示该订单是否延期。
        #
        # 普通排产模式下，如果没有 tardiness 变量，
        # 仍然沿用原来的 end_day - due 计算方式。
        if tardiness is not None and j in tardiness:
            delay = solver.Value(tardiness[j])
        elif end_day is not None:
            delay = max(0, end_day - order["due"])
        else:
            delay = 0

        if is_delayed is not None and j in is_delayed:
            delayed_flag = solver.Value(is_delayed[j]) == 1
        else:
            delayed_flag = delay > 0

        display_name = _get_order_display_name(order)
        internal_name = _get_order_internal_name(order)

        insert_process_type = order.get("insert_process_type", "原订单")
        original_quantity = order.get("original_quantity", order["quantity"])
        increase_quantity = order.get("increase_quantity", 0)

        order_rows.append({
            "订单": display_name,

            # 内部订单名主要用于同名新批次场景。
            # 如果没有同名新批次，也不会影响阅读。
            "内部订单名": internal_name,

            # 插单处理方式：
            # 原订单 / 加量 / 新单 / 同名新批次
            "插单处理方式": insert_process_type,

            # 是否插单影响：
            # 加量、新单、同名新批次均显示“是”。
            "是否插单影响": _get_yes_no(_get_insert_affected_flag(order)),

            # 是否插单：
            # 这里保留原字段含义，主要表示是否为新增订单。
            # 加量订单本身仍是原订单，所以“是否插单”可能为“否”，
            # 但“是否插单影响”会显示“是”。
            "是否插单": "是" if order.get("is_inserted", False) else "否",

            "是否加量": _get_yes_no(order.get("is_quantity_increased", False)),
            "原需求量": original_quantity,
            "插单增加量": increase_quantity,
            "最终需求量": order["quantity"],

            # 自动紧迫度相关字段。
            # 这些值由 data_loader.py 根据需求量、剩余窗口和交期自动计算。
            "所需产线天数": order.get("required_line_days", ""),
            "剩余窗口天数": order.get("remaining_window_days", ""),
            "自动紧迫度": order.get("urgency", ""),
            "紧迫度权重": order.get("urgency_weight", ""),

            "窗口开始": day_to_date(order["release"], model_start_date),
            "窗口结束": day_to_date(order["due"], model_start_date),
            "实际开工": day_to_date(start_day, model_start_date) if start_day is not None else "",
            "实际完工": day_to_date(end_day, model_start_date) if end_day is not None else "",
            "生产天数": production_days,
            "总产线·天数": total_line_days,

            # 保留原来的“需求量”字段，方便兼容旧表头理解。
            # 新版中它等同于“最终需求量”。
            "需求量": order["quantity"],

            "实际产量": actual_output,
            "超产线天数": over_line_days,
            "超产量": over_output,

            # 新字段：更清晰表达软交期下的延期。
            "是否延期": _get_yes_no(delayed_flag),
            "延期天数": delay,

            # 保留旧字段名，避免后续如果有旧代码引用“延迟天数”时出错。
            "延迟天数": delay,
        })

    return pd.DataFrame(order_rows)


def parse_calendar_view(
    solver,
    orders,
    variables,
    model_start_date,
    model_horizon,
    display_dates,
    line_capacity=None,
    has_power_outage=False
):
    x = variables["x"]
    num_orders = len(orders)

    has_power_outage = _get_has_power_outage(
        variables,
        has_power_outage
    )

    line_capacity = _get_line_capacity(
        variables,
        line_capacity
    )

    calendar_rows = []

    for i in range(NUM_LINES):
        row = {"产线": f"Line {i + 1}"}

        for display_date in display_dates:
            assigned_order = ""

            t = (display_date - model_start_date).days

            if 0 <= t < model_horizon:
                if (
                    has_power_outage
                    and line_capacity is not None
                    and line_capacity[i][t] == 0
                ):
                    assigned_order = "停电检修"
                else:
                    for j in range(num_orders):
                        if solver.Value(x[i, j, t]) == 1:
                            # 新版插单逻辑中，表格展示使用 display_name。
                            # 这样同名新批次可以显示为：
                            # A（插单批次）
                            assigned_order = _get_order_display_name(orders[j])
                            break

            row[f"{display_date.month}/{display_date.day}"] = assigned_order

        calendar_rows.append(row)

    return pd.DataFrame(calendar_rows)


def _count_used_lines_on_day(solver, orders, variables, day_idx):
    """
    统计某一天实际使用了多少条产线。
    只要某条产线当天分配给任意订单，就计为 1 条线。
    """
    x = variables["x"]
    num_orders = len(orders)

    count = 0

    for i in range(NUM_LINES):
        for j in range(num_orders):
            if solver.Value(x[i, j, day_idx]) == 1:
                count += 1
                break

    return count


def _actual_capacity_on_day(solver, orders, variables, day_idx, line_capacity=None):
    """
    统计某一天实际产量。

    无停电模式：
    使用线体数量 * DAILY_CAPACITY。

    有停电模式：
    对所有实际开线的产线，累加 line_capacity[i][day_idx]。
    """
    x = variables["x"]
    num_orders = len(orders)

    has_power_outage = variables.get("has_power_outage", False)
    line_capacity = _get_line_capacity(variables, line_capacity)

    total_capacity = 0

    for i in range(NUM_LINES):
        used = False

        for j in range(num_orders):
            if solver.Value(x[i, j, day_idx]) == 1:
                used = True
                break

        if used:
            if has_power_outage and line_capacity is not None:
                total_capacity += line_capacity[i][day_idx]
            else:
                total_capacity += DAILY_CAPACITY

    return total_capacity


def parse_line_quantity_detail_view(
    solver,
    orders,
    variables,
    model_start_date,
    model_horizon,
    display_dates,
    line_capacity=None,
    has_power_outage=False
):
    """
    生成表2下方的产量明细表。

    表格格式：
    - 第一列：订单
    - 后面列：日期
    - 相同订单连续放在一起
    - 每一行代表该订单实际占用过的一条产线
    - 无停电模式：有生产则显示 DAILY_CAPACITY
    - 有停电模式：有生产则显示该产线当天的真实产能 line_capacity[i][t]
    - 没有生产则留空
    - 最后增加：
        1. 线体合计：当天使用了多少条产线
        2. 产能合计：当天实际总产能
    """
    x = variables["x"]

    has_power_outage = _get_has_power_outage(
        variables,
        has_power_outage
    )

    line_capacity = _get_line_capacity(
        variables,
        line_capacity
    )

    detail_rows = []

    # =========================
    # 1. 订单明细行
    # =========================
    for j, order in enumerate(orders):
        order_rows = []

        for i in range(NUM_LINES):
            row = {
                # 新版插单逻辑中，明细表展示使用 display_name。
                # 同名新批次会显示为 A（插单批次）。
                "订单": _get_order_display_name(order)
            }

            has_any_production = False

            for display_date in display_dates:
                t = (display_date - model_start_date).days

                value = ""
                if 0 <= t < model_horizon:
                    if solver.Value(x[i, j, t]) == 1:
                        if has_power_outage and line_capacity is not None:
                            value = line_capacity[i][t]
                        else:
                            value = DAILY_CAPACITY

                        has_any_production = True

                row[f"{display_date.month}/{display_date.day}"] = value

            if has_any_production:
                order_rows.append(row)

        if order_rows:
            detail_rows.extend(order_rows)

            # 每个订单后面插入一行空白，便于分组查看
            blank_row = {"订单": ""}
            for display_date in display_dates:
                blank_row[f"{display_date.month}/{display_date.day}"] = ""
            detail_rows.append(blank_row)

    # 删除最后多余的空白行
    if detail_rows:
        last_row = detail_rows[-1]
        if all(v == "" for v in last_row.values()):
            detail_rows.pop()

    # =========================
    # 2. 明细和汇总之间插入空白行
    # =========================
    blank_row = {"订单": ""}
    for display_date in display_dates:
        blank_row[f"{display_date.month}/{display_date.day}"] = ""
    detail_rows.append(blank_row)

    # =========================
    # 3. 线体合计行
    # =========================
    line_total_row = {
        "订单": "线体合计"
    }

    for display_date in display_dates:
        t = (display_date - model_start_date).days

        line_count = ""
        if 0 <= t < model_horizon:
            count = _count_used_lines_on_day(
                solver,
                orders,
                variables,
                t
            )

            if count > 0:
                line_count = count

        line_total_row[f"{display_date.month}/{display_date.day}"] = line_count

    detail_rows.append(line_total_row)

    # =========================
    # 4. 产能合计行
    # =========================
    capacity_total_row = {
        "订单": "产能合计"
    }

    for display_date in display_dates:
        t = (display_date - model_start_date).days

        capacity = ""
        if 0 <= t < model_horizon:
            total_capacity = _actual_capacity_on_day(
                solver,
                orders,
                variables,
                t,
                line_capacity=line_capacity
            )

            if total_capacity > 0:
                capacity = total_capacity

        capacity_total_row[f"{display_date.month}/{display_date.day}"] = capacity

    detail_rows.append(capacity_total_row)

    return pd.DataFrame(detail_rows)


def parse_all_results(
    solver,
    orders,
    variables,
    model_start_date,
    model_horizon,
    display_dates,
    line_capacity=None,
    has_power_outage=False
):
    order_df = parse_order_view(
        solver,
        orders,
        variables,
        model_start_date,
        model_horizon,
        line_capacity=line_capacity,
        has_power_outage=has_power_outage
    )

    calendar_df = parse_calendar_view(
        solver,
        orders,
        variables,
        model_start_date,
        model_horizon,
        display_dates,
        line_capacity=line_capacity,
        has_power_outage=has_power_outage
    )

    detail_df = parse_line_quantity_detail_view(
        solver,
        orders,
        variables,
        model_start_date,
        model_horizon,
        display_dates,
        line_capacity=line_capacity,
        has_power_outage=has_power_outage
    )

    return order_df, calendar_df, detail_df


