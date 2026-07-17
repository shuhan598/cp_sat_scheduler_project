# =========================
# 文件说明：
# 这个文件负责 CP-SAT 排产模型中的变量创建。
#
# 主要职责：
# 1. 创建核心决策变量；
# 2. 创建辅助变量；
# 3. 根据是否停电，创建不同形式的换线变量和波动变量。
# =========================

from config import (
    NUM_LINES,
)

from scheduler_model.model_helpers import (
    get_factory_work_days,
    get_line_work_days,
)


def create_core_variables(model, orders, horizon):
    """
    创建核心决策变量。

    x[i, j, t] = 1 表示产线 i 在第 t 天生产订单 j。

    y[j, t] = 1 表示订单 j 在第 t 天处于生产状态。

    s[j] 表示订单 j 在允许窗口内由模型选择的开工日。
    e[j] 表示订单 j 在允许窗口内由模型选择的完工日。

    l[j, t] 表示订单 j 在第 t 天占用多少条产线。

    u[i, t] = 1 表示产线 i 在第 t 天处于生产状态。
    """
    num_orders = len(orders)

    x = {}
    y = {}
    s = {}
    e = {}
    l = {}
    u = {}

    # x[i, j, t] = 1 表示产线 i 在第 t 天生产订单 j
    for i in range(NUM_LINES):
        for j in range(num_orders):
            for t in range(horizon):
                x[i, j, t] = model.NewBoolVar(
                    f"x_line{i}_order{j}_day{t}"
                )

    # y[j, t] = 1 表示订单 j 在第 t 天处于生产状态
    for j in range(num_orders):
        for t in range(horizon):
            y[j, t] = model.NewBoolVar(
                f"y_order{j}_day{t}"
            )

    # s[j] 表示订单 j 的开工日
    # e[j] 表示订单 j 的完工日
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
    for j in range(num_orders):
        for t in range(horizon):
            l[j, t] = model.NewIntVar(
                0,
                NUM_LINES,
                f"l_order{j}_day{t}"
            )

    # u[i, t] = 1 表示产线 i 在第 t 天处于生产状态
    for i in range(NUM_LINES):
        for t in range(horizon):
            u[i, t] = model.NewBoolVar(
                f"active_line{i}_day{t}"
            )

    return x, y, s, e, l, u


