# =========================
# 文件说明：
# 这个文件负责产线位置稳定性相关软约束。
#
# 主要职责：
# 1. 所有模式下的通用订单产线号稳定；
# 2. 停电模式下的停电前后恢复原产线加强；
# 3. 插单模式下新插单 / 加量订单的额外稳定性加强。
# =========================

from scheduler_model.model_helpers import (
    add_order_line_position_stability_constraints,
    add_outage_resume_line_position_constraints,
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

    第一层：通用产线号稳定
        所有模式、所有订单都启用。
        用于保证订单生产期间尽量保持产线号稳定。

    第二层：停电前后恢复原产线
        只在停电模式启用。
        用于加强停电前最后生产日和停电后恢复生产日之间的产线恢复。

    第三层：插单订单 / 加量订单额外稳定
        只在插单模式启用。
        对插单新单、同名新批次、加量订单再额外加强稳定。
    """

    # =========================
    # 1. 通用产线号稳定：三种模式都启用
    # =========================
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
        name_prefix="general_extra_drift",
    )

    # =========================
    # 2. 停电前后恢复原产线：仅停电模式启用
    # =========================
    outage_resume_line_position_change = {}
    total_outage_resume_line_position_change = 0

    if has_power_outage:
        (
            outage_resume_line_position_change,
            total_outage_resume_line_position_change,
        ) = add_outage_resume_line_position_constraints(
            model=model,
            num_orders=num_orders,
            horizon=horizon,
            x=x,
            y=y,
            l=l,
            available_lines=available_lines,
            line_available=line_available,
            target_order_indices=None,
            name_prefix="outage_resume_extra_drift",
        )

    # =========================
    # 3. 插单模式：新插单 / 加量订单额外稳定
    # =========================
    insert_line_stability_change = {}
    total_insert_line_stability = 0

    if enable_insert_mode:
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
        outage_resume_line_position_change,
        total_outage_resume_line_position_change,
        insert_line_stability_change,
        total_insert_line_stability,
    )