import math

from config import (
    NUM_LINES,
    DAILY_CAPACITY,
    MIN_LINES_PER_ACTIVE_ORDER,
    OVER_PRODUCTION_UNIT,
)


def normalize_capacity_inputs(
    horizon,
    line_capacity=None,
    line_available=None,
    available_lines=None,
    full_outage_days=None,
    has_power_outage=False,
):
    """
    统一处理停电模式和非停电模式下的产能输入。

    无停电模式：
    1. 每条产线每天默认产能为 DAILY_CAPACITY；
    2. 每条产线每天都可用；
    3. 每天可用产线数为 NUM_LINES；
    4. 不存在全厂停电日。

    有停电模式：
    1. 每条产线每天使用 line_capacity[i][t] 作为真实产能；
    2. 停电产线 line_available[i][t] = 0；
    3. 每天可用产线数由 available_lines[t] 给出；
    4. full_outage_days 用于标记全厂停电日。
    """
    if has_power_outage:
        if line_capacity is None or line_available is None or available_lines is None:
            raise ValueError(
                "启用停电模式时，必须传入 line_capacity、line_available、available_lines。"
            )

        if full_outage_days is None:
            full_outage_days = [
                1 if available_lines[t] == 0 else 0
                for t in range(horizon)
            ]

        return line_capacity, line_available, available_lines, full_outage_days

    line_capacity = [
        [DAILY_CAPACITY for _ in range(horizon)]
        for _ in range(NUM_LINES)
    ]

    line_available = [
        [1 for _ in range(horizon)]
        for _ in range(NUM_LINES)
    ]

    available_lines = [
        NUM_LINES for _ in range(horizon)
    ]

    full_outage_days = [
        0 for _ in range(horizon)
    ]

    return line_capacity, line_available, available_lines, full_outage_days


def get_factory_work_days(horizon, available_lines):
    """
    返回非全厂停电日。

    有停电模式下：
    1. 订单允许被全厂停电日打断；
    2. 但忽略全厂停电日后，订单仍需连续；
    3. 生产阶段忽略全厂停电日后仍需连续；
    4. 订单占线数波动也只在非全厂停电日之间计算。
    """
    return [
        t for t in range(horizon)
        if available_lines[t] > 0
    ]


def get_line_work_days(horizon, line_available, line_idx):
    """
    返回某一条产线自己的可用日期。

    有停电模式下：
    1. 同一产线同一订单允许被该产线停电日打断；
    2. 但忽略该线停电日后，同一产线同一订单仍最多一个连续段；
    3. 该产线的换线判断，也只在该产线相邻可用日之间计算。
    """
    return [
        t for t in range(horizon)
        if line_available[line_idx][t] == 1
    ]


def add_basic_linking_constraints(
    model,
    num_orders,
    horizon,
    x,
    y,
    l,
    u,
    line_available,
    has_power_outage,
):
    """
    添加基础衔接约束。

    包含原代码中的：
    2. 产线独占约束；
    3. u[i,t] 与 x[i,j,t] 衔接；
    3.1 停电产线不可生产；
    4. l[j,t] 与 x[i,j,t] 衔接；
    5. y[j,t] 与 l[j,t] 衔接。
    """

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
    # 3.1 停电产线不可生产
    # =========================
    if has_power_outage:
        for i in range(NUM_LINES):
            for t in range(horizon):
                if line_available[i][t] == 0:
                    model.Add(u[i, t] == 0)

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
            model.Add(
                l[j, t] >= MIN_LINES_PER_ACTIVE_ORDER * y[j, t]
            )
            model.Add(
                l[j, t] <= NUM_LINES * y[j, t]
            )


