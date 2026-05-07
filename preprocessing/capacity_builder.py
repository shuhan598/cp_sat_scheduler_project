# =========================
# 文件说明：
# 这个文件负责根据停电计划，构建“产线-日期”维度的产能矩阵。
#
# 主要职责：
# 1. 生成每条产线每天的实际产能 line_capacity；
# 2. 生成每条产线每天是否可用 line_available；
# 3. 统计每天可用产线数 available_lines；
# 4. 识别全厂停电日 full_outage_days。
# =========================

import random

from config import (
    NUM_LINES,
    DAILY_CAPACITY,
    RECOVERY_RATIOS,
    RANDOM_SEED,
)


def build_line_capacity_matrix(
    power_outages,
    model_start_date,
    model_horizon
):
    """
    根据停电计划构建产线-日期产能矩阵。

    返回：
        line_capacity[i][t]
            第 i 条产线第 t 天的实际产能。

        line_available[i][t]
            第 i 条产线第 t 天是否可用，1 表示可用，0 表示停电不可用。

        available_lines[t]
            第 t 天可用产线数量。

        full_outage_days
            全厂停电日集合。
    """

    random.seed(RANDOM_SEED)

    line_capacity = [
        [DAILY_CAPACITY for _ in range(model_horizon)]
        for _ in range(NUM_LINES)
    ]

    line_available = [
        [1 for _ in range(model_horizon)]
        for _ in range(NUM_LINES)
    ]

    for outage in power_outages:
        start_date = outage["start_date"]
        end_date = outage["end_date"]
        affected_lines = outage["lines"]
        pre_outage_ratio = outage.get("pre_outage_ratio")

        start_idx = (start_date - model_start_date).days
        end_idx = (end_date - model_start_date).days

        # 停电前一天产能下降
        pre_day = start_idx - 1

        if 0 <= pre_day < model_horizon:
            ratio = pre_outage_ratio

            if ratio is None:
                ratio = random.uniform(0.55, 0.85)

            for i in affected_lines:
                line_capacity[i][pre_day] = int(
                    DAILY_CAPACITY * ratio
                )

        # 停电期间产能为 0
        for t in range(start_idx, end_idx + 1):
            if not (0 <= t < model_horizon):
                continue

            for i in affected_lines:
                line_capacity[i][t] = 0
                line_available[i][t] = 0

        # 停电结束后的产能恢复
        for offset, ratio in enumerate(RECOVERY_RATIOS):
            recover_day = end_idx + 1 + offset

            if not (0 <= recover_day < model_horizon):
                continue

            for i in affected_lines:
                # 如果恢复日又被其他停电覆盖，则不覆盖 0 产能。
                if line_available[i][recover_day] == 0:
                    continue

                line_capacity[i][recover_day] = int(
                    DAILY_CAPACITY * ratio
                )

    available_lines = []

    for t in range(model_horizon):
        available_lines.append(
            sum(line_available[i][t] for i in range(NUM_LINES))
        )

    full_outage_days = {
        t for t in range(model_horizon)
        if available_lines[t] == 0
    }

    return line_capacity, line_available, available_lines, full_outage_days