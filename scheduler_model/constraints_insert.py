# =========================
# 文件说明：
# 这个文件负责插单模式相关的辅助约束和软惩罚函数。
#
# 主要职责：
# 1. 判断旧排产计划中的非订单标记；
# 2. 构造插单模式下的软交期订单；
# 3. 添加插单模式下的释放期约束；
# 4. 识别加量订单的优先延续产线；
# 5. 判断加量订单合理挤占区域；
# 6. 添加订单分段惩罚；
# 7. 添加插单订单 / 加量订单的产线位置稳定性惩罚。
# =========================

from config import (
    NUM_LINES,
    QUANTITY_INCREASE_LOOKBACK_DAYS,
    WEIGHT_PLAN_CHANGE,
    WEIGHT_QUANTITY_INCREASE_CHANGE,
)

from scheduler_model.model_helpers import (
    get_factory_work_days,
)


NON_ORDER_LABELS = {
    "",
    "停电",
    "停电检修",
    "检修",
    "休息",
    "空闲",
}


def _is_non_order_label(value):
    """
    判断旧排产计划中的单元格是否是非订单标记。

    例如：
    - 停电检修
    - 空闲
    - 空字符串
    """

    if value is None:
        return True

    text = str(value).strip()

    if not text:
        return True

    return text in NON_ORDER_LABELS


def _build_soft_due_orders(orders, horizon, enable_insert_mode):
    """
    构造模型内部使用的订单列表。

    普通排产：
    仍然使用订单原本 due，保持原来的硬交期逻辑。

    插单排产：
    使用软交期。
    原来的 due 不再作为“禁止生产”的硬边界，
    而是作为延期天数计算基准。
    模型内部把 due 放宽到 horizon - 1，
    使订单可以排到后续月份继续生产。
    """

    if not enable_insert_mode:
        return orders

    model_orders = []

    for order in orders:
        model_order = dict(order)
        model_order["_original_due"] = order["due"]
        model_order["due"] = horizon - 1
        model_orders.append(model_order)

    return model_orders


def _add_release_only_window_constraints(
    model,
    orders,
    horizon,
    x,
    y,
    l,
):
    """
    插单模式下的软交期窗口约束。

    只保留“最早开工之前不能生产”的硬约束，
    不再把最晚完工日期作为禁止生产的硬边界。

    即：
    - t < release 时不能生产；
    - t > 原 due 后可以继续生产，但会产生延期惩罚。
    """

    for j, order in enumerate(orders):
        release = order["release"]

        for t in range(horizon):
            if t < release:
                model.Add(y[j, t] == 0)
                model.Add(l[j, t] == 0)

                for i in range(NUM_LINES):
                    model.Add(x[i, j, t] == 0)


def _build_quantity_continue_lines(
    previous_plan,
    quantity_increased_order_names,
    freeze_until_day,
    horizon,
):
    """
    识别加量订单的优先延续产线。

    逻辑：
    - 对于加量订单 A；
    - 查看插单日前 QUANTITY_INCREASE_LOOKBACK_DAYS 天；
    - 如果某条线在这段时间生产过 A；
    - 则认为这条线是 A 的优先延续产线。

    返回：
        continue_lines_by_order[订单名] = {line_idx1, line_idx2, ...}
    """

    continue_lines_by_order = {
        order_name: set()
        for order_name in quantity_increased_order_names
    }

    if not previous_plan or not quantity_increased_order_names:
        return continue_lines_by_order

    if freeze_until_day is None:
        return continue_lines_by_order

    freeze_until_day = min(int(freeze_until_day), horizon - 1)

    if freeze_until_day < 0:
        return continue_lines_by_order

    lookback_start = max(
        0,
        freeze_until_day - QUANTITY_INCREASE_LOOKBACK_DAYS + 1
    )

    for (line_idx, day_idx), old_name in previous_plan.items():
        if day_idx < lookback_start or day_idx > freeze_until_day:
            continue

        if old_name in quantity_increased_order_names:
            continue_lines_by_order[old_name].add(line_idx)

    return continue_lines_by_order


def _is_low_penalty_quantity_increase_cell(
    line_idx,
    old_order_name,
    quantity_continue_lines_by_order,
):
    """
    判断某个旧计划单元格是否属于“加量订单合理挤占区域”。

    例如：
    原计划 Line1 在插单日前生产 A，后续准备切到 B；
    现在 A 加量，Line1 继续生产 A，把 B 往后顺延。
    这种扰动是合理的，不应按普通扰动重罚。

    当前规则：
    - 如果某条产线是任一加量订单的优先延续产线；
    - 且旧单元格不是这个加量订单本身；
    - 则该单元格的扰动使用较低惩罚权重。

    说明：
    这是软目标，不是硬约束。
    """

    if _is_non_order_label(old_order_name):
        return False

    for inc_order_name, line_set in quantity_continue_lines_by_order.items():
        if line_idx in line_set and old_order_name != inc_order_name:
            return True

    return False


