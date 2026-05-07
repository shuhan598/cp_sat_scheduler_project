# =========================
# 文件说明：
# 这个文件负责构造排产前的上下文参数。
#
# 主要职责：
# 1. 为读取旧排产结果构造临时时间参数；
# 2. 构造插单模式下的自动跨月扩展尝试序列；
# 3. 计算当前订单输入自然覆盖的月份结束日期；
# 4. 插单读取旧计划时，自动识别旧排产文件中实际存在的月份排产图，
#    避免旧计划已经跨月但读取范围仍停留在订单自然月份的问题。
# =========================

import os
import re
from datetime import date

import pandas as pd

from config import (
    AUTO_EXTEND_MONTHS_FOR_INSERT,
    MAX_AUTO_EXTEND_MONTHS_FOR_INSERT,
    MONTHLY_SCHEDULE_SHEET_SUFFIX,
)

from preprocessing.date_utils import (
    _get_month_first_day,
    _get_month_last_day,
    _build_display_dates_range,
)


def _extract_months_from_previous_plan_file(previous_plan_file):
    """
    从旧排产结果文件中识别实际存在的月份排产图。

    示例：
        5月排产图
        6月排产图
        7月排产图

    返回：
        [5, 6, 7]

    说明：
        这里只识别严格符合“数字 + 月排产图”格式的 sheet。
        例如：
            5月排产图              会识别
            5月排产图-订单日产量明细 不会识别
            表1_订单视图            不会识别
    """

    if not previous_plan_file:
        return []

    if not os.path.exists(previous_plan_file):
        return []

    try:
        xls = pd.ExcelFile(previous_plan_file)
    except Exception:
        return []

    months = []

    pattern = rf"^(\d+){re.escape(MONTHLY_SCHEDULE_SHEET_SUFFIX)}$"

    for sheet_name in xls.sheet_names:
        text = str(sheet_name).strip()

        match = re.match(pattern, text)

        if not match:
            continue

        month = int(match.group(1))

        if 1 <= month <= 12:
            months.append(month)

    return months


def _infer_sheet_month_date(model_start_date, sheet_month):
    """
    根据模型开始日期推断旧排产 sheet 月份对应的年份。

    主要处理跨年情况。

    示例一：
        model_start_date = 2026-05-01
        sheet_month = 6
        返回：2026-06-01

    示例二：
        model_start_date = 2026-12-01
        sheet_month = 1
        返回：2027-01-01
    """

    year = model_start_date.year

    # 如果旧排产 sheet 的月份小于模型起始月份，
    # 说明大概率是跨年后的月份。
    # 例如模型从 2026 年 12 月开始，旧计划中有 1月排产图，
    # 则这个 1 月应理解为 2027 年 1 月。
    if sheet_month < model_start_date.month:
        year += 1

    return date(year, sheet_month, 1)


def _get_previous_plan_latest_sheet_end_date(previous_plan_file, model_start_date):
    """
    根据旧排产结果文件中实际存在的月份排产图，
    计算旧计划实际覆盖到的最后一天。

    示例：
        旧排产文件中存在：
            5月排产图
            6月排产图

        model_start_date = 2026-05-01

        则返回：
            2026-06-30

    用途：
        插单读取旧计划时，不能只按照“原订单 + 插单输入”的最晚交期
        来决定读取范围。

        因为普通排产阶段可能由于停电、产能不足等原因已经自动跨月，
        旧结果文件中可能已经存在 6月排产图、7月排产图。

        如果不把这些月份也读进来，会影响：
            1. 插单识别为“加量 / 同名新批次”的判断；
            2. previous_order_finish_day 的计算；
            3. 插单后的旧计划扰动判断。
    """

    months = _extract_months_from_previous_plan_file(previous_plan_file)

    if not months:
        return None

    month_dates = [
        _infer_sheet_month_date(
            model_start_date=model_start_date,
            sheet_month=month,
        )
        for month in months
    ]

    latest_month_date = max(month_dates)

    return _get_month_last_day(latest_month_date)


