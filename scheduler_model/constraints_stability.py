# =========================
# 文件说明：
# 这个文件负责产线位置稳定性相关软约束。
#
# 主要职责：
# 1. 处理停电模式下的订单产线位置稳定性；
# 2. 处理插单模式下插单订单 / 加量订单的产线位置稳定性；
# 3. 返回目标函数和结果导出需要使用的稳定性变量。
#
# 不负责：
# 1. 不负责创建变量；
# 2. 不负责订单连续性约束；
# 3. 不负责生产阶段约束；
# 4. 不负责目标函数组装。
# =========================

from scheduler_model.model_helpers import (
    add_order_line_position_stability_constraints,
)

from scheduler_model.constraints_insert import (
    _add_insert_line_stability_penalty,
)


def add_position_stability_constraints(
    model,
    orders,
    num_orders,
    horizon,
    x,
    y,
    available_lines,
    inserted_order_names,
    quantity_increased_order_names,
    has_power_outage,
    enable_insert_mode,
):
    """
    添加产线位置稳定性软约束。

    包含两类稳定性约束：

    1. 停电模式下的订单产线位置稳定性：
       同一个订单在相邻非全厂停电日之间，尽量继续使用同一批产线。

    2. 插单模式下的插单订单 / 加量订单产线位置稳定性：
       对插单订单和加量订单，鼓励其在相邻生产日继续使用相同产线组合。

    返回：
        order_line_position_change:
            停电模式下订单产线位置变化变量。

        total_order_line_position_change:
            停电模式下订单产线位置变化总量。

        insert_line_stability_change:
            插单模式下插单订单 / 加量订单产线位置变化变量。

        total_insert_line_stability:
            插单模式下插单订单 / 加量订单产线位置变化总量。
    """

    # =========================
    # 13.1 订单产线位置稳定性软约束
    # =========================
    if has_power_outage:
        (
            order_line_position_change,
            total_order_line_position_change,
        ) = add_order_line_position_stability_constraints(
            model=model,
            num_orders=num_orders,
            horizon=horizon,
            x=x,
            available_lines=available_lines,
        )
    else:
        # 无停电模式下不启用该目标项，保持原始排产逻辑
        order_line_position_change = {}
        total_order_line_position_change = 0

    # =========================
    # 13.1.1 插单模式：插单订单 / 加量订单产线位置稳定性软约束
    # =========================
    insert_line_stability_change = {}
    total_insert_line_stability = 0

    if enable_insert_mode:
        # 插单新单、同名新批次、加量订单都属于重点稳定对象。
        # 这些订单尽量以稳定产线组合连续生产，减少每天更换产线位置。
        insert_stability_target_order_names = (
            set(inserted_order_names)
            | set(quantity_increased_order_names)
        )

        (
            insert_line_stability_change,
            total_insert_line_stability,
        ) = _add_insert_line_stability_penalty(
            model=model,
            orders=orders,
            horizon=horizon,
            x=x,
            y=y,
            target_order_names=insert_stability_target_order_names,
            has_power_outage=has_power_outage,
            available_lines=available_lines,
        )

    return (
        order_line_position_change,
        total_order_line_position_change,
        insert_line_stability_change,
        total_insert_line_stability,
    )