def _add_segment_count_penalty(
    model,
    bool_by_day,
    ordered_days,
    name_prefix,
    require_at_least_one_segment=False,
):
    """
    统计一个布尔序列中的生产段数量，并返回额外分段惩罚变量。

    业务含义：
    插单模式下，原订单允许被插单打断后续产，
    例如：
        A A A 插单 插单 A A

    这时订单 A 从一个连续段变成两个连续段。
    模型允许这种情况发生，但会对“额外生产段”加入惩罚。

    参数：
    bool_by_day:
        某个订单或某条产线-订单在各日期上的生产状态。
        例如：
            y[j,t]
            x[i,j,t]

    ordered_days:
        需要检查连续性的日期序列。
        无停电时通常是自然日；
        停电时可以是排除停电日后的可生产日。

    require_at_least_one_segment:
        True：
            用于订单整体分段。
            因为每个订单至少要生产一天，所以总段数至少为 1。
            额外分段数 = 总段数 - 1。

        False：
            用于同一产线同一订单分段。
            某条产线可能完全不生产某个订单，所以总段数可以为 0。
            额外分段数 = max(0, 总段数 - 1)。
    """

    segment_start = {}

    for idx, t in enumerate(ordered_days):
        start_var = model.NewBoolVar(
            f"{name_prefix}_segment_start_day{t}"
        )

        segment_start[t] = start_var

        current = bool_by_day[t]

        if idx == 0:
            # 第一个可检查日期：
            # 如果当天生产，则它就是一个生产段开始。
            model.Add(start_var == current)
        else:
            prev_t = ordered_days[idx - 1]
            previous = bool_by_day[prev_t]

            # start_var = 1 当且仅当：
            # previous = 0 且 current = 1
            model.Add(start_var >= current - previous)
            model.Add(start_var <= current)
            model.Add(start_var <= 1 - previous)

    max_segments = max(1, len(ordered_days))

    total_segments = model.NewIntVar(
        0,
        max_segments,
        f"{name_prefix}_total_segments"
    )

    if segment_start:
        model.Add(total_segments == sum(segment_start.values()))
    else:
        model.Add(total_segments == 0)

    extra_segments = model.NewIntVar(
        0,
        max_segments,
        f"{name_prefix}_extra_segments"
    )

    if require_at_least_one_segment and ordered_days:
        # 订单整体分段：
        # 每个订单至少生产一天，因此总段数至少为 1。
        # 如果只有一个连续段，则 extra_segments = 0；
        # 如果有两个连续段，则 extra_segments = 1。
        model.Add(extra_segments == total_segments - 1)
    else:
        # 产线-订单分段：
        # 某条产线可能完全不生产该订单，此时 total_segments = 0，
        # extra_segments 应为 0。
        #
        # 这里不用 AddMaxEquality，是为了保持线性目标更简单。
        # 因为 extra_segments 会进入目标函数最小化，
        # 所以它会自动取满足约束的最小值。
        model.Add(extra_segments >= total_segments - 1)
        model.Add(extra_segments <= total_segments)

    return segment_start, total_segments, extra_segments


def _add_insert_line_stability_penalty(
    model,
    orders,
    horizon,
    x,
    y,
    target_order_names,
    has_power_outage=False,
    available_lines=None,
):
    """
    插单模式下的订单产线位置稳定性惩罚。

    业务含义：
    对插单订单和加量订单，鼓励同一订单在相邻生产日继续使用相同产线。

    例如：
    如果宥阳今天使用 Line 1、2、3，
    明天也尽量继续使用 Line 1、2、3。

    注意：
    这里是软约束，不会强制固定产线；
    如果为了满足交期、冻结计划或产能必须换线，模型仍然允许换线，
    但会在目标函数中产生惩罚。
    """

    target_order_names = set(target_order_names or [])

    if not target_order_names:
        return {}, 0

    if not has_power_outage:
        ordered_days = list(range(horizon))
    else:
        ordered_days = get_factory_work_days(
            horizon,
            available_lines,
        )

    insert_line_stability_change = {}

    for j, order in enumerate(orders):
        order_name = order["name"]

        if order_name not in target_order_names:
            continue

        for idx in range(len(ordered_days) - 1):
            t1 = ordered_days[idx]
            t2 = ordered_days[idx + 1]

            both_active = model.NewBoolVar(
                f"insert_line_stability_both_active_order{j}_day{t1}_{t2}"
            )

            model.Add(both_active <= y[j, t1])
            model.Add(both_active <= y[j, t2])
            model.Add(both_active >= y[j, t1] + y[j, t2] - 1)

            for i in range(NUM_LINES):
                change = model.NewBoolVar(
                    f"insert_line_stability_change_line{i}_order{j}_day{t1}_{t2}"
                )

                insert_line_stability_change[i, j, t1, t2] = change

                # 如果订单 j 在 t1、t2 两天都生产，
                # 则惩罚同一产线在两天之间是否从用到不用、或从不用到用。
                model.Add(
                    change >= x[i, j, t1] - x[i, j, t2]
                ).OnlyEnforceIf(both_active)

                model.Add(
                    change >= x[i, j, t2] - x[i, j, t1]
                ).OnlyEnforceIf(both_active)

                # 如果订单在两天中至少有一天不生产，则不计算位置稳定性惩罚。
                model.Add(change == 0).OnlyEnforceIf(both_active.Not())

    if insert_line_stability_change:
        total_insert_line_stability = sum(
            insert_line_stability_change.values()
        )
    else:
        total_insert_line_stability = 0

    return insert_line_stability_change, total_insert_line_stability


