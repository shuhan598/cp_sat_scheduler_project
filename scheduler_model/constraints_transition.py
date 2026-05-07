# =========================
# 文件说明：
# 这个文件负责排产模型中的跨日衔接类约束。
#
# 主要职责：
# 1. 添加换线变量约束；
# 2. 添加订单占线数稳定性约束；
# 3. 兼容普通模式和停电模式。
# =========================

from config import (
    NUM_LINES,
)

from scheduler_model.model_helpers import (
    get_factory_work_days,
    get_line_work_days,
)


def add_changeover_constraints(
    model,
    num_orders,
    horizon,
    x,
    w,
    line_available,
    has_power_outage,
):
    """
    添加换线变量约束。

    无停电模式：
        w[i, t] 表示产线 i 从第 t 天到第 t+1 天是否发生订单切换。

    有停电模式：
        w[i, idx] 表示产线 i 在相邻两个可用生产日之间是否发生订单切换。
    """

    if not has_power_outage:
        # 原逻辑：按自然相邻日判断换线
        for i in range(NUM_LINES):
            for t in range(horizon - 1):
                for j in range(num_orders):
                    for k in range(num_orders):
                        if j != k:
                            model.Add(
                                w[i, t] >= x[i, j, t] + x[i, k, t + 1] - 1
                            )
    else:
        # 停电逻辑：按该产线相邻可用日判断换线
        for i in range(NUM_LINES):
            line_work_days = get_line_work_days(
                horizon,
                line_available,
                i,
            )

            for idx in range(len(line_work_days) - 1):
                t1 = line_work_days[idx]
                t2 = line_work_days[idx + 1]

                for j in range(num_orders):
                    for k in range(num_orders):
                        if j != k:
                            model.Add(
                                w[i, idx] >= x[i, j, t1] + x[i, k, t2] - 1
                            )


def add_line_stability_constraints(
    model,
    num_orders,
    horizon,
    l,
    diff,
    available_lines,
    has_power_outage,
):
    """
    添加订单占线数稳定性约束。

    无停电模式：
        按自然相邻日计算订单占线数波动。

    有停电模式：
        忽略全厂停电日，只在相邻非全厂停电日之间计算订单占线数波动。
    """

    if not has_power_outage:
        # 原逻辑：按自然相邻日计算订单占线数波动
        for j in range(num_orders):
            for t in range(horizon - 1):
                model.Add(diff[j, t] >= l[j, t] - l[j, t + 1])
                model.Add(diff[j, t] >= l[j, t + 1] - l[j, t])
    else:
        # 停电逻辑：忽略全厂停电日后计算订单占线数波动
        work_days = get_factory_work_days(
            horizon,
            available_lines,
        )

        for j in range(num_orders):
            for idx in range(len(work_days) - 1):
                t1 = work_days[idx]
                t2 = work_days[idx + 1]

                model.Add(diff[j, idx] >= l[j, t1] - l[j, t2])
                model.Add(diff[j, idx] >= l[j, t2] - l[j, t1])