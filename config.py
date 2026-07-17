# =========================
# 基础产线参数
# =========================

NUM_LINES = 18                         # 产线总数
DAILY_CAPACITY = 230000                # 单条产线日产能
MIN_LINES_PER_ACTIVE_ORDER = 3         # 订单当天生产时最少占用产线数


# =========================
# 求解器参数
# =========================

MAX_SOLVE_TIME_SECONDS = 300          # 单次求解时间上限，单位：秒
NUM_SEARCH_WORKERS = 8                 # CP-SAT 并行搜索线程数


# =========================
# 普通排产目标函数权重
# =========================

WEIGHT_CHANGEOVER = 1500               # 换线惩罚
WEIGHT_ACTIVE_DAYS = 10                # 订单生产跨度惩罚
WEIGHT_LINE_STABILITY = 120            # 订单每日占线数波动惩罚
WEIGHT_LOAD_SPREAD = 5                 # 每日总开线数波动惩罚
WEIGHT_OVER_PRODUCTION = 700           # 超产惩罚
WEIGHT_PROD_DAYS = 5                   # 生产日数量惩罚
WEIGHT_ORDER_LINE_POSITION = 1200      # 订单跨日额外产线漂移惩罚
WEIGHT_OUTAGE_RESUME_LINE_POSITION = 2500  # 停电前后恢复原产线额外惩罚


# =========================
# 插单排产目标函数权重
# =========================

WEIGHT_PLAN_CHANGE = 3000                  # 插单后相对旧计划的扰动惩罚
WEIGHT_QUANTITY_INCREASE_CONTINUE = 5000   # 加量订单延续原产线奖励/惩罚权重
WEIGHT_QUANTITY_INCREASE_CHANGE = 500      # 加量订单合理挤占后续计划的低扰动权重
WEIGHT_DELAYED_ORDER_COUNT = 20000         # 延期订单数量惩罚
WEIGHT_WEIGHTED_TARDINESS = 3000           # 紧迫度加权延期天数惩罚
WEIGHT_ORDER_SPLIT = 50000                 # 原订单被拆成多段的惩罚
WEIGHT_LINE_ORDER_SPLIT = 8000             # 同一产线同一订单被打断的惩罚
WEIGHT_IDLE_LINE_INSERT = 20000            # 插单模式下空闲产线惩罚
WEIGHT_INSERT_LINE_STABILITY = 6000        # 插单模式下订单产线位置稳定性惩罚
WEIGHT_INSERT_PROD_DAYS = 1000             # 插单模式下生产日数量惩罚


# =========================
# 自动紧迫度参数
# =========================

URGENCY_WEIGHT_SCALE = 100             # 订单紧迫度整数化缩放系数


# =========================
# 插单排产参数
# =========================

FREEZE_DAYS_AFTER_INSERT = 0           # 插单后额外冻结天数
QUANTITY_INCREASE_LOOKBACK_DAYS = 3    # 加量订单原产线识别回看天数

AUTO_EXTEND_MONTHS_FOR_INSERT = 1      # 插单排产默认自动扩展月份数
MAX_AUTO_EXTEND_MONTHS_FOR_INSERT = 3  # 插单排产最多自动扩展月份数


# =========================
# 停电排产参数
# =========================

ENABLE_SOFT_DUE_FOR_OUTAGE = True      # 停电普通排产是否启用软交期
MAX_AUTO_EXTEND_MONTHS_FOR_OUTAGE = 3  # 停电普通排产最多自动扩展月份数

OVER_PRODUCTION_UNIT = 10000           # 停电模式下超产量缩放单位


# =========================
# 输入输出文件配置
# =========================

OUTPUT_EXCEL_FILE = "CP_SAT_排产结果.xlsx"
INSERT_OUTPUT_EXCEL_FILE = "CP_SAT_插单排产结果.xlsx"
PREVIOUS_PLAN_EXCEL_FILE = OUTPUT_EXCEL_FILE

INPUT_JSON_FILE = "input_orders.json"
INPUT_EXCEL_FILE = "input_orders.xlsx"
INPUT_SHEET_NAME = "订单输入"
INSERT_ORDER_SHEET_NAME = "插单输入"

MONTHLY_SCHEDULE_SHEET_SUFFIX = "月排产图"
ORDER_VIEW_SHEET_NAME = "表1_订单视图"

POWER_OUTAGE_EXCEL_FILE = "停电计划.xlsx"


# =========================
# 停电产能参数
# =========================

PRE_OUTAGE_RATIO_MIN = 0.55            # 停电前一天最低产能比例
PRE_OUTAGE_RATIO_MAX = 0.85            # 停电前一天最高产能比例
RANDOM_SEED = 42                       # 随机种子，保证结果可复现

RECOVERY_RATIOS = [0.40, 0.80, 0.90, 0.95, 1.00]  # 停电恢复期产能比例


# =========================
# 工序机台数匹配参数
# =========================
#
# 业务背景:
# 在原本"订单 × 产线 × 日期"排产之上，再为每个订单每天的占线数
# 进一步分配每个工序的实际机台数 Actual[p]。
#
# 算法思路 (参考 new/机台数匹配zgy改.doc):
# 1. 丝网是产线的最后一道工序, 每条产线占 1 台机台,
#    故 Actual[丝网] = l[j,t] (= line_count);
# 2. 由 l[j,t] 查矩阵 A 得到工序 1..11 的机台数上限 UpperBound[p];
# 3. 丝网实际产能 Capacity[final] = l[j,t] * Cj[丝网];
# 4. 对工序 1..11 取预估机台数 = ceil(Capacity[final] / Cj[p]) * MACHINE_RATIO,
#    与 UpperBound[p] 取小者作为 Actual[p];
# 5. 若 Actual[p] * Cj[p] <= Capacity[final]，则补到刚好超过的最小整数。
#
# 工序与矩阵列的对应关系:
#   工序 1..12 -> 矩阵 A 第 1..12 列 (制绒 ~ 丝网, 一一对应);
#   工序 12 (丝网) 同时也是产线终点, Actual[12] = line_count。

