from datetime import datetime

# =========================
# 全局配置
# =========================

# 产线数量
NUM_LINES = 18

# 单条产线日产能
DAILY_CAPACITY = 230000

# 一个订单只要当天开工，最少要分配几条产线。
MIN_LINES_PER_ACTIVE_ORDER = 3

# 求解时间上限，单位：秒
MAX_SOLVE_TIME_SECONDS = 300

# 求解线程数
NUM_SEARCH_WORKERS = 8

# 目标函数权重
WEIGHT_CHANGEOVER = 1500
WEIGHT_ACTIVE_DAYS = 10
WEIGHT_LINE_STABILITY = 120
WEIGHT_LOAD_SPREAD = 5
WEIGHT_OVER_PRODUCTION = 700

# 输出文件名
OUTPUT_EXCEL_FILE = "CP_SAT_排产结果.xlsx"

# 输入订单 Excel 文件
INPUT_EXCEL_FILE = "input_orders.xlsx"

# 输入订单所在 sheet 名称
INPUT_SHEET_NAME = "订单输入"
