# CP-SAT 光伏车间订单排产项目

本项目使用 Google OR-Tools CP-SAT 求解器实现“18条产线、多订单、连续生产、减少换线”的排产模型。

运行后会生成一个 Excel 文件：

```text
CP_SAT_排产结果.xlsx
```

Excel 中包含三张工作表：

1. `表1_订单视图`
2. `表2_产线日历`
3. `表3_换线报告`

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 主要修改文件

### `config.py`

修改排产周期、产线数量、单线日产能、是否每天满产：

```python
NUM_LINES = 18
HORIZON = 30
DAILY_CAPACITY = 230000
FULL_LOAD_EVERY_DAY = False
```

### `data.py`

修改订单数据：

```python
orders = [
    {
        "name": "公版",
        "quantity": 22080000,
        "release": 0,
        "due": 7,
    },
]
```

其中：

- `release=0` 表示排产起始日当天可以开工；
- `due=7` 表示排产起始日起第 8 天为交期；
- 如果 `START_DATE = 2026-04-01`，则 `due=7` 对应 4月8日。