def add_one_block_on_order_day_constraints(
    model,
    num_orders,
    horizon,
    x,
    y,
    block_start,
    block_end,
    line_available,
    has_power_outage,
):
    """
    添加同一订单同一天的产线连续块约束。

    业务含义：
    同一订单在同一天如果生产，它占用的产线必须形成一个连续块。

    无停电模式：
    - 按自然产线 0 ~ NUM_LINES-1 判断连续。

    有停电模式：
    - 只考虑当天可用产线；
    - 停电产线不参与连续性判断；
    - 避免因为中间某条线停电，把本来合理的可用产线块误判为不连续。
    """

    # =========================
    # 6. 同一订单同一天的产线连续块约束
    # =========================
    for j in range(num_orders):
        for t in range(horizon):
            if has_power_outage:
                # 停电模式下，只考虑当天可用产线
                lines_today = [
                    i for i in range(NUM_LINES)
                    if line_available[i][t] == 1
                ]
            else:
                # 无停电模式下，考虑全部产线
                lines_today = list(range(NUM_LINES))

            if not lines_today:
                model.Add(y[j, t] == 0)
                continue

            for idx, i in enumerate(lines_today):
                # block_start
                if idx == 0:
                    model.Add(block_start[i, j, t] == x[i, j, t])
                else:
                    prev_i = lines_today[idx - 1]
                    model.Add(
                        block_start[i, j, t] >= x[i, j, t] - x[prev_i, j, t]
                    )
                    model.Add(
                        block_start[i, j, t] <= x[i, j, t]
                    )
                    model.Add(
                        block_start[i, j, t] <= 1 - x[prev_i, j, t]
                    )

                # block_end
                if idx == len(lines_today) - 1:
                    model.Add(block_end[i, j, t] == x[i, j, t])
                else:
                    next_i = lines_today[idx + 1]
                    model.Add(
                        block_end[i, j, t] >= x[i, j, t] - x[next_i, j, t]
                    )
                    model.Add(
                        block_end[i, j, t] <= x[i, j, t]
                    )
                    model.Add(
                        block_end[i, j, t] <= 1 - x[next_i, j, t]
                    )

            model.Add(
                sum(block_start[i, j, t] for i in lines_today) == y[j, t]
            )
            model.Add(
                sum(block_end[i, j, t] for i in lines_today) == y[j, t]
            )


def add_active_line_block_constraints(
    model,
    horizon,
    u,
    prod_day,
    active_block_start,
    active_block_end,
):
    """
    添加同一天所有开线产线整体连续约束。

    只在无停电模式下使用。

    原因：
    有停电模式下，停电可能把可用产线切成多段，
    因此不能再要求所有开线产线在自然产线编号上整体连续。
    """

    # =========================
    # 7. 同一天所有开线产线整体连续约束
    #    有停电模式下取消，因为停电可能把可用产线切成多段。
    # =========================
    for t in range(horizon):
        for i in range(NUM_LINES):
            if i == 0:
                model.Add(active_block_start[i, t] == u[i, t])
            else:
                model.Add(
                    active_block_start[i, t] >= u[i, t] - u[i - 1, t]
                )
                model.Add(
                    active_block_start[i, t] <= u[i, t]
                )
                model.Add(
                    active_block_start[i, t] <= 1 - u[i - 1, t]
                )

            if i == NUM_LINES - 1:
                model.Add(active_block_end[i, t] == u[i, t])
            else:
                model.Add(
                    active_block_end[i, t] >= u[i, t] - u[i + 1, t]
                )
                model.Add(
                    active_block_end[i, t] <= u[i, t]
                )
                model.Add(
                    active_block_end[i, t] <= 1 - u[i + 1, t]
                )

        # 若 prod_day[t] = 1，当天所有开线产线必须形成一个整体连续块
        # 若 prod_day[t] = 0，当天没有开线块
        model.Add(
            sum(active_block_start[i, t] for i in range(NUM_LINES)) == prod_day[t]
        )
        model.Add(
            sum(active_block_end[i, t] for i in range(NUM_LINES)) == prod_day[t]
        )


def add_available_active_line_block_constraints(
    model,
    horizon,
    u,
    prod_day,
    active_block_start,
    active_block_end,
    line_available,
):
    """
    添加停电模式下的开线产线整体连续约束。

    与 add_active_line_block_constraints 的区别：
    1. 只在当天可用产线序列中判断连续；
    2. 停电产线不参与连续性判断；
    3. 如果 active_block_start / active_block_end 中没有对应变量，
       会在这里自动创建，避免停电模式下 KeyError。
    """

    for t in range(horizon):
        lines_today = [
            i for i in range(NUM_LINES)
            if line_available[i][t] == 1
        ]

        if not lines_today:
            model.Add(prod_day[t] == 0)
            continue

        # 停电模式下，active_block_start / active_block_end
        # 可能没有提前创建，所以这里按需创建。
        for i in lines_today:
            if (i, t) not in active_block_start:
                active_block_start[i, t] = model.NewBoolVar(
                    f"available_active_block_start_line{i}_day{t}"
                )

            if (i, t) not in active_block_end:
                active_block_end[i, t] = model.NewBoolVar(
                    f"available_active_block_end_line{i}_day{t}"
                )

        for idx, i in enumerate(lines_today):
            if idx == 0:
                model.Add(active_block_start[i, t] == u[i, t])
            else:
                prev_i = lines_today[idx - 1]

                model.Add(
                    active_block_start[i, t] >= u[i, t] - u[prev_i, t]
                )
                model.Add(
                    active_block_start[i, t] <= u[i, t]
                )
                model.Add(
                    active_block_start[i, t] <= 1 - u[prev_i, t]
                )

            if idx == len(lines_today) - 1:
                model.Add(active_block_end[i, t] == u[i, t])
            else:
                next_i = lines_today[idx + 1]

                model.Add(
                    active_block_end[i, t] >= u[i, t] - u[next_i, t]
                )
                model.Add(
                    active_block_end[i, t] <= u[i, t]
                )
                model.Add(
                    active_block_end[i, t] <= 1 - u[next_i, t]
                )

        model.Add(
            sum(active_block_start[i, t] for i in lines_today) == prod_day[t]
        )
        model.Add(
            sum(active_block_end[i, t] for i in lines_today) == prod_day[t]
        )


