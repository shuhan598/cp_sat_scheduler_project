import pandas as pd

from config import INPUT_EXCEL_FILE, INPUT_SHEET_NAME
from data_loader import load_orders_from_excel
from model_builder import build_model
from solver_runner import solve_model, is_solution_found, get_status_name
from result_parser import parse_all_results, print_solution_summary
from exporter import export_to_excel

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 300)
pd.set_option("display.max_rows", None)


def main():
    print("开始读取 Excel 订单数据...")

    orders, model_start_date, model_end_date, model_horizon, display_dates = load_orders_from_excel(
        INPUT_EXCEL_FILE,
        INPUT_SHEET_NAME
    )

    print("\n开始构建 CP-SAT 排产模型...")
    print(f"模型起始日期: {model_start_date}")
    print(f"模型结束日期: {model_end_date}")
    print(f"模型 HORIZON: {model_horizon}")
    print(f"展示日期范围: {display_dates[0]} ~ {display_dates[-1]}")

    model, variables = build_model(orders, model_horizon)

    print("模型构建完成，开始求解...")

    solver, status = solve_model(model)

    print("求解状态:", get_status_name(status))

    if not is_solution_found(status):
        print("没有找到可行解。")
        print("可能原因：")
        print("1. 订单需求量太大，交期太紧；")
        print("2. release/due 设置不合理；")
        print("3. 模型排产周期过短；")
        print("4. 连续块约束、产线连续开线约束、同线同订单不回切约束过强；")
        print("5. 生产阶段满产与订单总需求之间存在冲突。")
        return

    print("\n找到可行解！")
    print_solution_summary(solver, variables)

    order_df, calendar_df, detail_df = parse_all_results(
        solver,
        orders,
        variables,
        model_start_date,
        model_horizon,
        display_dates
    )

    output_file = export_to_excel(
        order_df,
        calendar_df,
        detail_df
    )

    print(f"\n两张结果表已全部导出到 Excel：{output_file}")
    print("Sheet 1：表1_订单视图")
    print("Sheet 2：表2_产线日历")


if __name__ == "__main__":
    main()