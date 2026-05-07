# =========================
# 文件说明：
# 这个文件当前主要负责订单输入、插单输入以及订单原始数据读取。
#
# 主要职责：
# 1. 读取“订单输入”sheet；
# 2. 读取“插单输入”sheet；
# 3. 将 Excel 订单数据整理成 raw_orders；
# 4. 保留普通排产和插单排产的兼容入口函数。
# =========================

import pandas as pd

from preprocessing.date_utils import (
    _parse_excel_date,
)

from preprocessing.order_builder import (
    build_orders_from_raw_orders,
    build_orders_for_insert_mode,
)


def _read_raw_orders_from_sheet(
    file_path,
    sheet_name,
    is_inserted=False,
    allow_empty=False,
):
    """
    从指定 sheet 读取订单原始数据。

    普通订单 sheet 必须包含：
    - 订单
    - 需求量
    - 最早开工
    - 最晚完工

    插单订单 sheet 必须包含：
    - 订单
    - 需求量
    - 插单日期
    - 最早开工
    - 最晚完工

    参数：
    is_inserted:
        False 表示普通订单；
        True 表示插单输入中的订单。

    allow_empty:
        True 时，允许 sheet 为空，主要用于“插单输入”sheet。
    """

    df = pd.read_excel(file_path, sheet_name=sheet_name)

    # 插单 sheet 可能只有一个空白 sheet，没有有效表头。
    # 这种情况下直接返回空列表，不启用插单模式。
    if allow_empty and df.empty and len(df.columns) == 0:
        return []

    df.columns = [str(c).strip() for c in df.columns]

    # 如果插单 sheet 是空白 sheet，pandas 可能读出 Unnamed 列。
    if allow_empty:
        all_unnamed_columns = all(
            str(c).startswith("Unnamed")
            for c in df.columns
        )

        if df.empty and all_unnamed_columns:
            return []

    required_columns = ["订单", "需求量", "最早开工", "最晚完工"]

    if is_inserted:
        required_columns = ["订单", "需求量", "插单日期", "最早开工", "最晚完工"]

    missing_columns = [c for c in required_columns if c not in df.columns]

    if missing_columns:
        if allow_empty and df.empty:
            return []

        raise ValueError(
            f"Excel 的 sheet={sheet_name} 缺少必要列：{missing_columns}。"
            f" 请确保表头包含：{required_columns}"
        )

    raw_orders = []

    for row_idx, row in df.iterrows():
        name = str(row["订单"]).strip()

        if not name or name.lower() == "nan":
            continue

        quantity = row["需求量"]

        if pd.isna(quantity):
            raise ValueError(
                f"sheet={sheet_name} 第 {row_idx + 2} 行订单 {name} 的需求量为空。"
            )

        try:
            quantity = int(quantity)
        except Exception:
            raise ValueError(
                f"sheet={sheet_name} 第 {row_idx + 2} 行订单 {name} 的需求量无法转换为整数。"
            )

        earliest_start = _parse_excel_date(
            row["最早开工"],
            "最早开工",
            name
        )

        latest_finish = _parse_excel_date(
            row["最晚完工"],
            "最晚完工",
            name
        )

        if earliest_start > latest_finish:
            raise ValueError(
                f"订单 {name} 的最早开工日期晚于最晚完工日期，请检查输入。"
            )

        insert_date = None

        if is_inserted:
            insert_date = _parse_excel_date(
                row["插单日期"],
                "插单日期",
                name
            )

            if insert_date > latest_finish:
                raise ValueError(
                    f"插单订单 {name} 的插单日期晚于最晚完工日期，请检查输入。"
                )

        raw_orders.append({
            # name 是模型内部使用的订单名。
            # 对同名新批次，后续会生成唯一内部名。
            "name": name,

            # display_name 是展示给用户看的订单名。
            "display_name": name,

            # original_name 保留原始输入订单名。
            "original_name": name,

            "quantity": quantity,
            "original_quantity": quantity,
            "increase_quantity": 0,

            "earliest_start_date": earliest_start,
            "latest_finish_date": latest_finish,

            "is_inserted": is_inserted,
            "insert_date": insert_date,

            # 插单处理方式：
            # 原订单 / 加量 / 新单 / 同名新批次
            "insert_process_type": "插单输入" if is_inserted else "原订单",

            # 是否为原订单加量
            "is_quantity_increased": False,
        })

    return raw_orders


