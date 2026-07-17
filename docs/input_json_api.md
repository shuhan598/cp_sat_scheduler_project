# 定线排产 JSON 输入需求接口文档

## 1. 接口定位

本项目不再使用 `input_orders.xlsx` 作为订单和插单输入。排产程序从项目根目录下的 `input_orders.json` 读取普通订单和插单订单。

结果输出仍为 Excel 文件：

- 普通排产 / 停电排产：`CP_SAT_排产结果.xlsx`
- 插单重排：`CP_SAT_插单排产结果.xlsx`

停电计划已纳入同一个 JSON 输入文件，通过顶层 `power_outages` 数组传入。

## 2. 请求文件

文件名固定为：

```text
input_orders.json
```

程序入口：

```bash
python main.py
```

`main.py` 会自动读取 `input_orders.json`，并根据 `insert_orders` 是否存在有效订单判断普通排产或插单重排。

## 3. 顶层结构

```json
{
  "orders": [],
  "insert_orders": [],
  "power_outages": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `orders` | array | 是 | 普通订单列表，至少用于构建基础排产订单 |
| `insert_orders` | array | 否 | 插单订单列表。省略或空数组表示普通排产 |
| `power_outages` | array | 否 | 停电计划列表。省略或空数组表示无停电 |

## 4. 普通订单字段

```json
{
  "order": "意诚",
  "quantity": 5700000,
  "earliest_start": "2026-05-01",
  "latest_finish": "2026-05-07"
}
```

| 字段 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `order` | string | 是 | 订单名称 | `意诚` |
| `quantity` | integer/string | 是 | 订单需求量，可为整数或可转换为整数的字符串 | `5700000` |
| `earliest_start` | string | 是 | 最早开工日期，格式建议 `YYYY-MM-DD` | `2026-05-01` |
| `latest_finish` | string | 是 | 最晚完工日期，格式建议 `YYYY-MM-DD` | `2026-05-07` |

## 5. 插单订单字段

```json
{
  "order": "宥阳",
  "quantity": 2000000,
  "insert_date": "2026-05-10",
  "earliest_start": "2026-05-10",
  "latest_finish": "2026-05-20"
}
```

| 字段 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `order` | string | 是 | 插单订单名称 | `宥阳` |
| `quantity` | integer/string | 是 | 插单新增需求量 | `2000000` |
| `insert_date` | string | 是 | 插单发生日期，格式建议 `YYYY-MM-DD` | `2026-05-10` |
| `earliest_start` | string | 是 | 插单订单允许开始生产的最早日期 | `2026-05-10` |
| `latest_finish` | string | 是 | 插单订单要求完成的最晚日期 | `2026-05-20` |

## 6. 停电计划字段

```json
{
  "start_date": "2026-05-08",
  "end_date": "2026-05-10",
  "affected_lines": "1-3",
  "pre_outage_ratio": "80%"
}
```

| 字段 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `start_date` | string | 是 | 停电开始日期，格式建议 `YYYY-MM-DD` | `2026-05-08` |
| `end_date` | string | 是 | 停电结束日期，格式建议 `YYYY-MM-DD` | `2026-05-10` |
| `affected_lines` | string/array | 是 | 受影响产线，支持 `全部`、`1,2,3`、`1-5`、`[1,2,3]` | `1-3` |
| `pre_outage_ratio` | number/string | 否 | 停电前一天产能比例，支持 `0.8`、`80%`、`80`；为空时按配置范围随机生成 | `80%` |
## 7. 普通排产示例

```json
{
  "orders": [
    {
      "order": "意诚",
      "quantity": 5700000,
      "earliest_start": "2026-05-01",
      "latest_finish": "2026-05-07"
    },
    {
      "order": "至上",
      "quantity": 12000000,
      "earliest_start": "2026-05-01",
      "latest_finish": "2026-05-15"
    }
  ],
  "insert_orders": [],
  "power_outages": []
}
```

## 8. 插单重排示例

```json
{
  "orders": [
    {
      "order": "意诚",
      "quantity": 5700000,
      "earliest_start": "2026-05-01",
      "latest_finish": "2026-05-07"
    },
    {
      "order": "至上",
      "quantity": 12000000,
      "earliest_start": "2026-05-01",
      "latest_finish": "2026-05-15"
    }
  ],
  "insert_orders": [
    {
      "order": "宥阳",
      "quantity": 2000000,
      "insert_date": "2026-05-10",
      "earliest_start": "2026-05-10",
      "latest_finish": "2026-05-20"
    }
  ],
  "power_outages": [
    {
      "start_date": "2026-05-08",
      "end_date": "2026-05-10",
      "affected_lines": "全部",
      "pre_outage_ratio": "80%"
    }
  ]
}
```

插单模式需要项目根目录存在旧排产结果 `CP_SAT_排产结果.xlsx`。程序会读取旧计划，用于冻结插单日期前计划并判断插单类型。

## 9. 校验规则

程序读取 JSON 时执行以下校验：

- 顶层必须是 JSON object；
- `orders` 必须存在，且必须是数组；
- `insert_orders` 如果存在，必须是数组；
- `power_outages` 如果存在，必须是数组；
- 普通订单必须包含 `order`、`quantity`、`earliest_start`、`latest_finish`；
- 插单订单必须包含 `order`、`quantity`、`insert_date`、`earliest_start`、`latest_finish`；
- `quantity` 不能为空，且必须能转换为整数；
- 日期不能为空，且必须能解析为日期；
- `earliest_start` 不能晚于 `latest_finish`；
- 插单订单的 `insert_date` 不能晚于 `latest_finish`；
- 停电记录的 `start_date` 不能晚于 `end_date`；
- 停电记录的 `affected_lines` 不能为空，且必须能解析出有效产线；
- `order` 为空字符串时，该记录会被忽略。

## 10. 模式判断

| 输入情况 | 运行模式 |
|---|---|
| `insert_orders` 不存在，且 `power_outages` 不存在或为空 | 普通排产 |
| `insert_orders` 为空数组，且 `power_outages` 存在有效记录 | 停电排产 |
| `insert_orders` 存在至少一条有效订单 | 插单重排 |

## 11. 字段映射

JSON 字段会转换为模型内部 raw order 字段：

| JSON 字段 | 内部字段 |
|---|---|
| `order` | `name` / `display_name` / `original_name` |
| `quantity` | `quantity` / `original_quantity` |
| `earliest_start` | `earliest_start_date` |
| `latest_finish` | `latest_finish_date` |
| `insert_date` | `insert_date` |
| `power_outages[].start_date` | `power_outages[].start_date` |
| `power_outages[].end_date` | `power_outages[].end_date` |
| `power_outages[].affected_lines` | `power_outages[].lines` |
| `power_outages[].pre_outage_ratio` | `power_outages[].pre_outage_ratio` |

后续排产、插单分类、旧计划读取和结果导出继续使用原有内部结构。


