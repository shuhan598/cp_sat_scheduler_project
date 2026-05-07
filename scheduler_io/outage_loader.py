# =========================
# 文件说明：
# 这个文件负责读取停电计划 Excel，并解析停电相关原始数据。
#
# 主要职责：
# 1. 解析“影响产线”字段；
# 2. 解析“停电前一天产能比例”字段；
# 3. 从“停电计划.xlsx”中读取停电记录；
# 4. 判断本次是否启用停电增强排产模式。
# =========================

import os
import random
import pandas as pd

from config import (
    NUM_LINES,
    PRE_OUTAGE_RATIO_MIN,
    PRE_OUTAGE_RATIO_MAX,
)

try:
    from config import POWER_OUTAGE_EXCEL_FILE
except ImportError:
    POWER_OUTAGE_EXCEL_FILE = "停电计划.xlsx"


def parse_line_numbers(value):
    """
    解析停电影响产线字段。

    支持格式：
    - 全部
    - 全线
    - 1,2,3
    - 1，2，3
    - 1-5
    - 1~5
    - 1、2、3

    返回：
        0-based 产线索引列表
    """

    if pd.isna(value):
        return []

    text = str(value).strip()

    if not text:
        return []

    if text in {"全部", "全线", "所有", "ALL", "all"}:
        return list(range(NUM_LINES))

    text = (
        text.replace("，", ",")
        .replace("、", ",")
        .replace("；", ",")
        .replace(";", ",")
        .replace("~", "-")
        .replace("—", "-")
    )

    result = set()

    for part in text.split(","):
        part = part.strip()

        if not part:
            continue

        if "-" in part:
            left, right = part.split("-", 1)
            left = int(left.strip())
            right = int(right.strip())

            for line_no in range(left, right + 1):
                if 1 <= line_no <= NUM_LINES:
                    result.add(line_no - 1)
        else:
            line_no = int(part)

            if 1 <= line_no <= NUM_LINES:
                result.add(line_no - 1)

    return sorted(result)


def _parse_pre_outage_ratio(value):
    """
    解析停电前一天产能比例。

    Excel 中可以填写：
    - 0.8
    - 80%
    - 80

    返回：
        0 ~ 1 之间的小数；如果为空，返回 None。
    """

    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    if text.endswith("%"):
        return float(text[:-1]) / 100.0

    ratio = float(text)

    if ratio > 1:
        ratio = ratio / 100.0

    return ratio


def load_power_outages_from_excel(file_path):
    """
    从单独的停电计划 Excel 文件读取停电计划。

    默认文件：
        停电计划.xlsx

    表头建议：
        停电开始日期
        停电结束日期
        影响产线
        停电前一天产能比例

    返回：
        power_outages: list[dict]

    每条记录结构：
        {
            "start_date": date,
            "end_date": date,
            "lines": [0, 1, 2],
            "pre_outage_ratio": 0.8 or None,
        }
    """

    df = pd.read_excel(file_path)

    df.columns = [str(c).strip() for c in df.columns]

    required_columns = [
        "停电开始日期",
        "停电结束日期",
        "影响产线",
    ]

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(
                f"停电计划文件 {file_path} 中缺少必要列：{col}"
            )

    power_outages = []

    for _, row in df.iterrows():
        if pd.isna(row["停电开始日期"]) or pd.isna(row["停电结束日期"]):
            continue

        start_date = pd.to_datetime(row["停电开始日期"]).date()
        end_date = pd.to_datetime(row["停电结束日期"]).date()

        affected_lines = parse_line_numbers(row["影响产线"])

        if not affected_lines:
            continue

        if "停电前一天产能比例" in df.columns:
            pre_outage_ratio = _parse_pre_outage_ratio(
                row["停电前一天产能比例"]
            )
        else:
            pre_outage_ratio = None

        if pre_outage_ratio is None:
            pre_outage_ratio = random.uniform(
                PRE_OUTAGE_RATIO_MIN,
                PRE_OUTAGE_RATIO_MAX,
            )

        power_outages.append({
            "start_date": start_date,
            "end_date": end_date,
            "lines": affected_lines,
            "pre_outage_ratio": pre_outage_ratio,
        })

    return power_outages


def read_power_outage_records():
    """
    读取停电计划。

    业务规则：
    - 只读取单独文件 POWER_OUTAGE_EXCEL_FILE；
    - 不再从订单 Excel 文件中寻找停电计划 sheet；
    - 如果未检测到停电计划文件，则使用原始排产模式。

    返回：
        power_outages:
            停电记录列表。

        has_power_outage:
            是否启用停电增强排产模式。
    """

    # =========================
    # 读取停电计划
    # =========================
    print("\n开始读取停电计划...")

    if os.path.exists(POWER_OUTAGE_EXCEL_FILE):
        print(f"检测到单独停电计划文件: {POWER_OUTAGE_EXCEL_FILE}")

        power_outages = load_power_outages_from_excel(POWER_OUTAGE_EXCEL_FILE)

        has_power_outage = len(power_outages) > 0

        if has_power_outage:
            print("\n检测到停电计划，本次启用停电增强排产模式。")
        else:
            print("\n单独停电计划文件存在，但未读取到有效停电记录。")
            print("本次使用原始排产模式。")
    else:
        print(f"未检测到单独停电计划文件: {POWER_OUTAGE_EXCEL_FILE}")
        print("本次使用原始排产模式。")

        power_outages = []
        has_power_outage = False

    return power_outages, has_power_outage