# =========================
# 文件说明:
# 这个文件负责"工序机台数匹配"后处理逻辑。
#
# 主要职责:
# 1. 根据排产结果中的 l[j, t] (订单 j 在第 t 天占用的产线数),
#    读取一维向量 A 得到11道工序各自的机台阈值 UpperBound[p];
# 2. 按文档 new/机台数匹配zgy改.doc 中描述的算法,
#    计算每个工序的实际机台数 Actual[p];
# 3. 把每个 (订单, 日期, 工序) 的机台数整理成 DataFrame,
#    供 Excel 导出使用。
# 4. 汇总表逐工序对比当日总机台M_sum与向量A各工序阈值，输出各工序差值
#
# 不负责:
# 1. 不负责构建 CP-SAT 模型;
# 2. 不负责把机台数作为模型硬约束 (当前实现为后处理);
# 3. 不负责 Excel 写入格式化。
#
# 工序索引说明 (zgy: 已移除 SE 工序, 共 11 个工序):
#   工序 1 ~ 工序 11 一一对应一维向量 MATRIX_A 的下标0~10阈值;
#   工序 11 (丝网)   -> 产线最后一道工序, Actual[11] = 当天产线数,
#                       其单台产能 Cj[丝网] 同时作为下游产能基准。
# =========================
# zgy: 已不再依赖 math.ceil / math.floor (改为浮点运算), 但保留 import 以备扩展
import math
import pandas as pd
#zgy
import sys
import os
# 获取当前文件所在目录的父目录
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
#zgy
from config import (
    MACHINE_RATIO,
    PROCESS_NAMES,
    PROCESS_CAPACITIES,
    MATRIX_A,
   # PROCESS_TO_MATRIX_COL,
)
# 工序总数, 与 PROCESS_NAMES / PROCESS_CAPACITIES 长度一致
# (zgy: 已移除 SE 工序, 从 12 改为 11)
NUM_PROCESSES = 11
# 丝网在 0-indexed 列表中的下标, 是产线终点工序
# (zgy: 移除 SE 后, 丝网仍是最后一个工序)
FINAL_PROCESS_IDX = NUM_PROCESSES - 1

def _safe_line_count(line_count):
    """
    把任意整数 / 浮点值限制到 0 ~ 18 的范围内。
    line_count 来自 solver.Value(l[j, t]), 理论上是 0 ~ NUM_LINES;
    这里只是做一个保护。
    """
    if line_count is None:
        return 0
    line_count = int(line_count)
    if line_count < 0:
        return 0
    if line_count > 18:
        return 18
    return line_count

