# =========================
# 文件说明：
# 这个文件负责将原始订单数据转换成模型可用的订单数据。
#
# 主要职责：
# 1. 检查订单名称是否重复；
# 2. 为同名新批次插单生成唯一内部订单名；
# 3. 将真实日期转换成模型 day index；
# 4. 构建普通排产订单；
# 5. 自动判断插单处理方式：新单 / 加量 / 同名新批次；
# 6. 计算订单所需产线天数、剩余窗口天数和自动紧迫度。
# =========================

import math
import pandas as pd
from copy import deepcopy
from datetime import datetime, date

from config import (
    DAILY_CAPACITY,
    URGENCY_WEIGHT_SCALE,
)

from preprocessing.date_utils import (
    _get_month_first_day,
    _get_month_last_day,
    _build_display_dates_range,
)


def _check_duplicate_order_names(raw_orders):
    """
    检查模型内部订单名称是否重复。

    注意：
    同名新批次订单在进入该函数前应该已经生成唯一内部名，
    因此这里检查的是 order["name"]，不是 display_name。
    """

    seen = set()
    duplicates = []

    for order in raw_orders:
        name = order["name"]

        if name in seen:
            duplicates.append(name)

        seen.add(name)

    if duplicates:
        duplicate_text = "、".join(sorted(set(duplicates)))
        raise ValueError(
            f"检测到重复订单名称：{duplicate_text}。"
            f" 请检查订单输入或同名新批次的内部命名逻辑。"
        )


def _make_unique_order_name(base_name, existing_names, insert_date):
    """
    为同名新批次生成唯一内部订单名。

    例如：
    原订单中已有 A；
    插单输入又来了 A，但旧计划中 A 已在插单日前完成；
    则内部命名为：
        A_插单批次_20260510

    如果仍然重复，则自动追加序号。
    """
    date_text = insert_date.strftime("%Y%m%d") if insert_date else "unknown"
    candidate = f"{base_name}_插单批次_{date_text}"

    if candidate not in existing_names:
        existing_names.add(candidate)
        return candidate

    idx = 2
    while True:
        candidate_with_idx = f"{candidate}_{idx}"
        if candidate_with_idx not in existing_names:
            existing_names.add(candidate_with_idx)
            return candidate_with_idx
        idx += 1


def _get_finish_day_idx(finish_value, model_start_date):
    """
    将 previous_order_finish_day 中的值统一转换成模型 day index。

    previous_order_finish_day 可能是：
    - int：模型 day index；
    - date：真实日期。
    """
    if finish_value is None:
        return None

    if isinstance(finish_value, int):
        return finish_value

    if isinstance(finish_value, pd.Timestamp):
        finish_value = finish_value.date()

    if isinstance(finish_value, datetime):
        finish_value = finish_value.date()

    if isinstance(finish_value, date):
        return (finish_value - model_start_date).days

    return None


