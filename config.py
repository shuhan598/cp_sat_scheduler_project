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
WEIGHT_ORDER_LINE_POSITION = 500       # 订单跨日额外产线漂移惩罚


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