def add_order_window_constraints(
    model,
    orders,
    horizon,
    y,
    l,
):
    """
    添加释放期和交期窗口约束。

    订单只能在 release ~ due 时间窗口内生产。

    如果日期不在订单允许窗口内：
    - y[j,t] = 0
    - l[j,t] = 0
    """

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


def add_at_most_one_active_segment(
    model,
    bool_by_day,
    ordered_days,
    name_prefix,
    external_start_vars=None,
):
    """
    通用连续段约束。

    约束含义：
    在 ordered_days 指定的日期序列上，bool_by_day 最多只能出现一个连续的 1 段。

    例如允许：
        0 0 1 1 1 0 0

    不允许：
        0 1 1 0 1 1

    ordered_days 的用法：
    1. 无停电模式下，ordered_days = list(range(horizon))；
    2. 订单连续生产时，有停电模式下 ordered_days = 非全厂停电日；
    3. 产线连续开线时，有停电模式下 ordered_days = 该产线可用日；
    4. 同一产线同一订单连续生产时，有停电模式下 ordered_days = 该产线可用日。

    external_start_vars：
    如果外部已经创建了 start 变量，例如 order_on_line_start[i,j,t]，
    可以传进来复用，避免破坏原来的变量返回结构。
    """
    start_flags = []

    for idx, t in enumerate(ordered_days):
        if external_start_vars is None:
            start = model.NewBoolVar(
                f"{name_prefix}_start_idx{idx}_day{t}"
            )
        else:
            start = external_start_vars[t]

        start_flags.append(start)

        if idx == 0:
            model.Add(start == bool_by_day[t])
        else:
            prev_t = ordered_days[idx - 1]

            model.Add(
                start >= bool_by_day[t] - bool_by_day[prev_t]
            )
            model.Add(
                start <= bool_by_day[t]
            )
            model.Add(
                start <= 1 - bool_by_day[prev_t]
            )

    model.Add(sum(start_flags) <= 1)

    return start_flags


def _build_adjacent_work_day_pairs(horizon, available_lines):
    """
    构造相邻可生产日对。

    普通模式：
        等价于相邻自然日期。

    停电模式：
        自动跳过全厂停电日。
        例如：
            3/10 可生产
            3/11 全厂停电
            3/12 全厂停电
            3/13 可生产

        会生成：
            (3/10, 3/13)
    """
    work_days = get_factory_work_days(
        horizon,
        available_lines,
    )

    return [
        (work_days[idx], work_days[idx + 1])
        for idx in range(len(work_days) - 1)
    ]


def _build_outage_resume_day_pairs(horizon, available_lines):
    """
    构造全厂停电前后恢复生产的日期对。

    只针对全厂停电区间：
    1. 找到停电前最后一个可生产日；
    2. 找到停电后第一个可生产日；
    3. 对这两个日期额外加强产线恢复惩罚。
    """
    outage_pairs = []

    t = 0

    while t < horizon:
        if available_lines[t] > 0:
            t += 1
            continue

        outage_start = t

        while t < horizon and available_lines[t] == 0:
            t += 1

        outage_end = t - 1

        pre_day = outage_start - 1
        while pre_day >= 0 and available_lines[pre_day] == 0:
            pre_day -= 1

        post_day = outage_end + 1
        while post_day < horizon and available_lines[post_day] == 0:
            post_day += 1

        if pre_day >= 0 and post_day < horizon:
            outage_pairs.append((pre_day, post_day))

    return outage_pairs


