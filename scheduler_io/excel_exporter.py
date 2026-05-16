from config import (
    NUM_LINES,
    OUTPUT_EXCEL_FILE,
    INSERT_OUTPUT_EXCEL_FILE,
    MONTHLY_SCHEDULE_SHEET_SUFFIX,
    ORDER_VIEW_SHEET_NAME,
)


def export_to_excel(order_df, calendar_df, detail_df, output_file=None):
    """
    普通排产导出。

    原逻辑：
    Sheet1：表1_订单视图
    Sheet2：表2_产线日历

    新逻辑：
    Sheet1：表1_订单视图
    Sheet2及以后：按月份自动生成排产图

    示例：
    如果订单输入是 5 月：
        Sheet1：表1_订单视图
        Sheet2：5月排产图

    如果排产周期跨到 6 月：
        Sheet1：表1_订单视图
        Sheet2：5月排产图
        Sheet3：6月排产图
    """
    if output_file is None:
        output_file = OUTPUT_EXCEL_FILE

    return export_monthly_schedule_to_excel(
        order_df=order_df,
        calendar_df=calendar_df,
        detail_df=detail_df,
        output_file=output_file,
    )


def export_insert_to_excel(
    order_df,
    new_calendar_df,
    new_detail_df,
    previous_plan_file=None,
    output_file=None,
):
    """
    插单模式导出。
    新逻辑：
    Sheet1：表1_订单视图
        插单后的订单视图，包含：
        - 原订单；
        - 加量订单；
        - 新插单订单；
        - 同名新批次订单；
        - 是否延期、延期天数、自动紧迫度等字段。

    Sheet2及以后：按月份自动生成插单后的新排产图
        例如：
        - 5月排产图
        - 6月排产图
        - 7月排产图

    说明：
    previous_plan_file 参数保留，是为了兼容 main.py 中原来的调用方式。
    新版导出不再把旧计划复制到插单结果文件中，
    而是直接按月份输出插单后的完整新计划。
    """
    if output_file is None:
        output_file = INSERT_OUTPUT_EXCEL_FILE

    order_color_mapping = _load_order_color_mapping_from_previous_plan(
        previous_plan_file
    )

    return export_monthly_schedule_to_excel(
        order_df=order_df,
        calendar_df=new_calendar_df,
        detail_df=new_detail_df,
        output_file=output_file,
        order_color_mapping=order_color_mapping,
    )


def export_monthly_schedule_to_excel(
    order_df,
    calendar_df,
    detail_df,
    output_file,
    order_color_mapping=None,
):
    """
    按月份导出排产结果。

    Sheet1：
        表1_订单视图

    Sheet2及以后：
        根据 calendar_df / detail_df 中的日期列自动拆分月份。

    示例：
        calendar_df 列为：
            产线, 5/1, 5/2, ..., 5/31

        则输出：
            5月排产图

        calendar_df 列为：
            产线, 5/1, ..., 5/31, 6/1, ..., 6/30

        则输出：
            5月排产图
            6月排产图

    每个月 sheet 内部仍保持原来的结构：
        上方：产线日历
        下方：订单日产量明细
    """
    month_sheets = _split_calendar_and_detail_by_month(
        calendar_df=calendar_df,
        detail_df=detail_df,
    )

    with __import__("pandas").ExcelWriter(output_file, engine="openpyxl") as writer:
        order_df.to_excel(
            writer,
            sheet_name=ORDER_VIEW_SHEET_NAME,
            index=False,
            startrow=1
        )

        workbook = writer.book

        ws1 = workbook[ORDER_VIEW_SHEET_NAME]
        _format_order_sheet(ws1)

        for item in month_sheets:
            sheet_name = item["sheet_name"]
            calendar_month_df = item["calendar_df"]
            detail_month_df = item["detail_df"]

            calendar_startrow = 1
            detail_gap_rows = 2

            calendar_header_excel_row = calendar_startrow + 1
            calendar_last_data_excel_row = calendar_header_excel_row + len(calendar_month_df)

            detail_title_excel_row = calendar_last_data_excel_row + detail_gap_rows
            detail_startrow = detail_title_excel_row

            calendar_month_df.to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
                startrow=calendar_startrow
            )

            detail_month_df.to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
                startrow=detail_startrow
            )

            ws = workbook[sheet_name]

            _format_calendar_and_detail_sheet(
                ws,
                calendar_df=calendar_month_df,
                detail_df=detail_month_df,
                detail_title_excel_row=detail_title_excel_row,
                title_text=sheet_name,
                detail_title_text=f"{sheet_name}-订单日产量明细",
                order_color_mapping=order_color_mapping,
            )

    return output_file


