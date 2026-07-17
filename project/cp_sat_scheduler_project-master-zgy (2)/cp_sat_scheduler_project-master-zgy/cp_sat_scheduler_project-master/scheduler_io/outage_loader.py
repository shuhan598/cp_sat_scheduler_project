# =========================
# 文件说明：
# 这个文件负责读取 JSON 中的停电计划，并解析停电相关原始数据。
#
# 主要职责：
# 1. 解析“影响产线”字段；
# 2. 解析“停电前一天产能比例”字段；
# 3. 从 input_orders.json 的 power_outages 数组读取停电记录；
# 4. 判断本次是否启用停电增强排产模式。
# =========================

import json
import random

import pandas as pd

from config import (
    INPUT_JSON_FILE,
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
    - [1, 2, 3]

    返回：
        0-based 产线索引列表
    """

    if isinstance(value, list):
        result = set()

        for item in value:
            line_no = int(item)
            if 1 <= line_no <= NUM_LINES:
                result.add(line_no - 1)

        return sorted(result)

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

    可以填写：
    - 0.8
    - 80%
    - 80

    返回：
        0 ~ 1 之间的小数；如果为空，返回 None。
    """

    if value is None or pd.isna(value):
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


def _parse_outage_date(value, field_name, row_idx):
    if value is None or str(value).strip() == "":
        raise ValueError(f"JSON power_outages[{row_idx}] 的 {field_name} 为空。")

    try:
        return pd.to_datetime(value).date()
    except Exception:
        raise ValueError(
            f"JSON power_outages[{row_idx}] 的 {field_name}={value} "
            f"无法识别为日期，请使用 YYYY-MM-DD 格式。"
        )


def load_power_outages_from_json(file_path):
    """
    从 input_orders.json 的 power_outages 数组读取停电计划。

    power_outages 可省略或为空数组。

    每条记录结构：
        {
            "start_date": "2026-05-08",
            "end_date": "2026-05-10",
            "affected_lines": "全部" or "1-3" or [1, 2, 3],
            "pre_outage_ratio": "80%" or 0.8 or 80
        }
    """

    with open(file_path, "r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)

    if not isinstance(payload, dict):
        raise ValueError("JSON 根节点必须是对象。")

    records = payload.get("power_outages", [])

    if not isinstance(records, list):
        raise ValueError("JSON power_outages 必须是数组。")

    power_outages = []

    for row_idx, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"JSON power_outages[{row_idx}] 必须是对象。")

        required_fields = ["start_date", "end_date", "affected_lines"]
        missing_fields = [field for field in required_fields if field not in record]

        if missing_fields:
            raise ValueError(
                f"JSON power_outages[{row_idx}] 缺少必要字段：{missing_fields}。"
            )

        start_date = _parse_outage_date(record["start_date"], "start_date", row_idx)
        end_date = _parse_outage_date(record["end_date"], "end_date", row_idx)

        if start_date > end_date:
            raise ValueError("停电开始日期晚于停电结束日期，请检查输入。")

        affected_lines = parse_line_numbers(record["affected_lines"])

        if not affected_lines:
            continue

        pre_outage_ratio = _parse_pre_outage_ratio(record.get("pre_outage_ratio"))

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


def load_power_outages_from_excel(file_path):
    """
    兼容保留：从单独的停电计划 Excel 文件读取停电计划。

    主流程已改为读取 input_orders.json，不再调用此函数。
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
    - 只读取 input_orders.json 的 power_outages 数组；
    - 不再读取单独的停电计划 Excel 文件；
    - 如果 power_outages 不存在或没有有效记录，则使用原始排产模式。
    """

    print("\n开始读取 JSON 停电计划...")
    print(f"停电计划来源: {INPUT_JSON_FILE} -> power_outages")

    power_outages = load_power_outages_from_json(INPUT_JSON_FILE)
    has_power_outage = len(power_outages) > 0

    if has_power_outage:
        print("\n检测到停电计划，本次启用停电增强排产模式。")
    else:
        print("\n未检测到有效停电记录，本次使用原始排产模式。")

    return power_outages, has_power_outage