def _add_extra_line_drift_for_day_pairs(
    model,
    num_orders,
    x,
    y,
    l,
    day_pairs,
    line_available=None,
    target_order_indices=None,
    name_prefix="extra_line_drift",
):
    """
    对指定日期对添加“额外产线漂移”惩罚变量。

    核心逻辑：
        额外漂移 = 产线组合变化量 - 正常加减线数量

    正常加线：
        Line 8,9,10 -> Line 8,9,10,11
        不重点惩罚。

    正常减线：
        Line 8,9,10,11 -> Line 8,9,10
        不重点惩罚。

    整体漂移：
        Line 8,9,10 -> Line 9,10,11
        要惩罚。

    停电模式下：
        如果某条线在前后任意一天不可用，则不比较这条线，
        避免把“产线不可用”误判为订单漂移。
    """
    if target_order_indices is None:
        target_order_indices = list(range(num_orders))

    extra_position_change = {}

    for j in target_order_indices:
        for pair_idx, (t1, t2) in enumerate(day_pairs):
            both_active = model.NewBoolVar(
                f"{name_prefix}_both_active_order{j}_pair{pair_idx}_day{t1}_{t2}"
            )

            model.Add(both_active <= y[j, t1])
            model.Add(both_active <= y[j, t2])
            model.Add(both_active >= y[j, t1] + y[j, t2] - 1)

            comparable_lines = []

            for i in range(NUM_LINES):
                if line_available is not None:
                    if line_available[i][t1] == 0 or line_available[i][t2] == 0:
                        continue

                comparable_lines.append(i)

            change_vars = []

            for i in comparable_lines:
                change = model.NewBoolVar(
                    f"{name_prefix}_order{j}_line{i}_pair{pair_idx}_day{t1}_{t2}"
                )

                change_vars.append(change)

                model.Add(
                    change >= x[i, j, t1] - x[i, j, t2]
                ).OnlyEnforceIf(both_active)

                model.Add(
                    change >= x[i, j, t2] - x[i, j, t1]
                ).OnlyEnforceIf(both_active)

                model.Add(
                    change <= x[i, j, t1] + x[i, j, t2]
                ).OnlyEnforceIf(both_active)

                model.Add(
                    change <= 2 - x[i, j, t1] - x[i, j, t2]
                ).OnlyEnforceIf(both_active)

                model.Add(change == 0).OnlyEnforceIf(both_active.Not())

            total_position_change = model.NewIntVar(
                0,
                NUM_LINES,
                f"{name_prefix}_total_position_change_order{j}_pair{pair_idx}_day{t1}_{t2}"
            )

            if change_vars:
                model.Add(total_position_change == sum(change_vars))
            else:
                model.Add(total_position_change == 0)

            line_count_delta = model.NewIntVar(
                -NUM_LINES,
                NUM_LINES,
                f"{name_prefix}_line_count_delta_order{j}_pair{pair_idx}_day{t1}_{t2}"
            )

            line_count_diff = model.NewIntVar(
                0,
                NUM_LINES,
                f"{name_prefix}_line_count_diff_order{j}_pair{pair_idx}_day{t1}_{t2}"
            )

            if comparable_lines:
                model.Add(
                    line_count_delta ==
                    sum(x[i, j, t2] for i in comparable_lines)
                    - sum(x[i, j, t1] for i in comparable_lines)
                )
            else:
                model.Add(line_count_delta == 0)

            model.AddAbsEquality(
                line_count_diff,
                line_count_delta,
            )

            extra_change = model.NewIntVar(
                0,
                NUM_LINES,
                f"{name_prefix}_extra_change_order{j}_pair{pair_idx}_day{t1}_{t2}"
            )

            model.Add(
                extra_change >= total_position_change - line_count_diff
            ).OnlyEnforceIf(both_active)

            model.Add(extra_change == 0).OnlyEnforceIf(both_active.Not())

            extra_position_change[j, t1, t2] = extra_change

    if extra_position_change:
        total_extra_position_change = sum(
            extra_position_change.values()
        )
    else:
        total_extra_position_change = 0

    return extra_position_change, total_extra_position_change


def add_order_line_position_stability_constraints(
    model,
    num_orders,
    horizon,
    x,
    y,
    l,
    available_lines,
    line_available=None,
    target_order_indices=None,
    name_prefix="order_line_extra_drift",
):
    """
    添加通用订单跨日产线额外漂移惩罚。

    适用：
    1. 普通排产；
    2. 停电排产；
    3. 插单排产。

    规则：
    订单只要在相邻有效生产日都生产，
    就尽量沿用原产线号。

    允许：
    1. 正常加线；
    2. 正常减线；
    3. 必要换线。

    惩罚：
    扣除正常加减线之后的额外产线漂移。
    """
    day_pairs = _build_adjacent_work_day_pairs(
        horizon=horizon,
        available_lines=available_lines,
    )

    return _add_extra_line_drift_for_day_pairs(
        model=model,
        num_orders=num_orders,
        x=x,
        y=y,
        l=l,
        day_pairs=day_pairs,
        line_available=line_available,
        target_order_indices=target_order_indices,
        name_prefix=name_prefix,
    )


