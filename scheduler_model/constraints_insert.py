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

    # 原有插单扰动权重
    WEIGHT_PLAN_CHANGE,
    WEIGHT_QUANTITY_INCREASE_CHANGE,

    # 新增：插单局部插入与原订单顺延权重
    WEIGHT_INSERT_USE_EMPTY_BEFORE_DUE,
    WEIGHT_INSERT_OCCUPY_OLD_BEFORE_DUE,
    WEIGHT_INSERT_USE_EMPTY_AFTER_DUE,
    WEIGHT_INSERT_OCCUPY_OLD_AFTER_DUE,
    WEIGHT_OCCUPIED_ORDER_URGENCY,
    WEIGHT_ORIGINAL_USE_EMPTY_FOR_MAKEUP,
    WEIGHT_ORIGINAL_MAKEUP_SAME_LINE,
    WEIGHT_ORIGINAL_MAKEUP_DIFF_LINE,
    WEIGHT_ORIGINAL_TO_OTHER_ORIGINAL_CHANGE,
    WEIGHT_ORIGINAL_TO_EMPTY_CHANGE,
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


def _build_old_lines_by_order(
    previous_plan,
    old_order_names,
    horizon,
):
    """
    统计旧计划中每个原订单曾经使用过哪些产线。

    用途：
    插单后，如果原订单被挤占，需要后续补产，
    则优先鼓励它继续使用自己旧计划中用过的产线。
    """

    old_order_names = set(old_order_names or [])

    old_lines_by_order = {
        order_name: set()
        for order_name in old_order_names
    }

    if not previous_plan:
        return old_lines_by_order

    for (line_idx, day_idx), old_name in previous_plan.items():
        if day_idx < 0 or day_idx >= horizon:
            continue

        if _is_non_order_label(old_name):
            continue

        if old_name in old_lines_by_order:
            old_lines_by_order[old_name].add(line_idx)

    return old_lines_by_order


def _is_old_line_for_order(
    order_name,
    line_idx,
    old_lines_by_order,
):
    """
    判断某条产线是否是订单在旧计划中使用过的产线。
    """

    return line_idx in old_lines_by_order.get(order_name, set())


def _is_quantity_increase_preferred_line(
    line_idx,
    order_name,
    quantity_continue_lines_by_order,
):
    """
    判断某条产线是否是加量订单的优先延续产线。

    加量订单在原产线上继续生产，属于合理扰动，
    应该使用较低惩罚。
    """

    return line_idx in quantity_continue_lines_by_order.get(order_name, set())


def _get_order_urgency_weight_by_name(orders):
    """
    获取订单紧迫度权重。

    用途：
    插单挤占原订单时，如果被挤占订单本身很紧急，
    则额外提高挤占惩罚，避免急单挤急单。
    """

    return {
        order["name"]: int(order.get("urgency_weight", 0))
        for order in orders
    }


