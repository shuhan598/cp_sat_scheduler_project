import pandas as pd
import calendar
from datetime import datetime, date


def _parse_excel_date(value, field_name, order_name):
    """
    将 Excel 中的日期解析成 Python 的 date 类型。
    这里只支持真实日期，不再建议直接输入 day index。
    """

    if pd.isna(value):
        raise ValueError(f"订单 {order_name} 的 {field_name} 为空，请检查 Excel 输入。")

    if isinstance(value, pd.Timestamp):
        return value.date()

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    try:
        return pd.to_datetime(value).date()
    except Exception:
        raise ValueError(
            f"订单 {order_name} 的 {field_name}={value} 无法识别为日期，请检查 Excel 输入格式。"
        )


def _get_display_month_from_orders(raw_orders):
    """
    根据订单真实日期自动识别展示月份。
    当前逻辑：
    - 默认使用最早开工日期所在的年月
    """
    earliest_start = min(o["earliest_start_date"] for o in raw_orders)
    return earliest_start.year, earliest_start.month


def _build_display_dates(display_year, display_month):
    """
    根据展示年月生成整月日期列表。
    例如：
    2026年5月 -> 2026/05/01 ~ 2026/05/31
    """
    month_last_day = calendar.monthrange(display_year, display_month)[1]

    display_start_date = date(display_year, display_month, 1)
    display_end_date = date(display_year, display_month, month_last_day)

    display_dates = [
        display_start_date + pd.Timedelta(days=i)
        for i in range((display_end_date - display_start_date).days + 1)
    ]

    return display_start_date, display_end_date, display_dates


def load_orders_from_excel(file_path, sheet_name="订单输入"):
    """
    从 Excel 读取订单数据，并自动生成模型需要的时间参数。

    Excel 必须包含列：
    - 订单
    - 需求量
    - 最早开工
    - 最晚完工

    返回：
    orders: 模型使用的订单列表
    model_start_date: 模型排产起始日期
    model_end_date: 模型排产结束日期
    model_horizon: 模型排产周期长度
    display_dates: 输出表展示用的整月日期列表
    """

    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df.columns = [str(c).strip() for c in df.columns]

    required_columns = ["订单", "需求量", "最早开工", "最晚完工"]
    missing_columns = [c for c in required_columns if c not in df.columns]

    if missing_columns:
        raise ValueError(
            f"Excel 缺少必要列：{missing_columns}。"
            f" 请确保表头包含：{required_columns}"
        )

    raw_orders = []

    for row_idx, row in df.iterrows():
        name = str(row["订单"]).strip()

        if not name or name.lower() == "nan":
            continue

        quantity = row["需求量"]
        if pd.isna(quantity):
            raise ValueError(f"第 {row_idx + 2} 行订单 {name} 的需求量为空。")

        try:
            quantity = int(quantity)
        except Exception:
            raise ValueError(f"第 {row_idx + 2} 行订单 {name} 的需求量无法转换为整数。")

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

        raw_orders.append({
            "name": name,
            "quantity": quantity,
            "earliest_start_date": earliest_start,
            "latest_finish_date": latest_finish,
        })

    if not raw_orders:
        raise ValueError("Excel 中没有读取到有效订单。")

    # =========================
    # 1. 自动生成模型排产区间
    # =========================
    model_start_date = min(o["earliest_start_date"] for o in raw_orders)
    model_end_date = max(o["latest_finish_date"] for o in raw_orders)
    model_horizon = (model_end_date - model_start_date).days + 1

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

        orders.append({
            "name": o["name"],
            "quantity": o["quantity"],
            "release": release,
            "due": due,
            "earliest_start_date": o["earliest_start_date"],
            "latest_finish_date": o["latest_finish_date"],
        })

    # =========================
    # 3. 自动生成输出展示整月日期
    # =========================
    display_year, display_month = _get_display_month_from_orders(raw_orders)

    display_start_date, display_end_date, display_dates = _build_display_dates(
        display_year,
        display_month
    )

    # =========================
    # 4. 打印检查信息
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