def _is_date_column(column_name):
    """
    判断某一列是否是日期列。

    当前 result_parser.py 生成的日期列格式为：
        5/1
        5/2
        6/1
        12/31

    因此这里用简单规则判断：
        月/日
    """
    import re

    text = str(column_name).strip()

    return re.match(r"^\d{1,2}/\d{1,2}$", text) is not None


def _get_month_from_date_column(column_name):
    """
    从日期列名中提取月份。

    示例：
        5/1 -> 5
        6/30 -> 6
    """
    text = str(column_name).strip()
    month_text = text.split("/", 1)[0]
    return int(month_text)


def _is_empty_cell_value(value):
    """
    判断单元格值是否为空。

    兼容：
    - None
    - 空字符串
    - pandas NaN
    """

    if value is None:
        return True

    try:
        import pandas as pd
        if pd.isna(value):
            return True
    except Exception:
        pass

    return str(value).strip() == ""


def _is_real_schedule_value(value):
    """
    判断产线日历单元格是否是真实排产。

    以下内容不算真实排产：
    - 空值
    - 停电检修

    只有真实订单名才算实际排产。
    """

    if _is_empty_cell_value(value):
        return False

    text = str(value).strip()

    if text == "停电检修":
        return False

    return True


def _is_monthly_schedule_sheet_name(sheet_name):
    """
    判断 sheet 是否是“月份排产图”。
    """
    import re

    text = str(sheet_name).strip()
    pattern = rf"^\d+{re.escape(MONTHLY_SCHEDULE_SHEET_SUFFIX)}$"

    return re.match(pattern, text) is not None


def _get_cell_fill_color(cell):
    """
    从旧排产结果单元格中读取订单填充色。

    只读取当前导出逻辑生成的 RGB 填充色；读取失败时返回 None。
    """
    fill = cell.fill

    if fill is None or fill.fill_type is None:
        return None

    color = fill.fgColor

    if color is None:
        return None

    if color.type != "rgb" or not color.rgb:
        return None

    rgb = str(color.rgb).strip()

    if len(rgb) == 8:
        rgb = rgb[-6:]

    if len(rgb) != 6:
        return None

    return rgb.upper()


def _load_order_color_mapping_from_previous_plan(previous_plan_file):
    """
    从旧排产结果文件中读取已有订单颜色映射。

    读取失败或没有识别到颜色时返回 None，调用方会自动回退到原颜色分配方式。
    """
    if not previous_plan_file:
        return None

    try:
        import os
        from openpyxl import load_workbook

        if not os.path.exists(previous_plan_file):
            return None

        workbook = load_workbook(previous_plan_file, data_only=True)
        order_color_mapping = {}

        for sheet_name in workbook.sheetnames:
            if not _is_monthly_schedule_sheet_name(sheet_name):
                continue

            ws = workbook[sheet_name]

            for row in ws.iter_rows(
                min_row=3,
                max_row=2 + NUM_LINES,
                min_col=2,
                max_col=ws.max_column,
            ):
                for cell in row:
                    value = cell.value

                    if not _is_real_schedule_value(value):
                        continue

                    order_name = str(value).strip()

                    if order_name in order_color_mapping:
                        continue

                    fill_color = _get_cell_fill_color(cell)

                    if fill_color:
                        order_color_mapping[order_name] = fill_color

        return order_color_mapping or None

    except Exception:
        return None


def _get_order_color_pool():
    """
    返回订单颜色池。
    """
    return [
        "E2F0D9",
        "D9EAF7",
        "FCE4D6",
        "EAD1DC",
        "FFF2CC",
        "D9EAD3",
        "D0E0E3",
        "EDEDED",
        "F4CCCC",
        "D9D2E9",
        "CFE2F3",
        "F9CB9C",
        "D5E8D4",
        "F8CECC",
        "DAE8FC",
        "E1D5E7",
    ]


