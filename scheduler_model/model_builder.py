from ortools.sat.python import cp_model

from scheduler_model.model_helpers import (
    normalize_capacity_inputs,
    add_basic_linking_constraints,
    add_one_block_on_order_day_constraints,
    add_active_line_block_constraints,
    add_order_window_constraints,
    add_order_start_end_linking_constraints,
    add_capacity_constraints,
)

from scheduler_model.variables import (
    create_core_variables,
    create_auxiliary_variables,
)

from scheduler_model.constraints_insert import (
    _build_soft_due_orders,
    _add_release_only_window_constraints,
    add_insert_tardiness_constraints,
    add_insert_plan_change_constraints,
)

from scheduler_model.objective_builder import (
    build_objective,
)

from scheduler_model.constraints_production import (
    add_production_stage_constraints,
)

from scheduler_model.constraints_transition import (
    add_changeover_constraints,
    add_line_stability_constraints,
)

from scheduler_model.constraints_continuity import (
    add_continuity_constraints,
)

from scheduler_model.constraints_stability import (
    add_position_stability_constraints,
)


def build_model(
    orders,
    horizon,
    line_capacity=None,
    line_available=None,
    available_lines=None,
    full_outage_days=None,
    has_power_outage=False,

    # =========================
    # 插单模式新增参数
    # =========================
    previous_plan=None,
    freeze_until_day=None,
    old_order_names=None,
    inserted_order_names=None,
    quantity_increased_order_names=None,
    enable_insert_mode=False,

    # =========================
    # 软交期参数
    # =========================
    enable_soft_due=False,
):
    """
    构建 CP-SAT 排产模型。

    无停电模式：
    1. 订单必须在 release ~ due 时间窗口内生产；
    2. 每个订单至少完成需求量，允许适当超产；
    3. 生产阶段从第 1 天开始，连续生产；
    4. 生产阶段内每天必须 18 条线满产；
    5. 所有订单完成后，后续日期允许全部空闲；
    6. 在满足硬约束基础上，尽量少换线、少波动、少超产。

    有停电模式：
    1. 每条产线每天使用 line_capacity[i][t] 作为真实产能；
    2. 停电产线 line_capacity[i][t] = 0，当天不允许生产；
    3. 生产日内所有可用产线必须全部使用；
    4. 订单完成按真实累计产量计算；
    5. 订单允许被全厂停电日打断，但忽略全厂停电日后仍需连续；
    6. 同一产线同一订单允许被该产线停电日打断，但忽略该线停电日后仍最多一个连续段；
    7. 不再要求所有开线产线整体连续，因为停电可能把可用产线切成多段；
    8. 停电模式下额外加入订单产线位置稳定性软约束，尽量减少同一订单跨生产日频繁换线。

    插单模式：
    1. 读取旧排产结果中的“表2_产线日历”作为 previous_plan；
    2. 插单日期之前的旧计划作为硬约束冻结，不允许改变；
    3. 插单日期之后允许重排；
    4. 对原订单偏离旧计划的部分加入扰动惩罚，尽量减少对原计划的影响；
    5. 最晚完工日期改为软交期，超过原交期仍可继续生产，但产生延期惩罚；
    6. 对延期订单数量和紧迫度加权延期天数加入惩罚，尽量减少延期订单和延期天数；
    7. 对加量订单加入原产线延续惩罚，尽量让原本生产该订单的产线继续生产；
    8. 插单模式下允许原订单被打断后续产，但会对额外生产段加入惩罚；
    9. 插单模式下将满线生产、产线稳定、集中生产作为软约束引导，而不是硬约束。

    软交期模式：
    1. enable_soft_due=True 时，订单可以超过原 due 继续生产；
    2. 超过原 due 的完工天数会产生延期惩罚；
    3. 主要用于普通停电排产自动扩展月份时，避免产能不足直接无解。
    """

    # =========================
    # A. 初始化模型与插单集合
    # =========================
    model = cp_model.CpModel()
    num_orders = len(orders)

    old_order_names = set(old_order_names or [])
    inserted_order_names = set(inserted_order_names or [])
    quantity_increased_order_names = set(quantity_increased_order_names or [])

    # 软交期开关：
    # 1. 插单模式默认启用软交期；
    # 2. 普通停电排产可以通过 enable_soft_due=True 启用软交期；
    # 3. 普通无停电排产默认仍使用硬交期。
    use_soft_due = enable_insert_mode or enable_soft_due

    # =========================
    # B. 构造模型订单与原始交期记录
    # =========================

    # 软交期模式下，模型内部使用扩展后的 due。
    # 原始 due 仍保存在 orders 中，用于计算延期天数和导出结果。
    model_orders = _build_soft_due_orders(
        orders=orders,
        horizon=horizon,
        enable_insert_mode=use_soft_due,
    )

    original_due = {
        j: orders[j]["due"]
        for j in range(num_orders)
    }

    # =========================
    # C. 统一处理停电 / 非停电产能输入
    # =========================
    line_capacity, line_available, available_lines, full_outage_days = normalize_capacity_inputs(
        horizon=horizon,
        line_capacity=line_capacity,
        line_available=line_available,
        available_lines=available_lines,
        full_outage_days=full_outage_days,
        has_power_outage=has_power_outage,
    )

    # =========================
    # D. 创建决策变量和辅助变量
    # =========================

    # 核心变量：
    # x[i, j, t] = 1 表示产线 i 在第 t 天生产订单 j
    # y[j, t] = 1 表示订单 j 在第 t 天处于生产状态
    # s[j] 表示订单 j 在允许窗口内由模型选择的开工日
    # e[j] 表示订单 j 在允许窗口内由模型选择的完工日
    # l[j, t] 表示订单 j 在第 t 天占用多少条产线
    # u[i, t] = 1 表示产线 i 在第 t 天处于生产状态
    x, y, s, e, l, u = create_core_variables(
        model=model,
        orders=model_orders,
        horizon=horizon,
    )

    # 辅助变量：
    # w：换线变量
    # diff：订单占线数波动变量
    # block_start / block_end：订单当天连续产线块的开始 / 结束
    # order_on_line_start：同一产线同一订单连续段的开始标记
    # active_block_start / active_block_end：无停电模式下整体开线块的开始 / 结束
    # prod_day：总体生产阶段标记
    # daily_load：每天总开线数
    # load_spread：最大日开线数 - 最小日开线数
    aux = create_auxiliary_variables(
        model=model,
        num_orders=num_orders,
        horizon=horizon,
        line_available=line_available,
        available_lines=available_lines,
        has_power_outage=has_power_outage,
    )

    w = aux["w"]
    diff = aux["diff"]
    block_start = aux["block_start"]
    block_end = aux["block_end"]
    order_on_line_start = aux["order_on_line_start"]
    active_block_start = aux["active_block_start"]
    active_block_end = aux["active_block_end"]
    prod_day = aux["prod_day"]
    daily_load = aux["daily_load"]
    max_load = aux["max_load"]
    min_load = aux["min_load"]
    load_spread = aux["load_spread"]

    # =========================
    # E. 添加基础约束
    # =========================

    # 包含：
    # 1. 产线独占约束；
    # 2. u[i,t] 与 x[i,j,t] 衔接；
    # 3. 停电产线不可生产；
    # 4. l[j,t] 与 x[i,j,t] 衔接；
    # 5. y[j,t] 与 l[j,t] 衔接。
    add_basic_linking_constraints(
        model=model,
        num_orders=num_orders,
        horizon=horizon,
        x=x,
        y=y,
        l=l,
        u=u,
        line_available=line_available,
        has_power_outage=has_power_outage,
    )

    # 同一订单同一天的产线连续块约束
    add_one_block_on_order_day_constraints(
        model=model,
        num_orders=num_orders,
        horizon=horizon,
        x=x,
        y=y,
        block_start=block_start,
        block_end=block_end,
        line_available=line_available,
        has_power_outage=has_power_outage,
    )

    # 同一天所有开线产线整体连续约束。
    # 有停电模式下取消，因为停电可能把可用产线切成多段。
    if not has_power_outage:
        add_active_line_block_constraints(
            model=model,
            horizon=horizon,
            u=u,
            prod_day=prod_day,
            active_block_start=active_block_start,
            active_block_end=active_block_end,
        )

    # =========================
    # F. 添加订单时间窗口约束
    # =========================
    if use_soft_due:
        # 软交期模式：
        # 保留“最早开工前不能生产”，
        # 但不再把最晚完工作为禁止生产的硬边界。
        # 超过原最晚完工后仍可生产，但会在延期约束中产生延期惩罚。
        _add_release_only_window_constraints(
            model=model,
            orders=model_orders,
            horizon=horizon,
            x=x,
            y=y,
            l=l,
        )
    else:
        # 普通硬交期模式：
        # 保留原来的 release ~ due 硬窗口约束。
        add_order_window_constraints(
            model=model,
            orders=model_orders,
            horizon=horizon,
            y=y,
            l=l,
        )

    # =========================
    # G. 添加连续性约束
    # =========================

    # 包含：
    # 1. 订单整体连续生产约束；
    # 2. 产线连续开线约束；
    # 3. 同一产线同一订单最多一个连续生产段；
    # 4. 插单模式下原订单分段续产的软惩罚。
    (
        order_segment_start,
        order_total_segments,
        order_extra_segments,
        total_order_split,
        line_order_segment_start,
        line_order_total_segments,
        line_order_extra_segments,
        total_line_order_split,
    ) = add_continuity_constraints(
        model=model,
        orders=orders,
        num_orders=num_orders,
        horizon=horizon,
        x=x,
        y=y,
        u=u,
        order_on_line_start=order_on_line_start,
        line_available=line_available,
        available_lines=available_lines,
        old_order_names=old_order_names,
        has_power_outage=has_power_outage,
        enable_insert_mode=enable_insert_mode,
    )

    # =========================
    # H. 添加订单起止时间衔接约束
    # =========================
    add_order_start_end_linking_constraints(
        model=model,
        num_orders=num_orders,
        horizon=horizon,
        y=y,
        s=s,
        e=e,
    )

    # =========================
    # I. 添加订单产能约束
    # =========================
    (
        required_line_days,
        over_line_days,
        actual_output,
        over_output,
        over_output_units,
    ) = add_capacity_constraints(
        model=model,
        orders=model_orders,
        horizon=horizon,
        x=x,
        l=l,
        line_capacity=line_capacity,
        has_power_outage=has_power_outage,
    )

    # =========================
    # J. 添加产线位置稳定性软约束
    # =========================

    # 包含：
    # 1. 停电模式下订单产线位置稳定性；
    # 2. 插单模式下插单订单 / 加量订单产线位置稳定性。
    (
        order_line_position_change,
        total_order_line_position_change,
        insert_line_stability_change,
        total_insert_line_stability,
    ) = add_position_stability_constraints(
        model=model,
        orders=orders,
        num_orders=num_orders,
        horizon=horizon,
        x=x,
        y=y,
        l=l,
        available_lines=available_lines,
        line_available=line_available,
        inserted_order_names=inserted_order_names,
        quantity_increased_order_names=quantity_increased_order_names,
        has_power_outage=has_power_outage,
        enable_insert_mode=enable_insert_mode,
    )

    # =========================
    # K. 添加延期与旧计划扰动约束
    # =========================

    # 软交期模式：延期变量。
    # 插单模式和普通停电软交期模式都会使用这里的延期惩罚。
    (
        tardiness,
        is_delayed,
        total_delayed_orders,
        total_weighted_tardiness,
    ) = add_insert_tardiness_constraints(
        model=model,
        orders=orders,
        num_orders=num_orders,
        horizon=horizon,
        e=e,
        original_due=original_due,
        enable_insert_mode=use_soft_due,
    )

    # 插单模式：冻结旧计划 + 原计划扰动惩罚。
    # 普通排产模式下 enable_insert_mode=False，函数内部会返回空变量和 0 惩罚。
    (
        plan_change,
        total_plan_change,
        weighted_plan_change_penalty,
        quantity_continue_break,
        total_quantity_continue_break,
        quantity_continue_lines_by_order,
        freeze_until_day,
    ) = add_insert_plan_change_constraints(
        model=model,
        orders=orders,
        num_orders=num_orders,
        horizon=horizon,
        x=x,
        y=y,
        previous_plan=previous_plan,
        freeze_until_day=freeze_until_day,
        old_order_names=old_order_names,
        inserted_order_names=inserted_order_names,
        quantity_increased_order_names=quantity_increased_order_names,
        enable_insert_mode=enable_insert_mode,
    )

    # =========================
    # L. 添加生产阶段约束
    # =========================
    (
        idle_lines,
        total_idle_lines,
        total_insert_prod_days,
    ) = add_production_stage_constraints(
        model=model,
        num_orders=num_orders,
        horizon=horizon,
        l=l,
        prod_day=prod_day,
        daily_load=daily_load,
        max_load=max_load,
        min_load=min_load,
        load_spread=load_spread,
        available_lines=available_lines,
        has_power_outage=has_power_outage,
        enable_insert_mode=enable_insert_mode,
    )

    # =========================
    # M. 添加跨日衔接约束
    # =========================

    # 换线变量约束
    add_changeover_constraints(
        model=model,
        num_orders=num_orders,
        horizon=horizon,
        x=x,
        w=w,
        line_available=line_available,
        has_power_outage=has_power_outage,
    )

    # 订单占线数稳定性约束
    add_line_stability_constraints(
        model=model,
        num_orders=num_orders,
        horizon=horizon,
        l=l,
        diff=diff,
        available_lines=available_lines,
        has_power_outage=has_power_outage,
    )

    # =========================
    # N. 构建目标函数
    # =========================
    (
        objective_expr,
        total_changeovers,
        total_line_diff,
        total_over_line_days,
        total_over_output,
        total_over_output_units,
    ) = build_objective(
        has_power_outage=has_power_outage,
        num_orders=num_orders,
        horizon=horizon,
        w=w,
        diff=diff,
        e=e,
        s=s,
        prod_day=prod_day,
        load_spread=load_spread,
        over_line_days=over_line_days,
        over_output=over_output,
        over_output_units=over_output_units,
        total_order_line_position_change=total_order_line_position_change,
        weighted_plan_change_penalty=weighted_plan_change_penalty,
        total_quantity_continue_break=total_quantity_continue_break,
        total_delayed_orders=total_delayed_orders,
        total_weighted_tardiness=total_weighted_tardiness,
        total_order_split=total_order_split,
        total_line_order_split=total_line_order_split,
        total_idle_lines=total_idle_lines,
        total_insert_line_stability=total_insert_line_stability,
        total_insert_prod_days=total_insert_prod_days,
    )

    total_active_days = sum(
        y[j, t]
        for j in range(num_orders)
        for t in range(horizon)
    )

    total_order_span = sum(
        e[j] - s[j] + 1
        for j in range(num_orders)
    )

    total_prod_days = sum(
        prod_day[t]
        for t in range(horizon)
    )

    model.Minimize(objective_expr)

    # =========================
    # O. 汇总并返回模型变量
    # =========================
    variables = {
        "x": x,
        "y": y,
        "s": s,
        "e": e,
        "l": l,
        "u": u,
        "w": w,
        "diff": diff,
        "block_start": block_start,
        "block_end": block_end,
        "order_on_line_start": order_on_line_start,
        "active_block_start": active_block_start,
        "active_block_end": active_block_end,
        "prod_day": prod_day,
        "daily_load": daily_load,
        "load_spread": load_spread,
        "required_line_days": required_line_days,
        "over_line_days": over_line_days,
        "actual_output": actual_output,
        "over_output": over_output,
        "over_output_units": over_output_units,
        "line_capacity": line_capacity,
        "line_available": line_available,
        "available_lines": available_lines,
        "full_outage_days": full_outage_days,
        "has_power_outage": has_power_outage,
        "order_line_position_change": order_line_position_change,
        "total_order_line_position_change": total_order_line_position_change,
        "total_changeovers": total_changeovers,
        "total_active_days": total_active_days,
        "total_order_span": total_order_span,
        "total_line_diff": total_line_diff,
        "total_prod_days": total_prod_days,
        "total_over_line_days": total_over_line_days,
        "total_over_output": total_over_output,
        "total_over_output_units": total_over_output_units,

        # 插单 / 软交期模式新增返回项
        "plan_change": plan_change,
        "total_plan_change": total_plan_change,
        "weighted_plan_change_penalty": weighted_plan_change_penalty,
        "enable_insert_mode": enable_insert_mode,
        "enable_soft_due": use_soft_due,
        "freeze_until_day": freeze_until_day,
        "old_order_names": old_order_names,
        "inserted_order_names": inserted_order_names,
        "quantity_increased_order_names": quantity_increased_order_names,

        # 延期相关变量
        "tardiness": tardiness,
        "is_delayed": is_delayed,
        "total_delayed_orders": total_delayed_orders,
        "total_weighted_tardiness": total_weighted_tardiness,
        "original_due": original_due,

        # 插单模式：加量订单延续原产线变量
        "quantity_continue_break": quantity_continue_break,
        "total_quantity_continue_break": total_quantity_continue_break,
        "quantity_continue_lines_by_order": quantity_continue_lines_by_order,

        # 插单模式：原订单分段续产变量
        "order_segment_start": order_segment_start,
        "order_total_segments": order_total_segments,
        "order_extra_segments": order_extra_segments,
        "total_order_split": total_order_split,

        # 插单模式：同一产线同一订单分段续产变量
        "line_order_segment_start": line_order_segment_start,
        "line_order_total_segments": line_order_total_segments,
        "line_order_extra_segments": line_order_extra_segments,
        "total_line_order_split": total_line_order_split,

        # 插单模式：满线利用软约束变量
        "idle_lines": idle_lines,
        "total_idle_lines": total_idle_lines,
        "total_insert_prod_days": total_insert_prod_days,

        # 插单模式：插单订单 / 加量订单产线位置稳定性变量
        "insert_line_stability_change": insert_line_stability_change,
        "total_insert_line_stability": total_insert_line_stability,
    }

    return model, variables