MACHINE_RATIO = 1.0                    # 机台数放大比例 (zgy: 固定为 1, 不再放大)

# 工序名称 (zgy: 移除 SE 工序, 共 11 项, 工序 11 (丝网) 即产线终点)
PROCESS_NAMES = [
    "制绒", "硼扩", "氧化", "碱抛", "Poly镀膜", "退火",
    "RCA", "ALD", "正膜", "背膜", "丝网",
]

# 各工序单台机台日产能 (片/24H), 顺序对应 PROCESS_NAMES
# (zgy: 移除 SE 工序对应的 201817)
#PROCESS_CAPACITIES = [
 #   304465, 197388, 171817, 125106, 309048, 99572, 176586,
  #  309048, 251101, 103485, 116983, 190317,
#]

#PROCESS_CAPACITIES = [
   # 376447, 249740, 141235, 372502, 126219, 205491,
  #  372502, 331776, 134711, 150807, 236712,
#]
   #制绒，硼扩， 氧化，碱抛，POLY，退火，RCA，ALD，正膜，背膜，丝网
PROCESS_CAPACITIES = [
    376448, 249740, 141236, 372503, 126219, 205492,
    372503, 331776, 134712, 150807, 236712,
]

# 工序在矩阵 A 中对应的列下标 (0-indexed)
# (zgy: 跳过 SE 列, 即矩阵 A 第 2 列(0-indexed))
# 矩阵 A 列顺序: 制绒, 硼扩, SE, 氧化, 碱抛, Poly镀膜, 退火, RCA, ALD, 正膜, 背膜, 丝网
#                 0    1   2   3    4    5         6    7    8    9    10   11
#PROCESS_TO_MATRIX_COL = [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11]//zgy

# 矩阵 A: 产线数 (1~18 行) × 12 列机台数上限。
# 列顺序: 制绒, 硼扩, SE, 氧化, 碱抛, Poly镀膜, 退火, RCA, ALD, 正膜, 背膜, 丝网
# (zgy: 矩阵 A 保留 12 列原始业务数据, SE 列通过 PROCESS_TO_MATRIX_COL 在算法中跳过)
#MATRIX_A = [
    # 制绒, 硼扩, SE, 氧化, 碱抛, Poly镀膜, 退火, RCA, ALD, 正膜, 背膜, 丝网
   # [ 2,  2,  2,  3,  2,  3,  2,  1,  1,  2,  2,  1],   #  1 条大线
   # [ 3,  3,  3,  5,  2,  4,  3,  2,  2,  4,  4,  2],   #  2 条大线
   # [ 3,  5,  4,  7,  3,  6,  4,  2,  3,  6,  6,  3],   #  3 条大线
   # [ 5,  6,  5,  8,  4,  8,  5,  3,  4,  8,  7,  4],   #  4 条大线
   # [ 7,  7,  6,  9,  4, 10,  6,  4,  4, 10,  9,  5],   #  5 条大线
   # [ 7,  8,  7, 10,  5, 12,  7,  4,  5, 12, 11,  6],   #  6 条大线
   # [ 8,  9,  8, 12,  5, 14,  8,  5,  6, 14, 12,  7],   #  7 条大线
   # [ 8, 10,  9, 14,  6, 16,  9,  5,  7, 16, 14,  8],   #  8 条大线
   # [ 8, 11, 11, 15,  7, 18, 10,  6,  7, 18, 16,  9],   #  9 条大线
   # [ 9, 12, 12, 17,  7, 20, 11,  7,  8, 20, 17, 10],   # 10 条大线
   # [10, 13, 13, 19,  8, 23, 12,  7,  9, 21, 18, 11],   # 11 条大线
   # [11, 14, 14, 21,  9, 25, 13,  8, 10, 23, 20, 12],   # 12 条大线
   # [11, 15, 15, 23,  9, 27, 15,  9, 10, 25, 23, 13],   # 13 条大线
  #  [11, 16, 16, 25, 10, 29, 16,  9, 11, 27, 24, 14],   # 14 条大线
  #  [12, 17, 17, 26, 11, 31, 17, 10, 12, 29, 26, 15],   # 15 条大线
  #  [12, 18, 19, 28, 12, 33, 19, 11, 13, 32, 28, 16],   # 16 条大线
 #   [12, 19, 20, 30, 12, 35, 20, 12, 14, 34, 30, 17],   # 17 条大线
  #  [12, 19, 22, 31, 12, 37, 21, 12, 15, 36, 32, 18],   # 18 条大线
#]

         #制绒，硼扩， 氧化，碱抛，POLY，退火，RCA，ALD，正膜，背膜，丝网
MATRIX_A = [11,16,27,11,32,19,11,12,31,28,18]

# 工序机台数明细 Sheet 名称
MACHINE_ALLOCATION_SHEET_NAME = "表3_工序机台数明细"

# 按日期机台数汇总 Sheet 名称 (M vs A 对比)
DATE_MACHINE_SUMMARY_SHEET_NAME = "表4_按日期机台数汇总"