def load_raw_orders_for_insert(
    file_path,
    base_sheet_name="订单输入",
    insert_sheet_name="插单输入",
):
    """
    读取原订单和插单输入，但暂不做“加量 / 新单 / 同名新批次”判断。

    为什么要拆成这个函数：
    - 插单类型判断需要用旧排产计划中的实际完工日；
    - 旧排产计划由 previous_plan_loader.py 读取；
    - 因此 main.py 会先读取 raw_orders，再读取旧计划，
      然后调用 build_orders_for_insert_mode() 完成分类和建模参数生成。
    """

    base_raw_orders = _read_raw_orders_from_sheet(
        file_path=file_path,
        sheet_name=base_sheet_name,
        is_inserted=False,
        allow_empty=False,
    )

    inserted_raw_orders = []

    try:
        xls = pd.ExcelFile(file_path)
        sheet_names = xls.sheet_names
    except Exception:
        sheet_names = []

    if insert_sheet_name in sheet_names:
        inserted_raw_orders = _read_raw_orders_from_sheet(
            file_path=file_path,
            sheet_name=insert_sheet_name,
            is_inserted=True,
            allow_empty=True,
        )

    if inserted_raw_orders:
        print(f"\n检测到插单订单 sheet：{insert_sheet_name}")
        for order in inserted_raw_orders:
            print(order)
    else:
        print("\n未检测到有效插单订单，本次按普通排产运行。")

    insert_dates = [
        o["insert_date"]
        for o in inserted_raw_orders
        if o.get("insert_date") is not None
    ]

    insert_info = {
        "enabled": bool(inserted_raw_orders),
        "insert_date": min(insert_dates) if insert_dates else None,
    }

    return base_raw_orders, inserted_raw_orders, insert_info


def load_orders_from_excel(file_path, sheet_name="订单输入"):
    """
    从 Excel 读取普通订单数据，并自动生成模型需要的时间参数。

    保留这个函数是为了兼容普通排产流程。

    Excel 必须包含列：
    - 订单
    - 需求量
    - 最早开工
    - 最晚完工
    """

    raw_orders = _read_raw_orders_from_sheet(
        file_path=file_path,
        sheet_name=sheet_name,
        is_inserted=False,
        allow_empty=False,
    )

    return build_orders_from_raw_orders(raw_orders)


def load_orders_with_optional_insert(
    file_path,
    base_sheet_name="订单输入",
    insert_sheet_name="插单输入",
):
    """
    兼容旧 main.py 的函数。

    新版完整插单流程建议 main.py 使用：
    1. load_raw_orders_for_insert()
    2. previous_plan_loader.py 读取旧计划和订单旧计划完工日
    3. build_orders_for_insert_mode()

    该函数保留是为了避免旧代码直接报错。
    如果不使用旧计划判断，这里会将插单订单都作为新单处理。
    """

    base_raw_orders, inserted_raw_orders, basic_insert_info = load_raw_orders_for_insert(
        file_path=file_path,
        base_sheet_name=base_sheet_name,
        insert_sheet_name=insert_sheet_name,
    )

    if not basic_insert_info["enabled"]:
        (
            orders,
            model_start_date,
            model_end_date,
            model_horizon,
            display_dates,
        ) = build_orders_from_raw_orders(base_raw_orders)

        insert_info = {
            "enabled": False,
            "old_order_names": {o["name"] for o in base_raw_orders},
            "inserted_order_names": set(),
            "quantity_increased_order_names": set(),
            "insert_date": None,
            "classification_records": [],
        }

        return (
            orders,
            model_start_date,
            model_end_date,
            model_horizon,
            display_dates,
            insert_info,
        )

    return build_orders_for_insert_mode(
        base_raw_orders=base_raw_orders,
        inserted_raw_orders=inserted_raw_orders,
        previous_order_finish_day={},
        forced_model_end_date=None,
    )