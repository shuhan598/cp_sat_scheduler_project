import glob
import os
import re
from pathlib import Path

import pandas as pd

from config import (
    NUM_LINES,
    MONTHLY_SCHEDULE_SHEET_SUFFIX,
)


# 兼容旧版导出格式
LEGACY_CALENDAR_SHEET_NAME = "表2_产线日历"


def find_previous_plan_file(preferred_file):
    """
    查找旧排产结果文件。

    优先使用 config.py 中指定的 PREVIOUS_PLAN_EXCEL_FILE，
    默认通常是：
        CP_SAT_排产结果.xlsx

    如果该文件不存在，则在当前目录下查找包含旧排产计划 sheet 的 Excel 文件。

    支持两类旧计划 sheet：
    1. 旧格式：
        表2_产线日历

    2. 新格式：
        5月排产图
        6月排产图
        7月排产图
    """

    if preferred_file and os.path.exists(preferred_file):
        return preferred_file

    candidates = []

    for file_path in glob.glob("*.xlsx"):
        file_name = Path(file_path).name

        # 跳过输入文件
        if file_name.lower() == "input_orders.xlsx":
            continue

        # 跳过 Excel 临时文件
        if file_name.startswith("~$"):
            continue

        try:
            xls = pd.ExcelFile(file_path)
        except Exception:
            continue

        if _find_schedule_sheet_names(xls.sheet_names):
            candidates.append(file_path)

    if not candidates:
        return None

    candidates.sort(
        key=lambda p: os.path.getmtime(p),
        reverse=True
    )

    return candidates[0]


def _is_monthly_schedule_sheet(sheet_name):
    """
    判断 sheet 是否是“月份排产图”。

    例如：
        5月排产图
        6月排产图
        12月排产图

    其中 MONTHLY_SCHEDULE_SHEET_SUFFIX 通常是：
        月排产图
    """

    text = str(sheet_name).strip()

    if not text.endswith(MONTHLY_SCHEDULE_SHEET_SUFFIX):
        return False

    pattern = rf"^\d+{re.escape(MONTHLY_SCHEDULE_SHEET_SUFFIX)}$"

    return re.match(pattern, text) is not None


def _find_schedule_sheet_names(sheet_names):
    """
    从 Excel 的 sheet 列表中找出排产图 sheet。

    优先顺序：
    1. 旧格式：表2_产线日历
    2. 新格式：5月排产图、6月排产图……

    返回：
        schedule_sheet_names: list[str]
    """

    schedule_sheet_names = []

    if LEGACY_CALENDAR_SHEET_NAME in sheet_names:
        schedule_sheet_names.append(LEGACY_CALENDAR_SHEET_NAME)

    monthly_sheets = [
        sheet_name
        for sheet_name in sheet_names
        if _is_monthly_schedule_sheet(sheet_name)
    ]

    monthly_sheets.sort(
        key=lambda name: int(re.search(r"(\d+)", str(name)).group(1))
    )

    for sheet_name in monthly_sheets:
        if sheet_name not in schedule_sheet_names:
            schedule_sheet_names.append(sheet_name)

    return schedule_sheet_names


def _parse_line_index(value):
    """
    解析产线名称。

    支持：
    - Line 1
    - line1
    - 产线1
    - 1号线
    - 1线
    - 1

    返回：
    0-based 产线索引。

    注意：
    这里必须严格识别产线名称，不能只要文本里出现数字就当成产线。
    否则类似“5月排产图-订单日产量明细”会被误判为 Line 5，
    进而把下方明细表误读为旧产线计划，导致冻结计划被污染。
    """

    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    # 统一去掉多余空格，便于识别 “Line 1” / “Line    1”
    text = re.sub(r"\s+", " ", text)

    patterns = [
        r"^Line\s*(\d+)$",
        r"^line\s*(\d+)$",
        r"^LINE\s*(\d+)$",
        r"^产线\s*(\d+)$",
        r"^(\d+)\s*号线$",
        r"^(\d+)\s*线$",
        r"^(\d+)$",
    ]

    line_no = None

    for pattern in patterns:
        match = re.fullmatch(pattern, text)
        if match:
            line_no = int(match.group(1))
            break

    if line_no is None:
        return None

    if line_no < 1 or line_no > NUM_LINES:
        return None

    return line_no - 1


def _normalize_cell_value(value):
    """
    清洗产线日历中的单元格值。

    空值、nan、none 统一返回空字符串。
    """

    if pd.isna(value):
        return ""

    text = str(value).strip()

    if text.lower() in {"nan", "none"}:
        return ""

    return text


def _build_date_column_mapping(df, model_start_date, model_horizon, display_dates):
    """
    建立 Excel 日期列名 -> 模型 day index 的映射。

    当前排产图表头格式一般是：
        5/1, 5/2, 5/3 ...
        6/1, 6/2, 6/3 ...

    模型内部使用：
        0, 1, 2 ...

    注意：
    新版 exporter.py 会按月份拆 sheet，
    但每个 sheet 里的日期列仍然是 5/1、6/1 这种格式。
    """

    date_col_to_day = {}

    df_columns = {str(c).strip(): c for c in df.columns}

    for display_date in display_dates:
        day_idx = (display_date - model_start_date).days

        if not (0 <= day_idx < model_horizon):
            continue

        short_name = f"{display_date.month}/{display_date.day}"

        if short_name in df_columns:
            date_col_to_day[df_columns[short_name]] = day_idx

    return date_col_to_day


