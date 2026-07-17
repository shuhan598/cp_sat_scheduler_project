# =========================
# 文件说明：
# 这个文件负责项目中的日期解析、月份范围计算和跨月扩展。
#
# 主要职责：
# 1. 将 Excel 中的日期解析为 Python date；
# 2. 获取某个日期所在月份的月初、月末；
# 3. 根据起止日期生成展示日期列表；
# 4. 支持插单模式下自动扩展到后续月份。
# =========================

import calendar
from datetime import datetime, date

import pandas as pd


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


def _get_month_first_day(value_date):
    """
    获取某个日期所在月份的第一天。
    """
    return date(value_date.year, value_date.month, 1)


def _get_month_last_day(value_date):
    """
    获取某个日期所在月份的最后一天。
    """
    last_day = calendar.monthrange(value_date.year, value_date.month)[1]
    return date(value_date.year, value_date.month, last_day)


def add_months_to_month_end(value_date, months):
    """
    将日期扩展到后续第 months 个月的月末。

    示例：
    value_date = 2026-05-31
    months = 1 -> 2026-06-30
    months = 2 -> 2026-07-31
    """
    month_index = value_date.month - 1 + months
    year = value_date.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def _build_display_dates_range(display_start_date, display_end_date):
    """
    根据起止日期生成展示日期列表。

    用于后续按月份输出：
    - 5月排产图
    - 6月排产图
    - 7月排产图

    注意：
    display_start_date 通常是模型起始月份的第一天；
    display_end_date 通常是模型结束月份的最后一天。
    """
    return [
        display_start_date + pd.Timedelta(days=i)
        for i in range((display_end_date - display_start_date).days + 1)
    ]


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

    该函数保留用于兼容旧逻辑。
    新的按月份输出逻辑主要使用 _build_display_dates_range。
    """
    month_last_day = calendar.monthrange(display_year, display_month)[1]

    display_start_date = date(display_year, display_month, 1)
    display_end_date = date(display_year, display_month, month_last_day)

    display_dates = [
        display_start_date + pd.Timedelta(days=i)
        for i in range((display_end_date - display_start_date).days + 1)
    ]

    return display_start_date, display_end_date, display_dates