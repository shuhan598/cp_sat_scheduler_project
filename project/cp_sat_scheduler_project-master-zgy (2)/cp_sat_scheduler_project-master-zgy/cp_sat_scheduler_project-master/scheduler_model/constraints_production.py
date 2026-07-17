# =========================
# 文件说明：
# 这个文件负责生产阶段相关约束。
#
# 主要职责：
# 1. 计算 daily_load；
# 2. 处理普通模式下生产阶段连续和满线生产；
# 3. 处理插单模式下的空闲产线软惩罚；
# 4. 处理停电模式下全厂停电日和可用产线；
# 5. 计算 load_spread；
# 6. 返回目标函数和导出结果需要使用的生产阶段变量。
# =========================

from config import (
    NUM_LINES,
)

from scheduler_model.model_helpers import (
    get_factory_work_days,
)


def add_production_stage_constraints(
    model,
    num_orders,
    horizon,
    l,
    prod_day,
    daily_load,
    max_load,
    min_load,
    load_spread,
    available_lines,
    has_power_outage,
    enable_insert_mode,
):
    """
    添加生产阶段约束。

    返回：
        idle_lines:
            插单模式下每天空闲产线数。

        total_idle_lines:
            插单模式下总空闲产线数。

        total_insert_prod_days:
            插单模式下总生产天数。
    """

    # daily_load[t] = 第 t 天所有订单占用产线数之和
    for t in range(horizon):
        model.Add(
            daily_load[t] == sum(l[j, t] for j in range(num_orders))
        )

    # 插单模式新增：
    # idle_lines[t] 表示生产日中未使用的产线数。
    # 这不是硬约束，而是目标函数惩罚项。
    # 作用是引导插单排产尽量使用满 18 条产线，减少大量空白产线的情况。
    idle_lines = {}
    total_idle_lines = 0
    total_insert_prod_days = 0

    if not has_power_outage:
        if not enable_insert_mode:
            # 原逻辑：生产阶段必须是前缀连续块
            for t in range(horizon - 1):
                model.Add(prod_day[t] >= prod_day[t + 1])

            # 第一天必须进入生产阶段
            model.Add(prod_day[0] == 1)

            # 生产阶段每天 NUM_LINES 条线满产；非生产阶段 0 条线
            for t in range(horizon):
                model.Add(daily_load[t] == NUM_LINES * prod_day[t])
        else:
            # 插单模式：
            # 不再要求生产阶段必须从第 1 天开始连续到最后；
            # 不再要求生产日必须 18 条线全开。
            #
            # 但是会计算 idle_lines[t]，在目标函数中惩罚空闲产线，
            # 从而让模型“能满线就满线，确实有冲突才少开线”。
            for t in range(horizon):
                # prod_day[t] = 0 时，daily_load[t] 必须为 0
                model.Add(daily_load[t] <= NUM_LINES * prod_day[t])

                # prod_day[t] = 1 时，daily_load[t] 至少为 1
                model.Add(daily_load[t] >= prod_day[t])

                idle_lines[t] = model.NewIntVar(
                    0,
                    NUM_LINES,
                    f"idle_lines_day{t}"
                )

                # 如果 prod_day[t] = 1，则 idle_lines[t] = 18 - daily_load[t]
                # 如果 prod_day[t] = 0，则 daily_load[t] = 0，idle_lines[t] = 0
                model.Add(
                    idle_lines[t] == NUM_LINES * prod_day[t] - daily_load[t]
                )
    else:
        if not enable_insert_mode:
            # 停电逻辑：忽略全厂停电日后，生产阶段仍然连续
            work_days = get_factory_work_days(
                horizon,
                available_lines,
            )

            if work_days:
                model.Add(prod_day[work_days[0]] == 1)

            for idx in range(len(work_days) - 1):
                t1 = work_days[idx]
                t2 = work_days[idx + 1]
                model.Add(prod_day[t1] >= prod_day[t2])

            # 全厂停电日不算生产日
            for t in range(horizon):
                if available_lines[t] == 0:
                    model.Add(prod_day[t] == 0)

            # 生产日必须开满所有可用产线；非生产日 0 条线
            for t in range(horizon):
                model.Add(daily_load[t] == available_lines[t] * prod_day[t])
        else:
            # 插单 + 停电模式：
            # 保留停电日不可生产；
            # 但不再强制生产阶段在非停电日上连续，
            # 也不再强制生产日必须开满所有可用产线。
            #
            # 同样通过 idle_lines[t] 软惩罚空闲可用产线。
            for t in range(horizon):
                if available_lines[t] == 0:
                    model.Add(prod_day[t] == 0)
                    model.Add(daily_load[t] == 0)
                else:
                    # prod_day[t] = 0 时，daily_load[t] 必须为 0
                    model.Add(daily_load[t] <= available_lines[t] * prod_day[t])

                    # prod_day[t] = 1 时，daily_load[t] 至少为 1
                    model.Add(daily_load[t] >= prod_day[t])

                    idle_lines[t] = model.NewIntVar(
                        0,
                        available_lines[t],
                        f"idle_lines_day{t}"
                    )

                    model.Add(
                        idle_lines[t] == available_lines[t] * prod_day[t] - daily_load[t]
                    )

    if idle_lines:
        total_idle_lines = sum(idle_lines.values())

    if enable_insert_mode:
        total_insert_prod_days = sum(
            prod_day[t]
            for t in range(horizon)
        )

    model.AddMaxEquality(
        max_load,
        [daily_load[t] for t in range(horizon)]
    )

    model.AddMinEquality(
        min_load,
        [daily_load[t] for t in range(horizon)]
    )

    model.Add(load_spread == max_load - min_load)

    return (
        idle_lines,
        total_idle_lines,
        total_insert_prod_days,
    )