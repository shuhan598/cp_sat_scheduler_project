from datetime import timedelta
from config import START_DATE, HORIZON


def day_to_date(day_index: int) -> str:
    """
    将第几天转换为日期字符串。

    例如：
    START_DATE = 2026-04-01
    day_index = 0 -> 04/01
    day_index = 7 -> 04/08
    """
    return (START_DATE + timedelta(days=day_index)).strftime("%m/%d")


def date_range_labels():
    """返回排产周期内所有日期标签。"""
    return [day_to_date(t) for t in range(HORIZON)]
