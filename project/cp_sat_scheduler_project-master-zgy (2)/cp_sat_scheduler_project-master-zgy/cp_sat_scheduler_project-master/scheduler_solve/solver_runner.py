from ortools.sat.python import cp_model

from config import MAX_SOLVE_TIME_SECONDS, NUM_SEARCH_WORKERS


def solve_model(model):
    """
    配置并运行 CP-SAT 求解器。
    """

    solver = cp_model.CpSolver()

    solver.parameters.max_time_in_seconds = MAX_SOLVE_TIME_SECONDS
    solver.parameters.num_search_workers = NUM_SEARCH_WORKERS

    status = solver.Solve(model)

    return solver, status


def is_solution_found(status):
    """
    判断是否找到可行解或最优解。
    """

    return status in [cp_model.OPTIMAL, cp_model.FEASIBLE]


def get_status_name(status):
    """
    将求解状态转换为可读文本。
    """

    if status == cp_model.OPTIMAL:
        return "OPTIMAL，已找到最优解"
    if status == cp_model.FEASIBLE:
        return "FEASIBLE，已找到可行解"
    if status == cp_model.INFEASIBLE:
        return "INFEASIBLE，模型无可行解"
    if status == cp_model.MODEL_INVALID:
        return "MODEL_INVALID，模型无效"
    if status == cp_model.UNKNOWN:
        return "UNKNOWN，未在限定时间内找到可行解"
    return f"未知状态：{status}"