def compute_actual_machines(line_count, total_lines=None, ratio=None):
    """
    根据 (订单当天产线数, 日内总产线数) 按比例分配每个工序的机台数。
    算法 (zgy: 同时确定所有订单, 按比例切分日内总配额):
    1. total_lines = 当天所有活跃订单产线数之和;
    2. 末位工序 (丝网) 每条线 1 台, Actual[末位] = line_count (整数);
    3. 对其他工序 p:
       - a_total_p = MATRIX_A[p_idx]   (一维向量对应工序p的总阈值)
       - share = a_total_p × line_count / total_lines     (按 line_count 比例切分)
       - 若 share 为整数 → 返回 int (机台数刚好整数, 便于现场确定机台编号)
         否则 → 返回 float (按比例切到小数, 现场协调)
    特性 (与"独立计算"版本对比):
      - 同一天的所有订单 *同时* 确定 (共享一维向量A各工序固定配额);
      - sum(Actual[p] over all orders) = A[p] (无拆单加成);
      - 表4 逐工序差异(M-A)行展示每道工序缺口/富余;
    参数:
        line_count:
            本订单当天占用的产线数, 1 ~ 18 的整数。
            0 表示当天没有生产, 返回全零数组。
        total_lines:
            日内总产线数 (当天所有订单 line_count 之和)。
            None 时退化为 line_count (单订单情形, 向后兼容)。
        ratio:
            (zgy: 已废弃, 按比例算法不需要放大系数, 保留参数仅作向后兼容。)
    返回:
        长度为 NUM_PROCESSES (=11) 的列表:
          - 比例分配后是整数的工序: int
          - 比例分配后是小数的工序: float
        (SE 工序已从配置中移除, 此列表不包含 SE。)
    """
    # zgy: ratio 在按比例算法中没有意义, 仅保留参数签名以向后兼容
    _ = ratio
    line_count = _safe_line_count(line_count)
    if line_count == 0:
        return [0] * NUM_PROCESSES
    # zgy: 默认 total_lines 退化为 line_count, 支持单订单调用
    if total_lines is None:
        total_lines = line_count
    # 保护性裁剪到 [1, 18]
    total_lines = max(1, min(18, int(total_lines)))
    # MATRIX_A 现为一维向量，存储11道工序各自阈值，不再分行
    actual = [0] * NUM_PROCESSES
    # 末位工序 (丝网): 自己的产线数, 整数
    actual[FINAL_PROCESS_IDX] = int(line_count)
    # 其他工序: 按 line_count / total_lines 比例切分向量A对应工序配额
    for p_idx in range(FINAL_PROCESS_IDX):
        a_total_p = MATRIX_A[p_idx]
        share = a_total_p * line_count / total_lines
        # zgy: 整数 share 返回 int (切线好确定); 否则返回 float
        if float(share).is_integer():
            actual[p_idx] = int(share)
        else:
            actual[p_idx] = share
    return actual

def compute_process_capacities(actual_machines):
    """
    根据每个工序的机台数, 计算每个工序的实际产能 (片/天)。
    返回长度为 NUM_PROCESSES (=11) 的浮点数列表, 与 PROCESS_NAMES 顺序一致。
    (zgy: SE 工序已移除)
    """
    return [
        actual_machines[p_idx] * PROCESS_CAPACITIES[p_idx]
        for p_idx in range(NUM_PROCESSES)
    ]

def _get_order_display_name(order):
    """
    与 result_parser.py 中保持一致, 优先使用展示名称。
    """
    return order.get("display_name", order.get("name", ""))

def _build_process_column_names():
    """
    构造工序列名: ['工序1-制绒', '工序2-硼扩', ..., '工序11-丝网']。
    (zgy: SE 工序已移除, 共 11 列)
    """
    return [
        f"工序{p_idx + 1}-{PROCESS_NAMES[p_idx]}"
        for p_idx in range(NUM_PROCESSES)
    ]

def parse_machine_allocation_view(
    solver,
    orders,
    variables,
    model_start_date,
    model_horizon,
    display_dates,
    ratio=None,
):
    """
    根据排产结果, 生成"工序机台数明细"表。
    输出 DataFrame 每行表示一个 (订单, 日期) 组合:
    - 订单 / 日期 / 占用产线数;
    - 工序1-制绒 ~ 工序11-丝网 共 11 列的机台数。
    (zgy: SE 工序已移除; 机台数采用按比例分配, 整数/小数自适应。)
    只输出占用产线数 > 0 的行, 避免输出大量空行。
    参数:
        ratio:
            机台数放大比例 (zgy: 按比例算法不使用, 仅向后兼容)。
    返回:
        pandas.DataFrame
    """
    if ratio is None:
        ratio = MACHINE_RATIO
    l = variables["l"]
    process_columns = _build_process_column_names()
    base_columns = ["订单", "日期", "占用产线数"]
    all_columns = base_columns + process_columns
    # zgy: 第一遍 - 计算每个日期的日内总产线数 (按比例分配需要)
    date_total_lines = {}
    for display_date in display_dates:
        t = (display_date - model_start_date).days
        if t < 0 or t >= model_horizon:
            continue
        total = 0
        for j in range(len(orders)):
            total += solver.Value(l[j, t])
        date_total_lines[t] = total
    rows = []
    # 第二遍: 按 (订单, 日期) 算每个订单的机台数, 共享 total_lines
    for j, order in enumerate(orders):
        display_name = _get_order_display_name(order)
        for display_date in display_dates:
            t = (display_date - model_start_date).days
            if t < 0 or t >= model_horizon:
                continue
            line_count = solver.Value(l[j, t])
            if line_count <= 0:
                continue
            total_lines = date_total_lines.get(t, line_count)
            actual = compute_actual_machines(line_count, total_lines, ratio=ratio)
            row = {
                "订单": display_name,
                "日期": f"{display_date.month}/{display_date.day}",
                "占用产线数": line_count,
            }
            for p_idx, col_name in enumerate(process_columns):
                row[col_name] = actual[p_idx]
            rows.append(row)
    if not rows:
        # 没有任何生产日时, 仍返回带表头的空 DataFrame, 便于上层统一处理
        return pd.DataFrame(columns=all_columns)
    return pd.DataFrame(rows, columns=all_columns)