def add_outage_resume_line_position_constraints(
    model,
    num_orders,
    horizon,
    x,
    y,
    l,
    available_lines,
    line_available=None,
    target_order_indices=None,
    name_prefix="outage_resume_extra_drift",
):
    """
    添加停电前后恢复原产线的专项惩罚。

    只比较：
        全厂停电前最后一个可生产日
        和
        全厂停电后第一个可生产日

    作用：
    如果订单跨过停电区间继续生产，
    停电后更强烈地倾向于恢复停电前使用过的产线号。
    """
    outage_resume_pairs = _build_outage_resume_day_pairs(
        horizon=horizon,
        available_lines=available_lines,
    )

    return _add_extra_line_drift_for_day_pairs(
        model=model,
        num_orders=num_orders,
        x=x,
        y=y,
        l=l,
        day_pairs=outage_resume_pairs,
        line_available=line_available,
        target_order_indices=target_order_indices,
        name_prefix=name_prefix,
    )


def add_order_start_end_linking_constraints(
    model,
    num_orders,
    horizon,
    y,
    s,
    e,
):
    """
    添加 s[j], e[j] 与 y[j,t] 的衔接约束。

    如果订单 j 在第 t 天生产，即 y[j,t] = 1，则：
    - s[j] <= t
    - e[j] >= t

    注意：
    这里没有显式强制 s[j] 等于第一个生产日，
    也没有显式强制 e[j] 等于最后一个生产日。

    但目标函数会最小化：
        e[j] - s[j] + 1

    因此在最优解中，s[j] 和 e[j] 通常会被压缩到实际生产段的首尾。
    """

    # =========================
    # 10. s[j], e[j] 与 y[j,t] 的衔接
    # =========================
    for j in range(num_orders):
        for t in range(horizon):
            model.Add(s[j] <= t).OnlyEnforceIf(y[j, t])
            model.Add(e[j] >= t).OnlyEnforceIf(y[j, t])


def add_capacity_constraints(
    model,
    orders,
    horizon,
    x,
    l,
    line_capacity,
    has_power_outage,
):
    """
    添加订单产能约束。

    无停电模式：
    1. 按线天数满足订单需求；
    2. required_line_days[j] = ceil(quantity / DAILY_CAPACITY)；
    3. over_line_days[j] 表示超出的线天数。

    有停电模式：
    1. 按真实累计产量满足订单需求；
    2. actual_output[j] = sum(line_capacity[i][t] * x[i,j,t])；
    3. over_output[j] 表示真实超产数量；
    4. over_output_units[j] 表示按 OVER_PRODUCTION_UNIT 折算后的超产单位。
    """
    required_line_days = {}
    over_line_days = {}

    actual_output = {}
    over_output = {}
    over_output_units = {}

    # =========================
    # 13. 订单产能约束
    # =========================
    if not has_power_outage:
        # 原逻辑：按线天数满足订单需求
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
    else:
        # 停电逻辑：按真实累计产量满足订单需求
        max_possible_output = sum(
            line_capacity[i][t]
            for i in range(NUM_LINES)
            for t in range(horizon)
        )

        for j, order in enumerate(orders):
            required_line_days[j] = math.ceil(
                order["quantity"] / DAILY_CAPACITY
            )

            actual_output[j] = model.NewIntVar(
                0,
                max_possible_output,
                f"actual_output_order{j}"
            )

            over_output[j] = model.NewIntVar(
                0,
                max_possible_output,
                f"over_output_order{j}"
            )

            over_output_units[j] = model.NewIntVar(
                0,
                math.ceil(max_possible_output / OVER_PRODUCTION_UNIT),
                f"over_output_units_order{j}"
            )

            total_output_j = sum(
                line_capacity[i][t] * x[i, j, t]
                for i in range(NUM_LINES)
                for t in range(horizon)
            )

            model.Add(actual_output[j] == total_output_j)
            model.Add(actual_output[j] >= order["quantity"])
            model.Add(over_output[j] == actual_output[j] - order["quantity"])

            # over_output_units 近似表示 ceil(over_output / OVER_PRODUCTION_UNIT)
            # 在目标函数最小化时，该约束会让它取到最小可行值。
            model.Add(
                over_output_units[j] * OVER_PRODUCTION_UNIT >= over_output[j]
            )

    return (
        required_line_days,
        over_line_days,
        actual_output,
        over_output,
        over_output_units,
    )