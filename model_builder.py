from ortools.sat.python import cp_model
import math

from config import (
    NUM_LINES,
    DAILY_CAPACITY,
    MIN_LINES_PER_ACTIVE_ORDER,
    WEIGHT_CHANGEOVER,
    WEIGHT_ACTIVE_DAYS,
    WEIGHT_LINE_STABILITY,
    WEIGHT_LOAD_SPREAD,
    WEIGHT_OVER_PRODUCTION,
)


def build_model(orders, horizon):
    """
    构建 CP-SAT 排产模型。

    当前版本逻辑：
    1. 订单必须在 release ~ due 时间窗口内生产；
    2. 每个订单至少完成需求量，允许适当超产；
    3. 生产阶段从第 1 天开始，连续生产；
    4. 生产阶段内每天必须 18 条线满产；
    5. 所有订单完成后，后续日期允许全部空闲；
    6. 在满足硬约束基础上，尽量少换线、少波动、少超产。
    """

    model = cp_model.CpModel()
    num_orders = len(orders)

    # =========================
    # 1. 决策变量
    # =========================

    # x[i, j, t] = 1 表示产线 i 在第 t 天生产订单 j
    x = {}
    for i in range(NUM_LINES):
        for j in range(num_orders):
            for t in range(horizon):
                x[i, j, t] = model.NewBoolVar(
                    f"x_line{i}_order{j}_day{t}"
                )

    # y[j, t] = 1 表示订单 j 在第 t 天处于生产状态
    y = {}
    for j in range(num_orders):
        for t in range(horizon):
            y[j, t] = model.NewBoolVar(
                f"y_order{j}_day{t}"
            )

    # s[j] 表示订单 j 在允许窗口内由模型选择的开工日
    # e[j] 表示订单 j 在允许窗口内由模型选择的完工日
    s = {}
    e = {}
    for j, order in enumerate(orders):
        release = order["release"]
        due = order["due"]

        s[j] = model.NewIntVar(
            release,
            due,
            f"start_day_order{j}"
        )

        e[j] = model.NewIntVar(
            release,
            due,
            f"end_day_order{j}"
        )

        model.Add(s[j] <= e[j])

    # l[j, t] 表示订单 j 在第 t 天占用多少条产线
    l = {}
    for j in range(num_orders):
        for t in range(horizon):
            l[j, t] = model.NewIntVar(
                0,
                NUM_LINES,
                f"l_order{j}_day{t}"
            )

    # u[i, t] = 1 表示产线 i 在第 t 天处于生产状态
    u = {}
    for i in range(NUM_LINES):
        for t in range(horizon):
            u[i, t] = model.NewBoolVar(
                f"active_line{i}_day{t}"
            )

    # w[i, t] = 1 表示产线 i 从第 t 天到第 t+1 天发生订单切换
    w = {}
    for i in range(NUM_LINES):
        for t in range(horizon - 1):
            w[i, t] = model.NewBoolVar(
                f"change_line{i}_day{t}"
            )

    # diff[j, t] 表示订单 j 相邻两天占用产线数变化的绝对值
    diff = {}
    for j in range(num_orders):
        for t in range(horizon - 1):
            diff[j, t] = model.NewIntVar(
                0,
                NUM_LINES,
                f"diff_order{j}_day{t}"
            )

    # block_start[i, j, t] = 1 表示订单 j 在第 t 天的连续产线块从产线 i 开始
    block_start = {}
    for i in range(NUM_LINES):
        for j in range(num_orders):
            for t in range(horizon):
                block_start[i, j, t] = model.NewBoolVar(
                    f"block_start_line{i}_order{j}_day{t}"
                )

    # block_end[i, j, t] = 1 表示订单 j 在第 t 天的连续产线块在产线 i 结束
    block_end = {}
    for i in range(NUM_LINES):
        for j in range(num_orders):
            for t in range(horizon):
                block_end[i, j, t] = model.NewBoolVar(
                    f"block_end_line{i}_order{j}_day{t}"
                )

    # order_on_line_start[i, j, t] = 1 表示产线 i 在第 t 天开始生产订单 j
    order_on_line_start = {}
    for i in range(NUM_LINES):
        for j in range(num_orders):
            for t in range(horizon):
                order_on_line_start[i, j, t] = model.NewBoolVar(
                    f"order{j}_start_on_line{i}_day{t}"
                )

    # active_block_start[i, t] = 1 表示第 t 天整体开线块从产线 i 开始
    active_block_start = {}
    for i in range(NUM_LINES):
        for t in range(horizon):
            active_block_start[i, t] = model.NewBoolVar(
                f"active_block_start_line{i}_day{t}"
            )

    # active_block_end[i, t] = 1 表示第 t 天整体开线块在产线 i 结束
    active_block_end = {}
    for i in range(NUM_LINES):
        for t in range(horizon):
            active_block_end[i, t] = model.NewBoolVar(
                f"active_block_end_line{i}_day{t}"
            )

    # prod_day[t] = 1 表示第 t 天属于总体生产阶段
    prod_day = {}
    for t in range(horizon):
        prod_day[t] = model.NewBoolVar(
            f"prod_day_{t}"
        )

    # daily_load[t] 表示第 t 天总共开了多少条产线
    daily_load = {}
    for t in range(horizon):
        daily_load[t] = model.NewIntVar(
            0,
            NUM_LINES,
            f"daily_load_day{t}"
        )

    max_load = model.NewIntVar(0, NUM_LINES, "max_load")
    min_load = model.NewIntVar(0, NUM_LINES, "min_load")
    load_spread = model.NewIntVar(0, NUM_LINES, "load_spread")

    # =========================
    # 2. 产线独占约束
    # =========================
    for i in range(NUM_LINES):
        for t in range(horizon):
            model.Add(
                sum(x[i, j, t] for j in range(num_orders)) <= 1
            )

    # =========================
    # 3. u[i,t] 与 x[i,j,t] 衔接
    # =========================
    for i in range(NUM_LINES):
        for t in range(horizon):
            model.Add(
                u[i, t] == sum(x[i, j, t] for j in range(num_orders))
            )

    # =========================
    # 4. l[j,t] 与 x[i,j,t] 衔接
    # =========================
    for j in range(num_orders):
        for t in range(horizon):
            model.Add(
                l[j, t] == sum(x[i, j, t] for i in range(NUM_LINES))
            )

    # =========================
    # 5. y[j,t] 与 l[j,t] 衔接
    # =========================
    for j in range(num_orders):
        for t in range(horizon):
            model.Add(l[j, t] >= MIN_LINES_PER_ACTIVE_ORDER * y[j, t])
            model.Add(l[j, t] <= NUM_LINES * y[j, t])

    # =========================
    # 6. 同一订单同一天的产线连续块约束
    # =========================
    for j in range(num_orders):
        for t in range(horizon):
            for i in range(NUM_LINES):
                if i == 0:
                    model.Add(block_start[i, j, t] == x[i, j, t])
                else:
                    model.Add(block_start[i, j, t] >= x[i, j, t] - x[i - 1, j, t])
                    model.Add(block_start[i, j, t] <= x[i, j, t])
                    model.Add(block_start[i, j, t] <= 1 - x[i - 1, j, t])

                if i == NUM_LINES - 1:
                    model.Add(block_end[i, j, t] == x[i, j, t])
                else:
                    model.Add(block_end[i, j, t] >= x[i, j, t] - x[i + 1, j, t])
                    model.Add(block_end[i, j, t] <= x[i, j, t])
                    model.Add(block_end[i, j, t] <= 1 - x[i + 1, j, t])

            model.Add(
                sum(block_start[i, j, t] for i in range(NUM_LINES)) == y[j, t]
            )
            model.Add(
                sum(block_end[i, j, t] for i in range(NUM_LINES)) == y[j, t]
            )

    # =========================
    # 7. 同一天所有开线产线整体连续约束
    # =========================
    for t in range(horizon):
        for i in range(NUM_LINES):
            if i == 0:
                model.Add(active_block_start[i, t] == u[i, t])
            else:
                model.Add(active_block_start[i, t] >= u[i, t] - u[i - 1, t])
                model.Add(active_block_start[i, t] <= u[i, t])
                model.Add(active_block_start[i, t] <= 1 - u[i - 1, t])

            if i == NUM_LINES - 1:
                model.Add(active_block_end[i, t] == u[i, t])
            else:
                model.Add(active_block_end[i, t] >= u[i, t] - u[i + 1, t])
                model.Add(active_block_end[i, t] <= u[i, t])
                model.Add(active_block_end[i, t] <= 1 - u[i + 1, t])

        # 若 prod_day[t] = 1，当天所有开线产线必须形成一个整体连续块
        # 若 prod_day[t] = 0，当天没有开线块
        model.Add(
            sum(active_block_start[i, t] for i in range(NUM_LINES)) == prod_day[t]
        )
        model.Add(
            sum(active_block_end[i, t] for i in range(NUM_LINES)) == prod_day[t]
        )

    # =========================
    # 8. 释放期和交期窗口约束
    # =========================
    for j, order in enumerate(orders):
        release = order["release"]
        due = order["due"]

        for t in range(horizon):
            if t < release or t > due:
                model.Add(y[j, t] == 0)
                model.Add(l[j, t] == 0)

    # =========================
    # 9. 订单连续生产约束
    # =========================
    for j in range(num_orders):
        start_flags = []

        for t in range(horizon):
            start = model.NewBoolVar(
                f"start_order{j}_day{t}"
            )
            start_flags.append(start)

            if t == 0:
                model.Add(start == y[j, t])
            else:
                model.Add(start >= y[j, t] - y[j, t - 1])
                model.Add(start <= y[j, t])
                model.Add(start <= 1 - y[j, t - 1])

        model.Add(sum(start_flags) <= 1)
        model.Add(
            sum(y[j, t] for t in range(horizon)) >= 1
        )

    # =========================
    # 10. s[j], e[j] 与 y[j,t] 的衔接
    # =========================
    for j in range(num_orders):
        for t in range(horizon):
            model.Add(s[j] <= t).OnlyEnforceIf(y[j, t])
            model.Add(e[j] >= t).OnlyEnforceIf(y[j, t])

    # =========================
    # 11. 产线连续开线约束
    # =========================
    for i in range(NUM_LINES):
        line_start_flags = []

        for t in range(horizon):
            line_start = model.NewBoolVar(
                f"line_start{i}_day{t}"
            )
            line_start_flags.append(line_start)

            if t == 0:
                model.Add(line_start == u[i, t])
            else:
                model.Add(line_start >= u[i, t] - u[i, t - 1])
                model.Add(line_start <= u[i, t])
                model.Add(line_start <= 1 - u[i, t - 1])

        model.Add(sum(line_start_flags) <= 1)

    # =========================
    # 12. 同一产线同一订单最多一个连续生产段
    # =========================
    for i in range(NUM_LINES):
        for j in range(num_orders):
            order_on_line_start_flags = []

            for t in range(horizon):
                order_on_line_start_flags.append(order_on_line_start[i, j, t])

                if t == 0:
                    model.Add(order_on_line_start[i, j, t] == x[i, j, t])
                else:
                    model.Add(
                        order_on_line_start[i, j, t]
                        >= x[i, j, t] - x[i, j, t - 1]
                    )
                    model.Add(order_on_line_start[i, j, t] <= x[i, j, t])
                    model.Add(order_on_line_start[i, j, t] <= 1 - x[i, j, t - 1])

            model.Add(sum(order_on_line_start_flags) <= 1)

    # =========================
    # 13. 订单产能约束：允许超产，但尽量少超产
    # =========================
    required_line_days = {}
    over_line_days = {}

    for j, order in enumerate(orders):
        required = math.ceil(order["quantity"] / DAILY_CAPACITY)
        required_line_days[j] = required

        total_line_days_j = sum(l[j, t] for t in range(horizon))

        over_line_days[j] = model.NewIntVar(
            0,
            NUM_LINES * horizon,
            f"over_line_days_order{j}"
        )

        # 至少完成订单需求，允许超产
        model.Add(total_line_days_j >= required)

        # 超产线天数 = 实际线天数 - 需求线天数
        model.Add(over_line_days[j] == total_line_days_j - required)

    # =========================
    # 14. 生产阶段约束：
    #     生产阶段连续；生产阶段内每天18条线满产；结束后全部空闲
    # =========================

    # daily_load[t] = 第 t 天所有订单占用产线数之和
    for t in range(horizon):
        model.Add(
            daily_load[t] == sum(l[j, t] for j in range(num_orders))
        )

    # 生产阶段必须是前缀连续块：
    # 允许 1,1,1,1,0,0,0
    # 不允许 1,1,0,1,1
    for t in range(horizon - 1):
        model.Add(prod_day[t] >= prod_day[t + 1])

    # 第一天天必须进入生产阶段
    model.Add(prod_day[0] == 1)

    # 生产阶段每天18条线满产；非生产阶段0条线
    for t in range(horizon):
        model.Add(daily_load[t] == NUM_LINES * prod_day[t])

    model.AddMaxEquality(
        max_load,
        [daily_load[t] for t in range(horizon)]
    )
    model.AddMinEquality(
        min_load,
        [daily_load[t] for t in range(horizon)]
    )
    model.Add(load_spread == max_load - min_load)

    # =========================
    # 15. 换线变量约束
    # =========================
    for i in range(NUM_LINES):
        for t in range(horizon - 1):
            for j in range(num_orders):
                for k in range(num_orders):
                    if j != k:
                        model.Add(
                            w[i, t] >= x[i, j, t] + x[i, k, t + 1] - 1
                        )

    # =========================
    # 16. 产线数稳定性约束
    # =========================
    for j in range(num_orders):
        for t in range(horizon - 1):
            model.Add(diff[j, t] >= l[j, t] - l[j, t + 1])
            model.Add(diff[j, t] >= l[j, t + 1] - l[j, t])

    # =========================
    # 17. 目标函数
    # =========================
    total_changeovers = sum(
        w[i, t]
        for i in range(NUM_LINES)
        for t in range(horizon - 1)
    )

    total_active_days = sum(
        y[j, t]
        for j in range(num_orders)
        for t in range(horizon)
    )

    total_order_span = sum(
        e[j] - s[j] + 1
        for j in range(num_orders)
    )

    total_line_diff = sum(
        diff[j, t]
        for j in range(num_orders)
        for t in range(horizon - 1)
    )

    total_prod_days = sum(prod_day[t] for t in range(horizon))

    total_over_line_days = sum(
        over_line_days[j] for j in range(num_orders)
    )

    model.Minimize(
        WEIGHT_CHANGEOVER * total_changeovers
        + WEIGHT_ACTIVE_DAYS * total_order_span
        + WEIGHT_LINE_STABILITY * total_line_diff
        + WEIGHT_LOAD_SPREAD * load_spread
        + WEIGHT_OVER_PRODUCTION * total_over_line_days
        + 5 * total_prod_days
    )

    # =========================
    # 18. 返回变量
    # =========================
    variables = {
        "x": x,
        "y": y,
        "s": s,
        "e": e,
        "l": l,
        "u": u,
        "w": w,
        "diff": diff,
        "block_start": block_start,
        "block_end": block_end,
        "order_on_line_start": order_on_line_start,
        "active_block_start": active_block_start,
        "active_block_end": active_block_end,
        "prod_day": prod_day,
        "daily_load": daily_load,
        "load_spread": load_spread,
        "required_line_days": required_line_days,
        "over_line_days": over_line_days,
        "total_changeovers": total_changeovers,
        "total_active_days": total_active_days,
        "total_order_span": total_order_span,
        "total_line_diff": total_line_diff,
        "total_prod_days": total_prod_days,
        "total_over_line_days": total_over_line_days,
    }

    return model, variables