def _has_actual_schedule_in_month(calendar_month_df, detail_month_df):
    """
    判断某个月是否存在实际排产。

    优先根据上方产线日历判断：
    - 只要日期列中出现真实订单名，就认为该月份需要导出。

    如果产线日历没有识别到，再用下方订单日产量明细兜底判断。
    """

    # =========================
    # 1. 根据上方产线日历判断
    # =========================
    for col in calendar_month_df.columns:
        if col == "产线":
            continue

        if not _is_date_column(col):
            continue

        for value in calendar_month_df[col]:
            if _is_real_schedule_value(value):
                return True

    # =========================
    # 2. 兜底：根据下方订单日产量明细判断
    # =========================
    for _, row in detail_month_df.iterrows():
        order_name = row.get("订单", "")

        if _is_empty_cell_value(order_name):
            continue

        order_name = str(order_name).strip()

        if order_name in ["线体合计", "产能合计"]:
            continue

        for col in detail_month_df.columns:
            if col == "订单":
                continue

            if not _is_date_column(col):
                continue

            value = row[col]

            if _is_empty_cell_value(value):
                continue

            try:
                if float(value) <= 0:
                    continue
            except Exception:
                pass

            return True

    return False


def _split_calendar_and_detail_by_month(calendar_df, detail_df):
    """
    按月份拆分产线日历和订单日产量明细。

    输入：
        calendar_df：
            第一列是“产线”，后面是日期列，例如 5/1、5/2、6/1。

        detail_df：
            第一列是“订单”，后面是日期列，例如 5/1、5/2、6/1。

    输出：
        [
            {
                "month": 5,
                "sheet_name": "5月排产图",
                "calendar_df": 5月产线日历,
                "detail_df": 5月订单日产量明细,
            },
            {
                "month": 6,
                "sheet_name": "6月排产图",
                "calendar_df": 6月产线日历,
                "detail_df": 6月订单日产量明细,
            },
        ]
    """

    if "产线" not in calendar_df.columns:
        raise ValueError("calendar_df 中缺少 '产线' 列，无法按月份导出排产图。")

    if "订单" not in detail_df.columns:
        raise ValueError("detail_df 中缺少 '订单' 列，无法按月份导出订单日产量明细。")

    month_to_columns = {}

    for col in calendar_df.columns:
        if col == "产线":
            continue

        if not _is_date_column(col):
            continue

        month = _get_month_from_date_column(col)

        if month not in month_to_columns:
            month_to_columns[month] = []

        month_to_columns[month].append(col)

    if not month_to_columns:
        raise ValueError("没有从排产结果中识别到日期列，无法生成月份排产图。")

    month_items = []

    for month in month_to_columns:
        cols = month_to_columns[month]

        calendar_month_df = calendar_df[["产线"] + cols].copy()

        # detail_df 理论上与 calendar_df 具有同样的日期列；
        # 这里做一次保护，避免某些日期列不存在时报错。
        detail_cols = [
            col for col in cols
            if col in detail_df.columns
        ]

        detail_month_df = detail_df[["订单"] + detail_cols].copy()

        # =========================
        # 跳过没有实际排产的月份
        # =========================
        #
        # 例如：
        # 模型为了寻找可行解扩展到了 6 月 30 日，
        # 但实际订单全部在 5 月完成。
        #
        # 此时 calendar_df 中虽然存在 6/1 ~ 6/30 的日期列，
        # 但这些列没有任何真实订单。
        #
        # 这种月份不应该导出为单独的“6月排产图”。
        if not _has_actual_schedule_in_month(
                calendar_month_df=calendar_month_df,
                detail_month_df=detail_month_df,
        ):
            continue

        sheet_name = f"{month}{MONTHLY_SCHEDULE_SHEET_SUFFIX}"

        month_items.append({
            "month": month,
            "sheet_name": sheet_name,
            "calendar_df": calendar_month_df,
            "detail_df": detail_month_df,
        })

    if not month_items:
        raise ValueError("排产结果中没有识别到任何存在实际生产的月份，无法生成月份排产图。")

    return month_items