def build_orders_from_raw_orders(
    raw_orders,
    forced_model_end_date=None,
    global_insert_date=None,
):
    """
    将原始订单日期统一转换成模型 day index。

    参数：
    raw_orders:
        已完成插单处理后的订单列表。
        包括：
        - 原订单；
        - 加量后合并的原订单；
        - 新单；
        - 同名新批次。

    forced_model_end_date:
        用于插单后自动跨月扩展。
        例如原本订单最晚到 5 月 31 日，
        插单后允许排到 6 月，则传入 2026-06-30。

    global_insert_date:
        本次插单重排日期。
        用于计算订单自动紧迫度。

    返回：
    orders: 模型使用的订单列表
    model_start_date: 模型排产起始日期
    model_end_date: 模型排产结束日期
    model_horizon: 模型排产周期长度
    display_dates: 输出表展示用的日期列表
    """

    if not raw_orders:
        raise ValueError("Excel 中没有读取到有效订单。")

    _check_duplicate_order_names(raw_orders)

    # =========================
    # 1. 自动生成模型排产区间
    # =========================
    model_start_date = min(o["earliest_start_date"] for o in raw_orders)
    natural_model_end_date = max(o["latest_finish_date"] for o in raw_orders)

    if forced_model_end_date is not None:
        model_end_date = max(natural_model_end_date, forced_model_end_date)
    else:
        model_end_date = natural_model_end_date

    model_horizon = (model_end_date - model_start_date).days + 1

    if global_insert_date is not None:
        global_insert_day_idx = (global_insert_date - model_start_date).days
    else:
        global_insert_day_idx = None

    # =========================
    # 2. 真实日期 -> 模型 day index
    # =========================
    orders = []

    for o in raw_orders:
        release = (o["earliest_start_date"] - model_start_date).days
        due = (o["latest_finish_date"] - model_start_date).days

        if release < 0:
            raise ValueError(
                f"订单 {o['name']} 的 release 计算结果小于 0，请检查日期逻辑。"
            )

        if due < release:
            raise ValueError(
                f"订单 {o['name']} 的 due 小于 release，请检查日期输入。"
            )

        # =========================
        # 3. 自动计算订单紧迫度
        # =========================
        required_line_days = math.ceil(o["quantity"] / DAILY_CAPACITY)

        if global_insert_day_idx is not None:
            effective_start = max(release, global_insert_day_idx)
        else:
            effective_start = release

        remaining_window_days = max(1, due - effective_start + 1)

        urgency = required_line_days / remaining_window_days
        urgency_weight = max(1, int(math.ceil(urgency * URGENCY_WEIGHT_SCALE)))

        orders.append({
            "name": o["name"],
            "display_name": o.get("display_name", o["name"]),
            "original_name": o.get("original_name", o["name"]),

            "quantity": o["quantity"],
            "original_quantity": o.get("original_quantity", o["quantity"]),
            "increase_quantity": o.get("increase_quantity", 0),

            "release": release,
            "due": due,
            "earliest_start_date": o["earliest_start_date"],
            "latest_finish_date": o["latest_finish_date"],

            "is_inserted": o.get("is_inserted", False),
            "insert_date": o.get("insert_date"),
            "insert_process_type": o.get("insert_process_type", "原订单"),
            "is_quantity_increased": o.get("is_quantity_increased", False),

            "required_line_days": required_line_days,
            "remaining_window_days": remaining_window_days,
            "urgency": round(urgency, 4),
            "urgency_weight": urgency_weight,
        })

    # =========================
    # 4. 生成输出展示日期
    #    新版逻辑：展示从模型起始月份第一天到模型结束月份最后一天。
    #    exporter.py 后续会按月份拆成“5月排产图”“6月排产图”。
    # =========================
    display_start_date = _get_month_first_day(model_start_date)
    display_end_date = _get_month_last_day(model_end_date)

    display_dates = _build_display_dates_range(
        display_start_date,
        display_end_date
    )

    # =========================
    # 5. 打印检查信息
    # =========================
    print("成功读取订单数据：")
    for order in orders:
        print(order)

    print("\n=== 自动识别的时间参数 ===")
    print(f"模型起始日期: {model_start_date}")
    print(f"模型结束日期: {model_end_date}")
    print(f"模型 HORIZON: {model_horizon}")

    print(f"展示起始日期: {display_start_date}")
    print(f"展示结束日期: {display_end_date}")
    print(f"展示天数: {len(display_dates)}")

    return orders, model_start_date, model_end_date, model_horizon, display_dates


