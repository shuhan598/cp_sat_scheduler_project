# =========================
# 文件说明：
# 构建排产模型中的连续性约束。
#
# 主要处理：
# 1. 订单整体是否连续生产；
# 2. 产线是否连续开线；
# 3. 同一产线同一订单是否连续生产；
# 4. 插单模式下，允许原订单被打断，但记录额外分段惩罚。
# =========================

from config import (
    NUM_LINES,
)

from scheduler_model.model_helpers import (
    get_factory_work_days,
    get_line_work_days,
    add_at_most_one_active_segment,
)

from scheduler_model.constraints_insert import (
    _add_segment_count_penalty,
)


def add_continuity_constraints(
    model,
    orders,
    num_orders,
    horizon,
    x,
    y,
    u,
    order_on_line_start,
    line_available,
    available_lines,
    old_order_names,
    has_power_outage,
    enable_insert_mode,
):
    """
    添加订单、产线、产线-订单三类连续性约束。

    普通模式：
        订单、产线、产线-订单都尽量保持一个连续生产段。

    停电模式：
        连续性判断会跳过停电不可用日期。

    插单模式：
        原订单允许被插单打断，但额外生产段会进入目标函数惩罚；
        新插单订单和同名新批次订单仍保持连续生产约束。
    """

    old_order_names = set(old_order_names or [])

    # =========================
    # 1. 订单整体连续性
    # =========================
    if not has_power_outage:
        order_days = list(range(horizon))
    else:
        order_days = get_factory_work_days(
            horizon,
            available_lines,
        )

    order_segment_start = {}
    order_total_segments = {}
    order_extra_segments = {}
    total_order_split = 0

    for j in range(num_orders):
        order_name = orders[j]["name"]

        # 插单模式下，原订单可以分段，但要记录额外分段数量。
        if enable_insert_mode and order_name in old_order_names:
            (
                segment_start,
                total_segments,
                extra_segments,
            ) = _add_segment_count_penalty(
                model=model,
                bool_by_day={
                    t: y[j, t]
                    for t in range(horizon)
                },
                ordered_days=order_days,
                name_prefix=f"order{j}",
                require_at_least_one_segment=True,
            )

            for t, start_var in segment_start.items():
                order_segment_start[j, t] = start_var

            order_total_segments[j] = total_segments
            order_extra_segments[j] = extra_segments

        # 普通订单、新插单订单、同名新批次订单最多只能有一个连续生产段。
        else:
            add_at_most_one_active_segment(
                model=model,
                bool_by_day={
                    t: y[j, t]
                    for t in range(horizon)
                },
                ordered_days=order_days,
                name_prefix=f"order{j}",
            )

        # 每个订单至少要安排一天生产。
        model.Add(
            sum(y[j, t] for t in range(horizon)) >= 1
        )

    if order_extra_segments:
        total_order_split = sum(order_extra_segments.values())

    # =========================
    # 2. 产线连续开线约束
    # =========================
    for i in range(NUM_LINES):
        if not has_power_outage:
            line_days = list(range(horizon))
        else:
            line_days = get_line_work_days(
                horizon,
                line_available,
                i,
            )

        # 普通模式下，每条产线最多一个连续开线段。
        if not enable_insert_mode:
            add_at_most_one_active_segment(
                model=model,
                bool_by_day={
                    t: u[i, t]
                    for t in range(horizon)
                },
                ordered_days=line_days,
                name_prefix=f"line{i}",
            )

        # 插单模式下放宽产线连续开线约束。
        # 产线仍受 u[i,t] 与 x[i,j,t] 的基础衔接约束控制。
        else:
            pass

    # =========================
    # 3. 同一产线同一订单连续性
    # =========================
    line_order_segment_start = {}
    line_order_total_segments = {}
    line_order_extra_segments = {}
    total_line_order_split = 0

    for i in range(NUM_LINES):
        if not has_power_outage:
            line_days = list(range(horizon))
        else:
            line_days = get_line_work_days(
                horizon,
                line_available,
                i,
            )

        for j in range(num_orders):
            order_name = orders[j]["name"]

            # 插单模式下，原订单允许在同一产线上被打断后续产，
            # 但额外分段会进入目标函数惩罚。
            if enable_insert_mode and order_name in old_order_names:
                (
                    segment_start,
                    total_segments,
                    extra_segments,
                ) = _add_segment_count_penalty(
                    model=model,
                    bool_by_day={
                        t: x[i, j, t]
                        for t in range(horizon)
                    },
                    ordered_days=line_days,
                    name_prefix=f"order{j}_on_line{i}",
                    require_at_least_one_segment=False,
                )

                for t, start_var in segment_start.items():
                    line_order_segment_start[i, j, t] = start_var

                line_order_total_segments[i, j] = total_segments
                line_order_extra_segments[i, j] = extra_segments

            # 普通订单、新插单订单、同名新批次订单在同一产线上最多一个连续段。
            else:
                add_at_most_one_active_segment(
                    model=model,
                    bool_by_day={
                        t: x[i, j, t]
                        for t in range(horizon)
                    },
                    ordered_days=line_days,
                    name_prefix=f"order{j}_on_line{i}",
                    external_start_vars={
                        t: order_on_line_start[i, j, t]
                        for t in range(horizon)
                    },
                )

    if line_order_extra_segments:
        total_line_order_split = sum(line_order_extra_segments.values())

    return (
        order_segment_start,
        order_total_segments,
        order_extra_segments,
        total_order_split,
        line_order_segment_start,
        line_order_total_segments,
        line_order_extra_segments,
        total_line_order_split,
    )