def create_auxiliary_variables(
    model,
    num_orders,
    horizon,
    line_available,
    available_lines,
    has_power_outage,
):
    """
    创建辅助变量。

    w:
    无停电模式：w[i, t] 表示产线 i 从第 t 天到第 t+1 天发生订单切换。
    有停电模式：w[i, idx] 表示产线 i 在相邻两个可用生产日之间发生订单切换。

    diff:
    无停电模式：diff[j,t] 表示自然相邻两天订单 j 的占线数变化。
    有停电模式：diff[j,idx] 表示相邻非全厂停电日之间订单 j 的占线数变化。

    block_start[i, j, t] = 1 表示订单 j 在第 t 天的连续产线块从产线 i 开始。
    block_end[i, j, t] = 1 表示订单 j 在第 t 天的连续产线块在产线 i 结束。

    order_on_line_start[i, j, t] = 1 表示产线 i 在第 t 天开始生产订单 j。

    active_block_start / active_block_end 只在无停电模式下使用，
    用于判断第 t 天整体开线块从哪里开始、在哪里结束。

    prod_day[t] = 1 表示第 t 天属于总体生产阶段。

    daily_load[t] 表示第 t 天总共开了多少条产线。

    load_spread = max_load - min_load。
    """
    w = {}
    diff = {}

    # =========================
    # 换线变量 w
    # =========================
    if not has_power_outage:
        # 无停电模式：w[i, t] 表示产线 i 从第 t 天到第 t+1 天发生订单切换
        for i in range(NUM_LINES):
            for t in range(horizon - 1):
                w[i, t] = model.NewBoolVar(
                    f"change_line{i}_day{t}"
                )
    else:
        # 有停电模式：w[i, idx] 表示产线 i 在相邻两个可用生产日之间发生订单切换
        for i in range(NUM_LINES):
            line_work_days = get_line_work_days(
                horizon,
                line_available,
                i,
            )

            for idx in range(len(line_work_days) - 1):
                w[i, idx] = model.NewBoolVar(
                    f"change_line{i}_workidx{idx}"
                )

    # =========================
    # 产线数稳定性变量 diff
    # =========================
    if not has_power_outage:
        # 无停电模式：diff[j,t] 表示自然相邻两天占线数变化
        for j in range(num_orders):
            for t in range(horizon - 1):
                diff[j, t] = model.NewIntVar(
                    0,
                    NUM_LINES,
                    f"diff_order{j}_day{t}"
                )
    else:
        # 有停电模式：diff[j,idx] 表示相邻非全厂停电日之间占线数变化
        work_days = get_factory_work_days(
            horizon,
            available_lines,
        )

        for j in range(num_orders):
            for idx in range(len(work_days) - 1):
                diff[j, idx] = model.NewIntVar(
                    0,
                    NUM_LINES,
                    f"diff_order{j}_workidx{idx}"
                )

    block_start = {}
    block_end = {}

    # block_start[i, j, t] = 1 表示订单 j 在第 t 天的连续产线块从产线 i 开始
    # block_end[i, j, t] = 1 表示订单 j 在第 t 天的连续产线块在产线 i 结束
    # 某一天订单的占线连在一起
    for i in range(NUM_LINES):
        for j in range(num_orders):
            for t in range(horizon):
                block_start[i, j, t] = model.NewBoolVar(
                    f"block_start_line{i}_order{j}_day{t}"
                )

                block_end[i, j, t] = model.NewBoolVar(
                    f"block_end_line{i}_order{j}_day{t}"
                )

    order_on_line_start = {}

    # order_on_line_start[i, j, t] = 1 表示产线 i 在第 t 天开始生产订单 j
    for i in range(NUM_LINES):
        for j in range(num_orders):
            for t in range(horizon):
                order_on_line_start[i, j, t] = model.NewBoolVar(
                    f"order{j}_start_on_line{i}_day{t}"
                )

    active_block_start = {}
    active_block_end = {}

    # active_block_start / active_block_end 只在无停电模式下使用
    if not has_power_outage:
        # active_block_start[i, t] = 1 表示第 t 天整体开线块从产线 i 开始
        # active_block_end[i, t] = 1 表示第 t 天整体开线块在产线 i 结束
        for i in range(NUM_LINES):
            for t in range(horizon):
                active_block_start[i, t] = model.NewBoolVar(
                    f"active_block_start_line{i}_day{t}"
                )

                active_block_end[i, t] = model.NewBoolVar(
                    f"active_block_end_line{i}_day{t}"
                )

    prod_day = {}

    # prod_day[t] = 1 表示第 t 天属于总体生产阶段
    for t in range(horizon):
        prod_day[t] = model.NewBoolVar(
            f"prod_day_{t}"
        )

    daily_load = {}

    # daily_load[t] 表示第 t 天总共开了多少条产线
    for t in range(horizon):
        daily_load[t] = model.NewIntVar(
            0,
            NUM_LINES,
            f"daily_load_day{t}"
        )

    max_load = model.NewIntVar(
        0,
        NUM_LINES,
        "max_load"
    )

    min_load = model.NewIntVar(
        0,
        NUM_LINES,
        "min_load"
    )

    load_spread = model.NewIntVar(
        0,
        NUM_LINES,
        "load_spread"
    )

    return {
        "w": w,
        "diff": diff,
        "block_start": block_start,
        "block_end": block_end,
        "order_on_line_start": order_on_line_start,
        "active_block_start": active_block_start,
        "active_block_end": active_block_end,
        "prod_day": prod_day,
        "daily_load": daily_load,
        "max_load": max_load,
        "min_load": min_load,
        "load_spread": load_spread,
    }