def add_insert_tardiness_constraints(
    model,
    orders,
    num_orders,
    horizon,
    e,
    original_due,
    enable_insert_mode,
):
    """
    插单模式：软交期延期变量。

    业务含义：
    插单模式下，订单可以超过原最晚完工日期继续生产，
    但会产生延期惩罚。

    返回：
        tardiness:
            tardiness[j] 表示订单 j 的延期天数。

        is_delayed:
            is_delayed[j] 表示订单 j 是否发生延期。

        total_delayed_orders:
            延期订单数量。

        total_weighted_tardiness:
            按订单紧迫度加权后的总延期天数。
    """

    tardiness = {}
    is_delayed = {}
    total_delayed_orders = 0
    total_weighted_tardiness = 0

    if enable_insert_mode:
        for j, order in enumerate(orders):
            tardiness[j] = model.NewIntVar(
                0,
                horizon,
                f"tardiness_order{j}"
            )

            is_delayed[j] = model.NewBoolVar(
                f"is_delayed_order{j}"
            )

            # tardiness[j] >= e[j] - 原始 due
            # 如果实际完工 e[j] 晚于原交期，则产生延期天数。
            model.Add(
                tardiness[j] >= e[j] - original_due[j]
            )

            # 如果 tardiness[j] > 0，则 is_delayed[j] 必须为 1。
            # 这里使用 horizon 作为大 M。
            model.Add(
                tardiness[j] <= horizon * is_delayed[j]
            )

        total_delayed_orders = sum(
            is_delayed[j]
            for j in range(num_orders)
        )

        total_weighted_tardiness = sum(
            int(orders[j].get("urgency_weight", 1)) * tardiness[j]
            for j in range(num_orders)
        )

    return (
        tardiness,
        is_delayed,
        total_delayed_orders,
        total_weighted_tardiness,
    )


