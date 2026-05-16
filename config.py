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

WEIGHT_PLAN_CHANGE = 3000                  # 插单后相对旧计划的基础扰动惩罚，作为兜底权重
WEIGHT_QUANTITY_INCREASE_CONTINUE = 5000   # 加量订单延续原产线奖励/惩罚权重
WEIGHT_QUANTITY_INCREASE_CHANGE = 500      # 加量订单合理挤占后续计划的低扰动权重
WEIGHT_DELAYED_ORDER_COUNT = 20000         # 延期订单数量惩罚
WEIGHT_WEIGHTED_TARDINESS = 3000           # 紧迫度加权延期天数惩罚

# 建议适当提高，增强原订单成块和减少后段乱排
WEIGHT_ORDER_SPLIT = 120000                # 原订单被拆成多段的惩罚
WEIGHT_LINE_ORDER_SPLIT = 25000            # 同一产线同一订单被打断的惩罚
WEIGHT_IDLE_LINE_INSERT = 50000            # 插单模式下空闲产线惩罚
WEIGHT_INSERT_LINE_STABILITY = 12000       # 插单模式下订单产线位置稳定性惩罚
WEIGHT_INSERT_PROD_DAYS = 5000             # 插单模式下生产日数量惩罚


# =========================
# 插单局部插入与原订单顺延权重
# =========================
#
# 业务逻辑：
# 1. 插单交期内用旧计划空闲位置，惩罚最低；
# 2. 插单交期内挤占原订单，可以接受；
# 3. 插单超过交期后生产，惩罚较高；
# 4. 插单挤占紧急原订单，额外加惩罚；
# 5. 原订单被挤占后，补产时尽量保持原产线；
# 6. 原订单之间互相替换，说明全局重排严重，惩罚较高。

WEIGHT_INSERT_USE_EMPTY_BEFORE_DUE = 0         # 插单在交期内使用旧计划空闲位置
WEIGHT_INSERT_OCCUPY_OLD_BEFORE_DUE = 3000    # 插单在交期内挤占旧计划原订单
WEIGHT_INSERT_USE_EMPTY_AFTER_DUE = 30000      # 插单超过交期后使用空闲位置
WEIGHT_INSERT_OCCUPY_OLD_AFTER_DUE = 50000     # 插单超过交期后还挤占原订单

WEIGHT_OCCUPIED_ORDER_URGENCY = 20             # 插单挤占原订单时，被挤占订单紧迫度附加惩罚

WEIGHT_ORIGINAL_USE_EMPTY_FOR_MAKEUP = 5000    # 原订单移动到旧计划空闲位置补产
WEIGHT_ORIGINAL_MAKEUP_SAME_LINE = 2000        # 原订单在自己旧产线上补产
WEIGHT_ORIGINAL_MAKEUP_DIFF_LINE = 15000       # 原订单在自己从未使用过的产线上补产

WEIGHT_ORIGINAL_TO_OTHER_ORIGINAL_CHANGE = 30000   # 旧计划中原订单被其他原订单替换
WEIGHT_ORIGINAL_TO_EMPTY_CHANGE = 20000            # 旧计划中原订单被改成空白


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