# =========================
# 按日期机台数汇总视图 (表4)
# =========================
#
# 业务背景:
# 表3 是"按订单"展开 (订单 × 日期), 看不出"当天总机台用量"。
# 老师建议增加"按日期"视图, 让现场切线时一眼看到:
#   1. 当天有哪些订单在生产, 各订单占用多少机台;
#   2. M汇总:当日所有订单各工序机台总和;
#   3. A向量理论:一维向量内11道工序独立阈值;
#   4. 逐工序差异(M-A):每道工序总机台与向量阈值对比，标注缺口/富余;
#   5. 备注汇总所有超标/空余工序。

def _build_a_reference_row(total_lines):
    """
    根据当天总产线数, 读取一维向量 A, 返回11道工序各自理论阈值列表。
    返回长度 NUM_PROCESSES (=11) 的列表; total_lines 不在 [1, 18] 时返回全 None。
    (zgy: MATRIX_A为一维向量，下标0~10一一对应11道工序阈值，不再按产线选行)
    """
    if total_lines < 1 or total_lines > 18:
        return [None] * NUM_PROCESSES
    # 直接取一维向量完整11个工序阈值
    a_vec = MATRIX_A
    return [a_vec[p_idx] for p_idx in range(NUM_PROCESSES)]

def _summarize_diff(m_sum, a_machines):
    """
    逐工序对比当日总机台M_sum与向量A各工序阈值，生成汇总备注:
    - M > A → 机台不够(缺口)
    - M < A → 空余机台
    (zgy: SE 工序已移除; 整数差异不带小数, 浮点差异保留 2 位小数)
    """
    if a_machines[0] is None:
        return ""
    short_p_names = [f"工序{i + 1}" for i in range(NUM_PROCESSES)]
    deficits = []
    surplus = []
    EPS = 1e-9

    def _fmt(diff_value):
        if isinstance(diff_value, int) or float(diff_value).is_integer():
            return f"{int(diff_value):+d}"
        return f"{diff_value:+.2f}"

    for p_idx in range(NUM_PROCESSES):
        diff = m_sum[p_idx] - a_machines[p_idx]
        if diff > EPS:
            deficits.append(f"{short_p_names[p_idx]}{_fmt(diff)}")
        elif diff < -EPS:
            surplus.append(f"{short_p_names[p_idx]}{_fmt(diff)}")
    parts = []
    if deficits:
        parts.append("机台不够: " + ", ".join(deficits))
    if surplus:
        parts.append("空余: " + ", ".join(surplus))
    if not parts:
        return "全部工序与向量A理论阈值一致"
    return "; ".join(parts)