def add_insert_plan_change_constraints(
    model,
    orders,
    num_orders,
    horizon,
    x,
    y,
    previous_plan,
    freeze_until_day,
    old_order_names,
    inserted_order_names,
    quantity_increased_order_names,
    enable_insert_mode,
):
    """
    插单模式：冻结旧计划 + 原计划扰动惩罚。

    业务含义：
    1. 插单日期之前的旧计划作为硬约束冻结，不允许改变；
    2. 插单日期之后允许重排；
    3. 对原订单偏离旧计划的部分加入扰动惩罚，尽量减少对原计划的影响；
    4. 对加量订单加入原产线延续惩罚，尽量让原本生产该订单的产线继续生产。

    返回：
        plan_change:
            原计划扰动变量。

        total_plan_change:
            原计划扰动总次数。

        weighted_plan_change_penalty:
            按权重计算后的扰动惩罚项。

        quantity_continue_break:
            加量订单未延续原产线的惩罚变量。

        total_quantity_continue_break:
            加量订单未延续原产线的总次数。

        quantity_continue_lines_by_order:
            加量订单对应的优先延续产线集合。

        freeze_until_day:
            处理后的冻结截止模型日。
    """

    plan_change = {}
    total_plan_change = 0
    weighted_plan_change_penalty = 0

    quantity_continue_break = {}
    total_quantity_continue_break = 0
    quantity_continue_lines_by_order = {}

    if enable_insert_mode and previous_plan is not None:
        order_name_to_idx = {
            order["name"]: j
            for j, order in enumerate(orders)
        }

        old_order_names = set(old_order_names or [])
        inserted_order_names = set(inserted_order_names or [])
        quantity_increased_order_names = set(quantity_increased_order_names or [])

        if freeze_until_day is None:
            freeze_until_day = -1

        freeze_until_day = min(int(freeze_until_day), horizon - 1)

        quantity_continue_lines_by_order = _build_quantity_continue_lines(
            previous_plan=previous_plan,
            quantity_increased_order_names=quantity_increased_order_names,
            freeze_until_day=freeze_until_day,
            horizon=horizon,
        )

        # 检查旧计划中是否存在当前订单列表无法识别的订单名称。
        # 如果旧计划订单名称和输入订单名称不一致，冻结约束可能错误。
        unknown_old_names = set()

        for (i, t), old_name in previous_plan.items():
            if _is_non_order_label(old_name):
                continue

            if 0 <= i < NUM_LINES and 0 <= t < horizon:
                if old_name not in order_name_to_idx:
                    unknown_old_names.add(old_name)

        if unknown_old_names:
            unknown_text = "、".join(sorted(unknown_old_names))
            raise ValueError(
                "旧排产结果中的订单名称无法在当前订单输入中找到："
                f"{unknown_text}。请检查 input_orders.xlsx 和旧排产结果是否对应。"
            )

        # 1）硬冻结：冻结期内每条产线每天必须保持旧计划
        #
        # previous_plan[(i, t)] = old_name
        #
        # 如果旧计划中第 i 条线第 t 天生产 old_name，
        # 则新模型中该位置必须继续生产 old_name。
        # 如果旧计划中为空，则该位置必须保持为空。
        if freeze_until_day >= 0:
            for i in range(NUM_LINES):
                for t in range(0, freeze_until_day + 1):
                    old_name = previous_plan.get((i, t), "")

                    if _is_non_order_label(old_name):
                        old_j = None
                    else:
                        old_j = order_name_to_idx.get(old_name)

                    for j in range(num_orders):
                        model.Add(
                            x[i, j, t] == (1 if old_j == j else 0)
                        )

        # 2）软扰动：冻结期之后允许重排，但尽量少改原订单计划
        #
        # 只对原订单计算扰动，不对插单订单计算扰动。
        # 例如：
        # 原计划 Line1 / 5月12日 / 公版 = 1
        # 新计划不再是公版，则记一次扰动。
        #
        # 原计划 Line1 / 5月12日 / 嘉泰盛 = 0
        # 新计划变成嘉泰盛，也记一次扰动。
        change_start_day = max(0, freeze_until_day + 1)

        weighted_plan_change_terms = []

        for i in range(NUM_LINES):
            for j, order in enumerate(orders):
                order_name = order["name"]

                if order_name not in old_order_names:
                    continue

                for t in range(change_start_day, horizon):
                    old_name = previous_plan.get((i, t), "")
                    old_value = 1 if old_name == order_name else 0

                    change = model.NewBoolVar(
                        f"plan_change_line{i}_order{j}_day{t}"
                    )

                    plan_change[i, j, t] = change

                    if old_value == 1:
                        # 原来这里生产该订单，现在不生产，算一次改动
                        model.Add(change >= 1 - x[i, j, t])
                    else:
                        # 原来这里不生产该订单，现在生产该订单，也算一次改动
                        model.Add(change >= x[i, j, t])

                    if _is_low_penalty_quantity_increase_cell(
                        line_idx=i,
                        old_order_name=old_name,
                        quantity_continue_lines_by_order=quantity_continue_lines_by_order,
                    ):
                        weight = WEIGHT_QUANTITY_INCREASE_CHANGE
                    else:
                        weight = WEIGHT_PLAN_CHANGE

                    weighted_plan_change_terms.append(
                        weight * change
                    )

        if plan_change:
            total_plan_change = sum(plan_change.values())
            weighted_plan_change_penalty = sum(weighted_plan_change_terms)

        # 3）加量订单延续原产线：
        #
        # 如果订单 A 加量，且 Line 1 是 A 的优先延续产线，
        # 那么当 A 在某天生产时，模型倾向让 Line 1 继续生产 A。
        for inc_order_name, line_set in quantity_continue_lines_by_order.items():
            j = order_name_to_idx.get(inc_order_name)

            if j is None:
                continue

            for i in line_set:
                for t in range(change_start_day, horizon):
                    break_var = model.NewBoolVar(
                        f"quantity_continue_break_line{i}_order{j}_day{t}"
                    )

                    quantity_continue_break[i, j, t] = break_var

                    # 如果订单 j 当天生产 y[j,t]=1，
                    # 但优先延续产线 i 没有生产它 x[i,j,t]=0，
                    # 则产生一次“不延续”惩罚。
                    model.Add(
                        break_var >= y[j, t] - x[i, j, t]
                    )

        if quantity_continue_break:
            total_quantity_continue_break = sum(
                quantity_continue_break.values()
            )

    return (
        plan_change,
        total_plan_change,
        weighted_plan_change_penalty,
        quantity_continue_break,
        total_quantity_continue_break,
        quantity_continue_lines_by_order,
        freeze_until_day,
    )