def _copy_sheet_from_existing_workbook(
    source_file,
    source_sheet_name,
    target_file,
    target_sheet_name,
    insert_index=1,
):
    """
    将旧结果文件中的某个 sheet 复制到新结果文件中。

    插单模式下用于：
    - 从 CP_SAT_排产结果.xlsx 复制原始“表2_产线日历”；
    - 放入 CP_SAT_插单排产结果.xlsx；
    - 保证表2是原计划，表3是插单后新计划。

    说明：
    该函数保留用于兼容旧版导出逻辑。
    新版导出已经改为“按月份输出排产图”，默认不再调用该函数。
    """
    from copy import copy
    from openpyxl import load_workbook
    from openpyxl.cell.cell import MergedCell

    source_wb = load_workbook(source_file)
    target_wb = load_workbook(target_file)

    if source_sheet_name not in source_wb.sheetnames:
        raise ValueError(
            f"旧结果文件 {source_file} 中没有找到 sheet：{source_sheet_name}"
        )

    if target_sheet_name in target_wb.sheetnames:
        del target_wb[target_sheet_name]

    source_ws = source_wb[source_sheet_name]

    target_ws = target_wb.create_sheet(
        title=target_sheet_name,
        index=insert_index,
    )

    # =========================
    # 复制单元格内容和样式
    # =========================
    for row in source_ws.iter_rows():
        for cell in row:
            if isinstance(cell, MergedCell):
                continue

            new_cell = target_ws.cell(
                row=cell.row,
                column=cell.column,
                value=cell.value,
            )

            if cell.has_style:
                new_cell._style = copy(cell._style)

            if cell.number_format:
                new_cell.number_format = cell.number_format

            if cell.alignment:
                new_cell.alignment = copy(cell.alignment)

            if cell.font:
                new_cell.font = copy(cell.font)

            if cell.fill:
                new_cell.fill = copy(cell.fill)

            if cell.border:
                new_cell.border = copy(cell.border)

    # =========================
    # 复制合并单元格
    # =========================
    for merged_range in source_ws.merged_cells.ranges:
        target_ws.merge_cells(str(merged_range))

    # =========================
    # 复制列宽
    # =========================
    for col_letter, col_dim in source_ws.column_dimensions.items():
        target_ws.column_dimensions[col_letter].width = col_dim.width

    # =========================
    # 复制行高
    # =========================
    for row_idx, row_dim in source_ws.row_dimensions.items():
        target_ws.row_dimensions[row_idx].height = row_dim.height

    # =========================
    # 复制冻结窗格和筛选
    # =========================
    target_ws.freeze_panes = source_ws.freeze_panes

    if source_ws.auto_filter and source_ws.auto_filter.ref:
        target_ws.auto_filter.ref = source_ws.auto_filter.ref

    target_wb.save(target_file)


def _get_base_styles():
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

    header_fill = PatternFill("solid", fgColor="D9EAF7")
    title_fill = PatternFill("solid", fgColor="F4F9FD")
    header_font = Font(bold=True, color="000000")
    title_font = Font(size=14, bold=True)
    thin = Side(style="thin", color="B7B7B7")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    return {
        "header_fill": header_fill,
        "title_fill": title_fill,
        "header_font": header_font,
        "title_font": title_font,
        "border": border,
        "center": center,
    }


def _format_header_row(ws, row_idx, max_col):
    styles = _get_base_styles()

    for col_idx in range(1, max_col + 1):
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.fill = styles["header_fill"]
        cell.font = styles["header_font"]
        cell.border = styles["border"]
        cell.alignment = styles["center"]