def _read_schedule_sheet(
    file_path,
    sheet_name,
    model_start_date,
    model_horizon,
    display_dates,
):
    """
    读取单个排产图 sheet。

    支持：
    - 表2_产线日历
    - 5月排产图
    - 6月排产图

    返回：
        previous_plan_part[(line_idx, day_idx)] = 订单名称
    """

    # exporter.py 中排产图结构是：
    # 第1行：标题
    # 第2行：表头
    # 因此 header=1
    df = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        header=1,
    )

    df.columns = [str(c).strip() for c in df.columns]

    if "产线" not in df.columns:
        raise ValueError(
            f"旧排产结果 {file_path} 的 sheet={sheet_name} 中没有找到 '产线' 列。"
        )

    date_col_to_day = _build_date_column_mapping(
        df=df,
        model_start_date=model_start_date,
        model_horizon=model_horizon,
        display_dates=display_dates,
    )

    if not date_col_to_day:
        return {}

    previous_plan_part = {}

    # 新增保护：
    # 只读取上方产线日历区域的 18 条产线。
    # 读取满 NUM_LINES 条有效产线后立即停止，
    # 避免继续读取下方“订单日产量明细”区域。
    read_line_indices = set()

    for _, row in df.iterrows():
        line_idx = _parse_line_index(row.get("产线"))

        # 下方“订单日产量明细”部分不会有严格合法的产线名，
        # 因此会被自动跳过。
        if line_idx is None:
            continue

        # 如果同一个 sheet 中重复出现同一条产线，
        # 说明已经进入了异常区域或重复区域，直接跳过重复行。
        if line_idx in read_line_indices:
            continue

        for col_name, day_idx in date_col_to_day.items():
            old_order_name = _normalize_cell_value(row[col_name])
            previous_plan_part[(line_idx, day_idx)] = old_order_name

        read_line_indices.add(line_idx)

        if len(read_line_indices) >= NUM_LINES:
            break

    return previous_plan_part


def compute_previous_order_finish_day(previous_plan):
    """
    根据旧计划计算每个订单在旧计划中的实际最后生产日。

    参数：
        previous_plan[(line_idx, day_idx)] = 订单名称

    返回：
        previous_order_finish_day[订单名称] = 最后生产的模型 day index

    示例：
        previous_order_finish_day["嘉泰盛"] = 5

    业务用途：
        判断插单是“加量”还是“同名新批次”。

        如果插单订单 A 在原订单中存在，且：
            previous_order_finish_day["A"] >= insert_day_idx
        则说明旧计划中 A 在插单日期当天或之后仍在生产，
        系统自动判断为“原订单加量”。

        如果：
            previous_order_finish_day["A"] < insert_day_idx
        则说明 A 已经在插单日前完成，
        即使同名，也应判断为“同名新批次”。
    """

    previous_order_finish_day = {}

    for (_, day_idx), order_name in previous_plan.items():
        order_name = _normalize_cell_value(order_name)

        if not order_name:
            continue

        if order_name not in previous_order_finish_day:
            previous_order_finish_day[order_name] = day_idx
        else:
            previous_order_finish_day[order_name] = max(
                previous_order_finish_day[order_name],
                day_idx
            )

    return previous_order_finish_day


def load_previous_plan_from_excel(
    file_path,
    model_start_date,
    model_horizon,
    display_dates,
):
    """
    从旧排产结果中读取旧计划。

    兼容：
    1. 旧格式：
        表2_产线日历

    2. 新格式：
        5月排产图
        6月排产图
        7月排产图

    返回：
        previous_plan[(line_idx, day_idx)] = 订单名称

    示例：
        previous_plan[(0, 0)] = "嘉泰盛"

    表示：
        原计划中，Line 1 在模型第 0 天生产“嘉泰盛”。
    """

    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(
            "没有找到旧排产结果文件，无法启用插单扰动惩罚。"
        )

    xls = pd.ExcelFile(file_path)
    schedule_sheet_names = _find_schedule_sheet_names(xls.sheet_names)

    if not schedule_sheet_names:
        raise ValueError(
            f"旧排产结果 {file_path} 中没有找到排产图 sheet。"
            f" 请确认是否存在 {LEGACY_CALENDAR_SHEET_NAME}，"
            f" 或类似 5{MONTHLY_SCHEDULE_SHEET_SUFFIX} 的 sheet。"
        )

    previous_plan = {}

    for sheet_name in schedule_sheet_names:
        previous_plan_part = _read_schedule_sheet(
            file_path=file_path,
            sheet_name=sheet_name,
            model_start_date=model_start_date,
            model_horizon=model_horizon,
            display_dates=display_dates,
        )

        previous_plan.update(previous_plan_part)

    if not previous_plan:
        raise ValueError(
            f"旧排产结果 {file_path} 中没有读取到有效旧计划。"
            " 请检查日期列格式是否类似 5/1、5/2、6/1。"
        )

    return previous_plan


def load_previous_plan_with_finish_days_from_excel(
    file_path,
    model_start_date,
    model_horizon,
    display_dates,
):
    """
    从旧排产结果中同时读取：

    1. previous_plan：
        previous_plan[(line_idx, day_idx)] = 订单名称

    2. previous_order_finish_day：
        previous_order_finish_day[订单名称] = 旧计划最后生产日 day index

    这是插单模式推荐使用的读取函数。

    main.py 后续建议使用这个函数，而不是只调用 load_previous_plan_from_excel()。
    """

    previous_plan = load_previous_plan_from_excel(
        file_path=file_path,
        model_start_date=model_start_date,
        model_horizon=model_horizon,
        display_dates=display_dates,
    )

    previous_order_finish_day = compute_previous_order_finish_day(
        previous_plan
    )

    return previous_plan, previous_order_finish_day