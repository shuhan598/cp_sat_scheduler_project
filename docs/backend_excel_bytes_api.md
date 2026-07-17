# 后端调用排产并获取 Excel 字节流说明

## 1. 调用目标

排产程序运行后会生成 Excel 文件。后端不需要自己读取控制台输出，也不需要解析 Excel 内容，只需要调用 Python 提供的函数，拿到 Excel 的二进制字节流后通过接口返回给前端。

当前提供的调用入口在 `main.py`：

```python
from main import run_schedule_and_get_excel_bytes
```

## 2. 输入要求

默认读取项目根目录下的：

```text
input_orders.json
```

该 JSON 文件仍按现有格式传入订单、插单和停电计划。

如果后端已经把请求数据写入其他 JSON 文件，也可以传入文件路径：

```python
response = run_schedule_and_get_excel_bytes("path/to/input_orders.json")
```

## 3. Python 调用方式

```python
from main import run_schedule_and_get_excel_bytes

response = run_schedule_and_get_excel_bytes()

if not response["success"]:
    raise RuntimeError(response["message"])

excel_bytes = response["content"]
filename = response["filename"]
content_type = response["content_type"]
```

## 4. 成功返回结构

```python
{
    "success": True,
    "message": "排产成功",
    "content": b"...Excel二进制字节...",
    "filename": "CP_SAT_排产结果.xlsx",
    "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "schedule_result": {
        "output_file": "CP_SAT_排产结果.xlsx",
        "result": {},
        "orders": [],
        "model_start_date": "...",
        "model_end_date": "..."
    }
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | bool | 是否排产成功 |
| `message` | str | 返回说明 |
| `content` | bytes | Excel 文件字节流，后端直接返回这个字段 |
| `filename` | str | 下载文件名，普通排产一般是 `CP_SAT_排产结果.xlsx`，插单排产一般是 `CP_SAT_插单排产结果.xlsx` |
| `content_type` | str | Excel MIME 类型 |
| `schedule_result` | dict | 排产流程返回的原始结果，包含 `output_file` 等信息 |

## 5. 失败返回结构

如果没有找到可行排产结果，返回：

```python
{
    "success": False,
    "message": "未找到可行排产结果",
    "content": None,
    "filename": None,
    "content_type": None,
    "schedule_result": None
}
```

后端收到 `success == False` 时，不应该返回 Excel 文件流，而应该返回业务错误信息。

## 6. FastAPI 返回文件流示例

```python
from fastapi import FastAPI, HTTPException, Response

from main import run_schedule_and_get_excel_bytes

app = FastAPI()


@app.post("/schedule")
def schedule():
    result = run_schedule_and_get_excel_bytes()

    if not result["success"]:
        raise HTTPException(status_code=422, detail=result["message"])

    return Response(
        content=result["content"],
        media_type=result["content_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{result["filename"]}"'
        },
    )
```

## 7. Flask 返回文件流示例

```python
from io import BytesIO

from flask import Flask, jsonify, send_file

from main import run_schedule_and_get_excel_bytes

app = Flask(__name__)


@app.post("/schedule")
def schedule():
    result = run_schedule_and_get_excel_bytes()

    if not result["success"]:
        return jsonify({"message": result["message"]}), 422

    return send_file(
        BytesIO(result["content"]),
        mimetype=result["content_type"],
        as_attachment=True,
        download_name=result["filename"],
    )
```

## 8. 后端接口响应头要求

后端返回给前端时建议设置：

```http
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="CP_SAT_排产结果.xlsx"
```

如果是插单排产，文件名会自动变成：

```text
CP_SAT_插单排产结果.xlsx
```

## 9. 注意事项

1. `content` 是 `bytes`，不要转成 JSON 字符串返回。
2. HTTP 接口要直接返回二进制响应体。
3. 如果前端要下载文件，后端必须设置 `Content-Disposition`。
4. 当前函数会先生成 Excel 文件，再读取该文件的字节流。
5. 如果后端通过子进程调用 Python，建议改为直接调用 Python 函数，避免解析控制台输出。