def _get_original_due(order):
    """
    获取订单原始交期。

    插单模式下，模型内部 due 可能被扩展为 horizon - 1。
    但这里传入的是原始 orders，一般仍然保留原 due。
    为了兼容，优先取 _original_due。
    """

    return int(order.get("_original_due", order["due"]))


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
    插单模式：冻结旧计划 + 分级扰动惩罚。

    新版业务逻辑：
    1. 插单日前旧计划硬冻结；
    2. 插单日后允许重排；
    3. 插单优先在自身交期内使用旧计划空闲位置；
    4. 交期内空闲不足时，允许插单挤占原订单；
    5. 插单挤占原订单时，优先挤占紧迫度低的订单；
    6. 被挤占原订单后续补产时，尽量使用自己旧计划用过的产线；
    7. 原订单之间互相替换、无关订单大面积重排，给予较高惩罚。
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

        # =========================
        # 1. 识别加量订单优先延续产线
        # =========================
        quantity_continue_lines_by_order = _build_quantity_continue_lines(
            previous_plan=previous_plan,
            quantity_increased_order_names=quantity_increased_order_names,
            freeze_until_day=freeze_until_day,
            horizon=horizon,
        )

        # =========================
        # 2. 识别原订单旧计划使用过的产线
        # =========================
        old_lines_by_order = _build_old_lines_by_order(
            previous_plan=previous_plan,
            old_order_names=old_order_names,
            horizon=horizon,
        )

        order_urgency_weight_by_name = _get_order_urgency_weight_by_name(
            orders
        )

        # =========================
        # 3. 检查旧计划中是否存在当前订单列表无法识别的订单名称
        # =========================
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

        # =========================
        # 4. 硬冻结：冻结期内每条产线每天必须保持旧计划
        # =========================
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

        # =========================
        # 5. 软扰动：冻结期之后按业务类型分级惩罚
        # =========================
        #
        # 分类逻辑：
        #
        # A. 旧计划为空：
        #    1）插单在交期内使用空位：低惩罚或 0；
        #    2）插单在交期后使用空位：高惩罚；
        #    3）原订单移动到空位补产：按是否原产线分级惩罚。
        #
        # B. 旧计划中有原订单 old_name：
        #    1）新计划仍为 old_name：不惩罚；
        #    2）新计划变成插单：允许，但按插单交期和 old_name 紧迫度惩罚；
        #    3）新计划变成其他原订单：重罚，避免全局重排；
        #    4）新计划变成空：重罚。
        change_start_day = max(0, freeze_until_day + 1)

        weighted_plan_change_terms = []

        for i in range(NUM_LINES):
            for t in range(change_start_day, horizon):
                old_name = previous_plan.get((i, t), "")
                old_has_order = not _is_non_order_label(old_name)

                assigned_sum = sum(
                    x[i, j, t]
                    for j in range(num_orders)
                )

                if old_has_order:
                    old_j = order_name_to_idx.get(old_name)

                    # 正常情况下 old_j 一定存在，因为前面已经检查过 unknown_old_names。
                    if old_j is None:
                        continue

                    # 5.1 旧计划原订单单元格是否发生变化。
                    #
                    # old_cell_changed = 1 表示：
                    # 旧计划中该位置原本生产 old_name，
                    # 但新计划中不再生产 old_name。
                    old_cell_changed = model.NewBoolVar(
                        f"old_cell_changed_line{i}_oldorder{old_j}_day{t}"
                    )

                    model.Add(
                        old_cell_changed == 1 - x[i, old_j, t]
                    )

                    plan_change[i, old_j, t] = old_cell_changed

                    # 5.2 旧计划原订单变成空白。
                    #
                    # 这说明原计划被打掉了，但没有被插单或其他订单使用，
                    # 一般属于不理想扰动。
                    empty_after_change = model.NewBoolVar(
                        f"old_cell_to_empty_line{i}_day{t}"
                    )

                    model.Add(assigned_sum == 0).OnlyEnforceIf(
                        empty_after_change
                    )
                    model.Add(assigned_sum >= 1).OnlyEnforceIf(
                        empty_after_change.Not()
                    )

                    weighted_plan_change_terms.append(
                        WEIGHT_ORIGINAL_TO_EMPTY_CHANGE * empty_after_change
                    )

                    # 5.3 旧计划原订单被插单订单挤占。
                    #
                    # 插单在自身交期内挤占：可以接受，中等惩罚；
                    # 插单超过交期后挤占：较高惩罚；
                    # 如果被挤占的 old_name 很紧急，再额外加惩罚。
                    occupied_order_urgency = order_urgency_weight_by_name.get(
                        old_name,
                        0,
                    )

                    for j, order in enumerate(orders):
                        new_order_name = order["name"]

                        if new_order_name == old_name:
                            continue

                        if new_order_name in inserted_order_names:
                            original_due = _get_original_due(order)

                            if t <= original_due:
                                base_weight = WEIGHT_INSERT_OCCUPY_OLD_BEFORE_DUE
                            else:
                                base_weight = WEIGHT_INSERT_OCCUPY_OLD_AFTER_DUE

                            weight = (
                                base_weight
                                + WEIGHT_OCCUPIED_ORDER_URGENCY * occupied_order_urgency
                            )

                            weighted_plan_change_terms.append(
                                weight * x[i, j, t]
                            )

                            continue

                        if new_order_name in old_order_names:
                            # 旧计划原订单被其他原订单替换。
                            #
                            # 这通常意味着全局重排，应该重罚。
                            # 但如果新订单是加量订单，且该产线是它的优先延续产线，
                            # 则认为是合理加量扰动，使用低惩罚。
                            if (
                                new_order_name in quantity_increased_order_names
                                and _is_quantity_increase_preferred_line(
                                    line_idx=i,
                                    order_name=new_order_name,
                                    quantity_continue_lines_by_order=quantity_continue_lines_by_order,
                                )
                            ):
                                weight = WEIGHT_QUANTITY_INCREASE_CHANGE
                            else:
                                weight = WEIGHT_ORIGINAL_TO_OTHER_ORIGINAL_CHANGE

                            weighted_plan_change_terms.append(
                                weight * x[i, j, t]
                            )

                            continue

                        # 兜底：理论上不会进入这里。
                        weighted_plan_change_terms.append(
                            WEIGHT_PLAN_CHANGE * x[i, j, t]
                        )

                else:
                    # =========================
                    # 旧计划为空：插单或原订单使用空闲产能
                    # =========================
                    for j, order in enumerate(orders):
                        new_order_name = order["name"]

                        if new_order_name in inserted_order_names:
                            # 插单使用旧计划空闲位置。
                            #
                            # 如果在交期内使用空位，这是最理想的情况；
                            # 如果超过交期后才用空位，则说明插单延期，惩罚较高。
                            original_due = _get_original_due(order)

                            if t <= original_due:
                                weight = WEIGHT_INSERT_USE_EMPTY_BEFORE_DUE
                            else:
                                weight = WEIGHT_INSERT_USE_EMPTY_AFTER_DUE

                            if weight > 0:
                                weighted_plan_change_terms.append(
                                    weight * x[i, j, t]
                                )

                            # 插单使用空位不计入“原计划扰动单元格数”，
                            # 因为没有挤占旧计划原订单。
                            continue

                        if new_order_name in old_order_names:
                            # 原订单移动到旧计划空闲位置补产。
                            #
                            # 如果是加量订单，且使用优先延续产线，低惩罚；
                            # 否则判断是否使用自己旧计划中用过的产线。
                            if (
                                new_order_name in quantity_increased_order_names
                                and _is_quantity_increase_preferred_line(
                                    line_idx=i,
                                    order_name=new_order_name,
                                    quantity_continue_lines_by_order=quantity_continue_lines_by_order,
                                )
                            ):
                                weight = WEIGHT_QUANTITY_INCREASE_CHANGE
                            elif _is_old_line_for_order(
                                order_name=new_order_name,
                                line_idx=i,
                                old_lines_by_order=old_lines_by_order,
                            ):
                                weight = min(
                                    WEIGHT_ORIGINAL_USE_EMPTY_FOR_MAKEUP,
                                    WEIGHT_ORIGINAL_MAKEUP_SAME_LINE,
                                )
                            else:
                                weight = WEIGHT_ORIGINAL_MAKEUP_DIFF_LINE

                            weighted_plan_change_terms.append(
                                weight * x[i, j, t]
                            )

                            # 原订单移动到旧空位，计入扰动统计。
                            plan_change[i, j, t] = x[i, j, t]

        if plan_change:
            total_plan_change = sum(plan_change.values())

        if weighted_plan_change_terms:
            weighted_plan_change_penalty = sum(weighted_plan_change_terms)

        # =========================
        # 6. 加量订单延续原产线
        # =========================
        #
        # 保留你原来的逻辑：
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