def build_previous_plan_time_params(
    base_raw_orders,
    inserted_raw_orders,
    previous_plan_file=None,
):
    """
    为读取旧排产结果构造临时的时间参数。

    注意：
    这一步不是最终排产模型的时间参数，只是为了读取旧计划。

    为什么要单独构造：
    1. 插单自动识别“加量 / 新单 / 同名新批次”需要先读取旧计划；
    2. 旧计划读取需要 model_start_date、model_horizon、display_dates；
    3. 但是最终 orders 需要等识别完插单类型后才能生成。

    原逻辑：
        只根据原订单和插单输入的最晚交期，决定旧计划读取到几月。

    问题：
        如果普通排产阶段因为停电或产能不足已经自动扩展到了下个月，
        例如旧结果文件中已经有“6月排产图”，
        但订单输入本身最晚交期仍在 5 月，
        那么原逻辑只会读取 5 月旧计划，导致 6 月旧计划被忽略。

    新逻辑：
        旧计划读取范围取二者较大值：
            1. 原订单 + 插单输入自然覆盖的月份结束日期；
            2. 旧排产结果文件中实际存在的最后一个月份排产图结束日期。
    """

    raw_orders = list(base_raw_orders) + list(inserted_raw_orders)

    if not raw_orders:
        raise ValueError("没有读取到有效订单，无法构造旧计划读取时间参数。")

    model_start_date = min(o["earliest_start_date"] for o in raw_orders)

    natural_end_date = max(o["latest_finish_date"] for o in raw_orders)

    # 读取旧排产图时，展示范围按整月构造。
    display_start_date = _get_month_first_day(model_start_date)

    # 订单输入自然覆盖到的月份结束日。
    natural_display_end_date = _get_month_last_day(natural_end_date)

    # 旧排产文件中实际存在的最后一个月份排产图结束日。
    previous_plan_sheet_end_date = _get_previous_plan_latest_sheet_end_date(
        previous_plan_file=previous_plan_file,
        model_start_date=model_start_date,
    )

    if previous_plan_sheet_end_date is None:
        display_end_date = natural_display_end_date
    else:
        display_end_date = max(
            natural_display_end_date,
            previous_plan_sheet_end_date,
        )

    display_dates = _build_display_dates_range(
        display_start_date,
        display_end_date,
    )

    model_horizon = (display_end_date - model_start_date).days + 1

    return model_start_date, display_end_date, model_horizon, display_dates


def get_insert_extend_attempts():
    """
    构造插单模式下的自动跨月扩展尝试序列。

    业务逻辑：
    1. 先尝试不扩展月份，即仍然在当前排产月份内完成；
    2. 如果无解，再自动扩展到下一个月份；
    3. 如果仍无解，再继续扩展到后续月份；
    4. 最多扩展到 MAX_AUTO_EXTEND_MONTHS_FOR_INSERT。

    示例：
        AUTO_EXTEND_MONTHS_FOR_INSERT = 1
        MAX_AUTO_EXTEND_MONTHS_FOR_INSERT = 3

    则尝试：
        0个月扩展
        1个月扩展
        2个月扩展
        3个月扩展

    这样可以避免在当前月份本来能排完时，也强行输出 6月排产图。
    """

    attempts = [0]

    start_month = max(1, int(AUTO_EXTEND_MONTHS_FOR_INSERT))
    max_month = max(start_month, int(MAX_AUTO_EXTEND_MONTHS_FOR_INSERT))

    for month_count in range(start_month, max_month + 1):
        if month_count not in attempts:
            attempts.append(month_count)

    return attempts


def get_natural_period_end_date(base_raw_orders, inserted_raw_orders):
    """
    获取当前订单输入自然覆盖的月份结束日期。

    示例：
        如果原订单和插单输入都在 5 月内，
        则返回 2026-05-31。

        如果订单本身已经跨到 6 月，
        则返回 2026-06-30。
    """

    raw_orders = list(base_raw_orders) + list(inserted_raw_orders)

    if not raw_orders:
        raise ValueError("没有有效订单，无法计算自然排产月份结束日期。")

    natural_end_date = max(o["latest_finish_date"] for o in raw_orders)

    return _get_month_last_day(natural_end_date)