def parse_date_machine_summary_view(
    solver,
    orders,
    variables,
    model_start_date,
    model_horizon,
    display_dates,
    ratio=None,
):
    """
    生成"按日期机台数汇总"表 (表4)。
    每天一个分块, 包含以下行:
      1. 当天每个活跃订单一行 (按一维向量A各工序配额比例切分);
      2. M汇总行:当日各工序全部订单机台累加;
      3. A向量理论行:一维向量存储的11道工序独立阈值;
      4. 差异(M-A)行:逐工序展示总机台与向量阈值差值，备注汇总异常工序;
      5. 空行分隔。
    DataFrame 列结构:
      日期 / 类型/订单 / 占用产线 / 工序1-制绒 ... 工序11-丝网 / 备注
    """
    if ratio is None:
        ratio = MACHINE_RATIO
    l = variables["l"]
    process_columns = _build_process_column_names()
    base_columns = ["日期", "类型/订单", "占用产线"]
    all_columns = base_columns + process_columns + ["备注"]
    rows = []
    for display_date in display_dates:
        t = (display_date - model_start_date).days
        if t < 0 or t >= model_horizon:
            continue
        date_str = f"{display_date.month}/{display_date.day}"
        # 1. 收集当日活跃订单、计算总产线
        active_orders = []
        total_lines = 0
        for j, order in enumerate(orders):
            line_count = solver.Value(l[j, t])
            if line_count <= 0:
                continue
            active_orders.append((order, line_count))
            total_lines += line_count
        if not active_orders:
            continue
        # 2. 计算每个订单机台，并累加得到M汇总
        day_orders = []
        m_sum = [0] * NUM_PROCESSES
        for order, line_count in active_orders:
            actual = compute_actual_machines(line_count, total_lines, ratio=ratio)
            day_orders.append({
                "name": _get_order_display_name(order),
                "lines": line_count,
                "machines": actual,
            })
            for p_idx in range(NUM_PROCESSES):
                m_sum[p_idx] += actual[p_idx]
        # 3. 输出各订单明细行
        for od in day_orders:
            row = {
                "日期": date_str,
                "类型/订单": od["name"],
                "占用产线": od["lines"],
                "备注": "",
            }
            for p_idx, col_name in enumerate(process_columns):
                row[col_name] = od["machines"][p_idx]
            rows.append(row)
        # 4. M汇总行
        row_m = {
            "日期": date_str,
            "类型/订单": "M矩阵汇总",
            "占用产线": total_lines,
            "备注": f"当天共 {len(day_orders)} 个订单开线",
        }
        for p_idx, col_name in enumerate(process_columns):
            row_m[col_name] = m_sum[p_idx]
        rows.append(row_m)
        # 5. A向量理论行（一维向量11个工序阈值）
        a_machines = _build_a_reference_row(total_lines)
        row_a = {
            "日期": date_str,
            "类型/订单": "A向量理论(各工序独立阈值)",
            "占用产线": "",
            "备注": "一维向量MATRIX_A存储11道工序独立机台上限",
        }
        for p_idx, col_name in enumerate(process_columns):
            row_a[col_name] = a_machines[p_idx] if a_machines[p_idx] is not None else ""
        rows.append(row_a)
        # 6. 逐工序差值(M-A)行，保留每道工序差值数值
        row_diff = {
            "日期": date_str,
            "类型/订单": "差异(M-A)",
            "占用产线": "",
            "备注": _summarize_diff(m_sum, a_machines),
        }
        for p_idx, col_name in enumerate(process_columns):
            if a_machines[p_idx] is not None:
                row_diff[col_name] = m_sum[p_idx] - a_machines[p_idx]
            else:
                row_diff[col_name] = ""
        rows.append(row_diff)
        # 7. 空行分隔
        empty_row = {col: "" for col in all_columns}
        rows.append(empty_row)
    # 移除末尾多余空行
    while rows and all(v == "" or v is None for v in rows[-1].values()):
        rows.pop()
    if not rows:
        return pd.DataFrame(columns=all_columns)
    return pd.DataFrame(rows, columns=all_columns)