def _format_range(ws, start_row, end_row, start_col, end_col):
    styles = _get_base_styles()

    if end_row < start_row:
        return

    for r in range(start_row, end_row + 1):
        for c in range(start_col, end_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = styles["border"]
            cell.alignment = styles["center"]


def _format_order_sheet(ws):
    from openpyxl.utils import get_column_letter

    styles = _get_base_styles()

    ws["A1"] = "表1：订单视图"
    ws["A1"].font = styles["title_font"]
    ws["A1"].fill = styles["title_fill"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ws.max_column)

    _format_header_row(ws, 2, ws.max_column)
    _format_range(ws, 3, ws.max_row, 1, ws.max_column)

    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:{get_column_letter(ws.max_column)}{ws.max_row}"

    widths = {
        "订单": 18,
        "内部订单名": 24,
        "插单处理方式": 14,
        "是否插单影响": 14,
        "是否插单": 10,
        "是否加量": 10,
        "原需求量": 14,
        "插单增加量": 14,
        "最终需求量": 14,
        "所需产线天数": 14,
        "剩余窗口天数": 14,
        "自动紧迫度": 14,
        "紧迫度权重": 14,
        "窗口开始": 12,
        "窗口结束": 12,
        "实际开工": 12,
        "实际完工": 12,
        "生产天数": 12,
        "总产线·天数": 14,
        "需求量": 14,
        "实际产量": 14,
        "超产线天数": 14,
        "超产量": 14,
        "是否延期": 10,
        "延期天数": 12,
        "延迟天数": 12,
    }

    # 根据表头名称设置列宽。
    # 这样即使 result_parser.py 后续调整字段顺序，也不会导致列宽错位。
    for col_idx in range(1, ws.max_column + 1):
        header_value = ws.cell(row=2, column=col_idx).value
        header_text = str(header_value).strip() if header_value is not None else ""
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = widths.get(header_text, 14)

    number_headers = {
        "原需求量",
        "插单增加量",
        "最终需求量",
        "所需产线天数",
        "剩余窗口天数",
        "紧迫度权重",
        "生产天数",
        "总产线·天数",
        "需求量",
        "实际产量",
        "超产线天数",
        "超产量",
        "延期天数",
        "延迟天数",
    }

    decimal_headers = {
        "自动紧迫度",
    }

    for col_idx in range(1, ws.max_column + 1):
        header_value = ws.cell(row=2, column=col_idx).value
        header_text = str(header_value).strip() if header_value is not None else ""

        if header_text in number_headers:
            for cell in ws.iter_cols(
                min_col=col_idx,
                max_col=col_idx,
                min_row=3,
                max_row=ws.max_row,
            ):
                for item in cell:
                    item.number_format = "#,##0"

        if header_text in decimal_headers:
            for cell in ws.iter_cols(
                min_col=col_idx,
                max_col=col_idx,
                min_row=3,
                max_row=ws.max_row,
            ):
                for item in cell:
                    item.number_format = "0.0000"


def _format_calendar_and_detail_sheet(
    ws,
    calendar_df,
    detail_df,
    detail_title_excel_row,
    title_text="表2：产线日历",
    detail_title_text="表2-附表：订单日产量明细",
    order_color_mapping=None,
):
    from openpyxl.styles import PatternFill, Font
    from openpyxl.utils import get_column_letter

    styles = _get_base_styles()

    # =========================
    # 上方标题：产线日历
    # =========================
    ws["A1"] = title_text
    ws["A1"].font = styles["title_font"]
    ws["A1"].fill = styles["title_fill"]
    ws.merge_cells(
        start_row=1,
        start_column=1,
        end_row=1,
        end_column=calendar_df.shape[1]
    )

    calendar_header_row = 2
    calendar_first_data_row = 3
    calendar_last_data_row = calendar_first_data_row + len(calendar_df) - 1

    _format_header_row(ws, calendar_header_row, calendar_df.shape[1])
    _format_range(ws, calendar_first_data_row, calendar_last_data_row, 1, calendar_df.shape[1])

    # =========================
    # 下方标题：订单日产量明细
    # =========================
    ws.cell(row=detail_title_excel_row, column=1).value = detail_title_text
    ws.cell(row=detail_title_excel_row, column=1).font = styles["title_font"]
    ws.cell(row=detail_title_excel_row, column=1).fill = styles["title_fill"]
    ws.merge_cells(
        start_row=detail_title_excel_row,
        start_column=1,
        end_row=detail_title_excel_row,
        end_column=detail_df.shape[1]
    )

    detail_header_row = detail_title_excel_row + 1
    detail_first_data_row = detail_header_row + 1
    detail_last_data_row = detail_first_data_row + len(detail_df) - 1

    _format_header_row(ws, detail_header_row, detail_df.shape[1])
    _format_range(ws, detail_first_data_row, detail_last_data_row, 1, detail_df.shape[1])

    # =========================
    # 自动筛选与冻结
    # =========================
    ws.freeze_panes = "B3"
    ws.auto_filter.ref = f"A2:{get_column_letter(calendar_df.shape[1])}{calendar_last_data_row}"

    # =========================
    # 订单颜色池：上下两个表保持一致
    # =========================
    color_pool = _get_order_color_pool()

    if order_color_mapping is None:
        order_fills = {}
    else:
        order_fills = order_color_mapping

    color_idx = 0
    used_colors = set(order_fills.values())

    # 从上方产线日历里按订单第一次出现顺序分配颜色
    for r in range(calendar_first_data_row, calendar_last_data_row + 1):
        for c in range(2, calendar_df.shape[1] + 1):
            value = ws.cell(r, c).value
            if value is not None:
                value = str(value).strip()
                if value != "" and value not in order_fills:
                    while (
                        len(used_colors) < len(color_pool)
                        and color_pool[color_idx % len(color_pool)] in used_colors
                    ):
                        color_idx += 1

                    order_fills[value] = color_pool[color_idx % len(color_pool)]
                    used_colors.add(order_fills[value])
                    color_idx += 1

    # =========================
    # 上方产线日历着色
    # =========================
    for r in range(calendar_first_data_row, calendar_last_data_row + 1):
        ws.cell(r, 1).font = Font(bold=True)

        for c in range(2, calendar_df.shape[1] + 1):
            cell = ws.cell(r, c)
            value = cell.value

            if value is not None:
                value = str(value).strip()
                if value in order_fills:
                    cell.fill = PatternFill("solid", fgColor=order_fills[value])

    # =========================
    # 下方订单日产量明细着色
    # 下方表结构：A=订单，B起=日期
    # =========================
    if len(detail_df) > 0:
        summary_fill = PatternFill("solid", fgColor="D9EAF7")
        summary_font = Font(bold=True)

        for r in range(detail_first_data_row, detail_last_data_row + 1):
            order_cell = ws.cell(r, 1)
            order_cell.font = Font(bold=True)

            order_name = order_cell.value

            if order_name is not None:
                order_name = str(order_name).strip()

                # 汇总行：线体合计、产能合计
                if order_name in ["线体合计", "产能合计"]:
                    for c in range(1, detail_df.shape[1] + 1):
                        cell = ws.cell(r, c)
                        cell.fill = summary_fill
                        cell.font = summary_font

                        # A列是文字，不设置数字格式
                        if c == 1:
                            continue

                        # 显示 18、4,140,000 这类数值
                        cell.number_format = "#,##0"
                    continue

                # 普通订单行按订单颜色处理
                if order_name != "" and order_name in order_fills:
                    fill = PatternFill("solid", fgColor=order_fills[order_name])

                    # 订单列染色
                    order_cell.fill = fill

                    # 有生产量的日期单元格染色
                    for c in range(2, detail_df.shape[1] + 1):
                        cell = ws.cell(r, c)
                        if cell.value not in (None, ""):
                            cell.fill = fill
                            cell.number_format = "#,##0"

    # =========================
    # 列宽
    # =========================
    ws.column_dimensions["A"].width = 14

    # 日期列需要放得下 4,140,000，避免 Excel 显示 #######
    for col_idx in range(2, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 12

    # 行高
    for row_idx in range(1, ws.max_row + 1):
        ws.row_dimensions[row_idx].height = 22


def print_monthly_sheet_info(display_dates, calendar_df=None, detail_df=None):
    """
    打印本次实际会导出的月份排产图名称。

    如果传入 calendar_df / detail_df：
    - 按实际有排产的月份打印；
    - 空月份不会打印。

    如果没有传入 calendar_df / detail_df：
    - 保持旧逻辑，按 display_dates 打印。
    """

    months = []

    if calendar_df is not None and detail_df is not None:
        month_sheets = _split_calendar_and_detail_by_month(
            calendar_df=calendar_df,
            detail_df=detail_df,
        )

        months = [
            item["month"]
            for item in month_sheets
        ]

    else:
        for display_date in display_dates:
            month = display_date.month
            if month not in months:
                months.append(month)

    for idx, month in enumerate(months, start=2):
        print(f"Sheet {idx}：{month}月排产图")