def build_orders_for_insert_mode(
    base_raw_orders,
    inserted_raw_orders,
    previous_order_finish_day=None,
    forced_model_end_date=None,
):
    """
    插单模式下，根据旧计划自动判断插单处理方式，并生成模型订单。

    自动判断规则：
    1. 插单订单名不在原订单中：
       -> 全新插单订单

    2. 插单订单名在原订单中，且旧计划中该订单在插单日期当天或之后仍有生产：
       -> 原订单加量
       -> 不新增订单，而是将插单需求量合并到原订单需求量中

    3. 插单订单名在原订单中，但旧计划中该订单已在插单日前完成：
       -> 同名新批次插单
       -> 作为新订单进入模型，生成唯一内部订单名
    """

    if not inserted_raw_orders:
        return build_orders_from_raw_orders(
            raw_orders=base_raw_orders,
            forced_model_end_date=forced_model_end_date,
            global_insert_date=None,
        ) + ({
            "enabled": False,
            "old_order_names": {o["name"] for o in base_raw_orders},
            "inserted_order_names": set(),
            "quantity_increased_order_names": set(),
            "insert_date": None,
            "classification_records": [],
        },)

    previous_order_finish_day = previous_order_finish_day or {}

    all_dates = (
        [o["earliest_start_date"] for o in base_raw_orders]
        + [o["earliest_start_date"] for o in inserted_raw_orders]
    )
    model_start_date_for_compare = min(all_dates)

    insert_dates = [
        o["insert_date"]
        for o in inserted_raw_orders
        if o.get("insert_date") is not None
    ]

    global_insert_date = min(insert_dates)
    global_insert_day_idx = (global_insert_date - model_start_date_for_compare).days

    base_orders = [deepcopy(o) for o in base_raw_orders]
    base_order_map = {o["name"]: o for o in base_orders}

    existing_internal_names = {o["name"] for o in base_orders}

    new_insert_orders = []
    inserted_order_names = set()
    quantity_increased_order_names = set()
    classification_records = []

    for insert_order in inserted_raw_orders:
        insert_name = insert_order["name"]
        insert_quantity = insert_order["quantity"]
        insert_date = insert_order["insert_date"]
        insert_day_idx = (insert_date - model_start_date_for_compare).days

        if insert_name not in base_order_map:
            # =========================
            # 情况一：全新插单订单
            # =========================
            new_order = deepcopy(insert_order)
            new_order["insert_process_type"] = "新单"
            new_order["is_inserted"] = True
            new_order["is_quantity_increased"] = False
            new_order["original_quantity"] = 0
            new_order["increase_quantity"] = insert_quantity

            # 新单名称本身不能与已有内部名称冲突
            if new_order["name"] in existing_internal_names:
                new_order["name"] = _make_unique_order_name(
                    base_name=insert_name,
                    existing_names=existing_internal_names,
                    insert_date=insert_date,
                )
            else:
                existing_internal_names.add(new_order["name"])

            inserted_order_names.add(new_order["name"])
            new_insert_orders.append(new_order)

            classification_records.append({
                "订单": insert_name,
                "处理方式": "新单",
                "插单数量": insert_quantity,
                "说明": "原订单中不存在该订单名，作为全新插单订单。"
            })

            continue

        # 插单订单名存在于原订单中，需要继续判断旧计划中是否已经完成
        old_finish_value = previous_order_finish_day.get(insert_name)
        old_finish_day_idx = _get_finish_day_idx(
            old_finish_value,
            model_start_date_for_compare
        )

        if old_finish_day_idx is not None and old_finish_day_idx >= insert_day_idx:
            # =========================
            # 情况二：原订单加量
            # =========================
            base_order = base_order_map[insert_name]

            if not base_order.get("is_quantity_increased", False):
                base_order["original_quantity"] = base_order["quantity"]
                base_order["increase_quantity"] = 0

            base_order["quantity"] += insert_quantity
            base_order["increase_quantity"] += insert_quantity
            base_order["is_quantity_increased"] = True
            base_order["insert_process_type"] = "加量"
            base_order["is_inserted"] = False

            # 加量后，最终交期取原订单交期和插单交期中较晚的日期。
            # 这样新增量可以继续排产，不会被原订单旧交期过早截断。
            base_order["latest_finish_date"] = max(
                base_order["latest_finish_date"],
                insert_order["latest_finish_date"]
            )

            # 最早开工保持原订单最早开工，确保原订单已排部分仍合法。
            base_order["insert_date"] = insert_date

            quantity_increased_order_names.add(base_order["name"])

            classification_records.append({
                "订单": insert_name,
                "处理方式": "加量",
                "插单数量": insert_quantity,
                "旧计划完工日": old_finish_day_idx,
                "插单日": insert_day_idx,
                "说明": "原订单中存在，且旧计划中插单日后仍在生产，合并为原订单加量。"
            })

        else:
            # =========================
            # 情况三：同名新批次插单
            # =========================
            new_order = deepcopy(insert_order)
            new_internal_name = _make_unique_order_name(
                base_name=insert_name,
                existing_names=existing_internal_names,
                insert_date=insert_date,
            )

            new_order["name"] = new_internal_name
            new_order["display_name"] = f"{insert_name}（插单批次）"
            new_order["original_name"] = insert_name
            new_order["insert_process_type"] = "同名新批次"
            new_order["is_inserted"] = True
            new_order["is_quantity_increased"] = False
            new_order["original_quantity"] = 0
            new_order["increase_quantity"] = insert_quantity

            inserted_order_names.add(new_order["name"])
            new_insert_orders.append(new_order)

            classification_records.append({
                "订单": insert_name,
                "处理方式": "同名新批次",
                "插单数量": insert_quantity,
                "旧计划完工日": old_finish_day_idx,
                "插单日": insert_day_idx,
                "说明": "原订单中存在，但旧计划中该订单已在插单日前完成，作为新批次插单。"
            })

    processed_raw_orders = base_orders + new_insert_orders

    (
        orders,
        model_start_date,
        model_end_date,
        model_horizon,
        display_dates,
    ) = build_orders_from_raw_orders(
        raw_orders=processed_raw_orders,
        forced_model_end_date=forced_model_end_date,
        global_insert_date=global_insert_date,
    )

    old_order_names = {o["name"] for o in base_orders}

    insert_info = {
        "enabled": True,
        "old_order_names": old_order_names,
        "inserted_order_names": inserted_order_names,
        "quantity_increased_order_names": quantity_increased_order_names,
        "insert_date": global_insert_date,
        "classification_records": classification_records,
    }

    print("\n=== 插单自动识别结果 ===")
    for record in classification_records:
        print(record)

    return (
        orders,
        model_start_date,
        model_end_date,
        model_horizon,
        display_dates,
        insert_info,
    )