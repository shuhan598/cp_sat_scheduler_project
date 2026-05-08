# =========================
# 文件说明：
# 这个文件负责产线位置稳定性相关软约束。
#
# 主要职责：
# 1. 普通排产：减少订单跨日额外产线漂移；
# 2. 停电排产：跳过全厂停电日，尽量恢复停电前产线组合；
# 3. 插单排产：优先约束新插单订单 / 加量订单的产线漂移。
# =========================

from scheduler_model.model_helpers import (
    add_order_line_position_stability_constraints,
)


def add_position_stability_constraints(
    model,
    orders,
    num_orders,
    horizon,
    x,
    y,
    l,
    available_lines,
    line_available,
    inserted_order_names,
    quantity_increased_order_names,
    has_power_outage,
    enable_insert_mode,
):
    """
    添加产线位置稳定性软约束。

    普通排产：
        所有订单启用额外漂移惩罚。

    停电排产：
        所有订单启用额外漂移惩罚；
        比较时跳过全厂停电日；
        单条产线停电时，不强制比较不可用产线。

    插单排产：
        新插单订单、同名新批次订单、加量订单启用额外漂移惩罚；
        原订单主要依靠旧计划扰动惩罚控制，不在这里额外强压。
    """

    order_line_position_change = {}
    total_order_line_position_change = 0

    insert_line_stability_change = {}
    total_insert_line_stability = 0

    # 普通排产 / 普通停电排产：所有订单启用
    if not enable_insert_mode:
        (
            order_line_position_change,
            total_order_line_position_change,
        ) = add_order_line_position_stability_constraints(
            model=model,
            num_orders=num_orders,
            horizon=horizon,
            x=x,
            y=y,
            l=l,
            available_lines=available_lines,
            line_available=line_available,
            target_order_indices=None,
            name_prefix="normal_extra_drift",
        )

    # 插单排产：先只对新插单订单 / 加量订单启用
    else:
        target_order_names = (
            set(inserted_order_names or [])
            | set(quantity_increased_order_names or [])
        )

        target_order_indices = [
            j for j, order in enumerate(orders)
            if order["name"] in target_order_names
        ]

        if target_order_indices:
            (
                insert_line_stability_change,
                total_insert_line_stability,
            ) = add_order_line_position_stability_constraints(
                model=model,
                num_orders=num_orders,
                horizon=horizon,
                x=x,
                y=y,
                l=l,
                available_lines=available_lines,
                line_available=line_available,
                target_order_indices=target_order_indices,
                name_prefix="insert_extra_drift",
            )

    return (
        order_line_position_change,
        total_order_line_position_change,
        insert_line_stability_change,
        total_insert_line_stability,
    )