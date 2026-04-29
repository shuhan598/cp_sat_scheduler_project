import pandas as pd

from config import NUM_LINES, DAILY_CAPACITY


def day_to_date(day_idx, start_date):
    """
    将模型内部的 day index 转成真实日期字符串。
    """
    if day_idx is None:
        return ""
    return str(start_date + pd.Timedelta(days=int(day_idx)))


def parse_order_view(solver, orders, variables, model_start_date, model_horizon):
    y = variables["y"]
    l = variables["l"]
    tardiness = variables.get("tardiness", None)
    over_line_days_var = variables.get("over_line_days", None)

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

        actual_output = total_line_days * DAILY_CAPACITY

        if over_line_days_var is not None:
            over_line_days = solver.Value(over_line_days_var[j])
        else:
            over_line_days = 0

        over_output = over_line_days * DAILY_CAPACITY

        if tardiness is not None:
            delay = solver.Value(tardiness[j])
        elif end_day is not None:
            delay = max(0, end_day - order["due"])
        else:
            delay = 0

        order_rows.append({
            "订单": order["name"],
            "窗口开始": day_to_date(order["release"], model_start_date),
            "窗口结束": day_to_date(order["due"], model_start_date),
            "实际开工": day_to_date(start_day, model_start_date) if start_day is not None else "",
            "实际完工": day_to_date(end_day, model_start_date) if end_day is not None else "",
            "生产天数": production_days,
            "总产线·天数": total_line_days,
            "需求量": order["quantity"],
            "实际产量": actual_output,
            "超产线天数": over_line_days,
            "超产量": over_output,
            "延迟天数": delay,
        })

    return pd.DataFrame(order_rows)


def parse_calendar_view(solver, orders, variables, model_start_date, model_horizon, display_dates):
    x = variables["x"]
    num_orders = len(orders)

    calendar_rows = []

    for i in range(NUM_LINES):
        row = {"产线": f"Line {i + 1}"}

        for display_date in display_dates:
            assigned_order = ""

            t = (display_date - model_start_date).days

            if 0 <= t < model_horizon:
                for j in range(num_orders):
                    if solver.Value(x[i, j, t]) == 1:
                        assigned_order = orders[j]["name"]
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


def parse_line_quantity_detail_view(solver, orders, variables, model_start_date, model_horizon, display_dates):
    """
    生成表2下方的产量明细表。

    表格格式：
    - 第一列：订单
    - 后面列：日期
    - 相同订单连续放在一起
    - 每一行代表该订单实际占用过的一条产线
    - 有生产则显示 DAILY_CAPACITY
    - 没有生产则留空
    - 最后增加：
        1. 线体合计：当天使用了多少条产线
        2. 产能合计：当天总产能 = 线体合计 * DAILY_CAPACITY
    """
    x = variables["x"]

    detail_rows = []

    # =========================
    # 1. 订单明细行
    # =========================
    for j, order in enumerate(orders):
        order_rows = []

        for i in range(NUM_LINES):
            row = {
                "订单": order["name"]
            }

            has_any_production = False

            for display_date in display_dates:
                t = (display_date - model_start_date).days

                value = ""
                if 0 <= t < model_horizon:
                    if solver.Value(x[i, j, t]) == 1:
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
            count = _count_used_lines_on_day(
                solver,
                orders,
                variables,
                t
            )

            if count > 0:
                capacity = count * DAILY_CAPACITY

        capacity_total_row[f"{display_date.month}/{display_date.day}"] = capacity

    detail_rows.append(capacity_total_row)

    return pd.DataFrame(detail_rows)


def parse_all_results(solver, orders, variables, model_start_date, model_horizon, display_dates):
    order_df = parse_order_view(
        solver,
        orders,
        variables,
        model_start_date,
        model_horizon
    )

    calendar_df = parse_calendar_view(
        solver,
        orders,
        variables,
        model_start_date,
        model_horizon,
        display_dates
    )

    detail_df = parse_line_quantity_detail_view(
        solver,
        orders,
        variables,
        model_start_date,
        model_horizon,
        display_dates
    )

    return order_df, calendar_df, detail_df


def print_solution_summary(solver, variables):
    print("目标函数值:", solver.ObjectiveValue())

    if "total_tardiness" in variables:
        print("总延迟天数:", solver.Value(variables["total_tardiness"]))

    print("总换线次数:", solver.Value(variables["total_changeovers"]))
    print("总生产天数:", solver.Value(variables["total_active_days"]))
    print("产线数波动:", solver.Value(variables["total_line_diff"]))
    print("负载波动:", solver.Value(variables["load_spread"]))

    if "total_over_line_days" in variables:
        total_over_line_days = solver.Value(variables["total_over_line_days"])
        print("总超产线天数:", total_over_line_days)
        print("总超产量:", total_over_line_days * DAILY_CAPACITY)

    if "total_prod_days" in variables:
        print("连续生产阶段天数:", solver.Value(variables["total_prod_days"]))