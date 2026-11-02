"""把后端生成的 OpenAPI 规范导成两份交付物（离线可读，评审不用起服务）。

    cd webapp/backend
    python scripts/export_api_docs.py

产物（覆盖式重生成，改完接口重跑一遍即可）：
    docs/交付材料/实验四_第23组/api/openapi.json   OpenAPI 3 规范，可导入 Postman / 喂 AI
    docs/交付材料/实验四_第23组/api/API文档.md     人读版：路径/方法/参数/返回值/错误码表

报告要求 3「API 文档 + 异常处理说明」拿这份当底稿（wlz 润色排版仍是他的活）。
线上一份永远是最新的：跑起服务看 /docs、/scalar、/redoc。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from app.config import REPO_ROOT  # noqa: E402
from app.errors import ErrorCode  # noqa: E402
from app.main import app  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "交付材料" / "实验四_第23组" / "api"
_METHODS = ("get", "post", "put", "patch", "delete")
_PRIMITIVE = {
    "string": "字符串",
    "integer": "整数",
    "number": "小数",
    "boolean": "布尔",
    "object": "对象",
    "array": "数组",
}
_MAX_DEPTH = 2  # 嵌套展开到第 3 层为止，够我们这几个模型用


def _cell(text: str) -> str:
    """Markdown 表格单元格：竖线转义、换行压平。"""
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def _resolve(spec: dict, node: dict, depth: int = 0) -> dict:
    """跟着 $ref 走到真实模型（自引用时靠 depth 兜底，别转死）。"""
    if depth > 10 or not isinstance(node, dict) or "$ref" not in node:
        return node
    name = node["$ref"].rsplit("/", 1)[-1]
    return _resolve(spec, spec.get("components", {}).get("schemas", {}).get(name, {}), depth + 1)


def _type_of(spec: dict, node: dict) -> tuple[str, dict | None]:
    """返回（中文类型文字, 可继续展开的模型节点）。"""
    node = _resolve(spec, node)
    if "anyOf" in node:
        parts = [_resolve(spec, p) for p in node["anyOf"]]
        names = [
            _PRIMITIVE.get(p.get("type") or "", "对象") for p in parts if p.get("type") != "null"
        ]
        child = next((p for p in parts if isinstance(p.get("properties"), dict)), None)
        nullable = "（可为空）" if any(p.get("type") == "null" for p in parts) else ""
        return (" 或 ".join(dict.fromkeys(names)) or "对象") + nullable, child
    if node.get("type") == "array":
        inner_text, _ = _type_of(spec, node.get("items", {}))
        items = _resolve(spec, node.get("items", {}))
        return f"{inner_text} 的数组", items if "properties" in items else None
    if node.get("format") == "binary" or node.get("contentMediaType"):
        return "文件", None  # OpenAPI 3.1 用 contentMediaType 表示上传文件
    if "properties" in node:
        return "对象", node
    kind = node.get("type")
    if not kind:  # Any / 无 schema：批量结果是对象数组，单张是对象，别写成“字符串”
        return "对象或数组", None
    return _PRIMITIVE.get(kind, "字符串"), None


def _is_array(spec: dict, node: dict) -> bool:
    """这个字段本身是不是数组（决定嵌套路径用 [] 还是点号）。"""
    node = _resolve(spec, node)
    if "anyOf" in node:
        parts = [_resolve(spec, p) for p in node["anyOf"]]
        node = next((p for p in parts if isinstance(p, dict)), {})
    return node.get("type") == "array"


def _field_rows(spec: dict, node: dict, prefix: str = "", depth: int = 0) -> list[str]:
    """把一个模型铺成表格行，嵌套对象用点号路径（数组用 [] 后缀）。"""
    node = _resolve(spec, node)
    rows = []
    for name, prop in (node.get("properties") or {}).items():
        text, child = _type_of(spec, prop)
        rows.append(f"| `{prefix}{name}` | {text} | {_cell(prop.get('description', ''))} |")
        if child is not None and depth < _MAX_DEPTH:
            step = "[]." if _is_array(spec, prop) else "."
            rows.extend(_field_rows(spec, child, f"{prefix}{name}{step}", depth + 1))
    return rows


def _params_table(spec: dict, operation: dict) -> list[str]:
    rows = [
        "| 参数 | 位置 | 类型 | 必填 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for param in operation.get("parameters", []):
        schema = param.get("schema", {})
        rows.append(
            f"| `{param['name']}` | {param.get('in')} | {_type_of(spec, schema)[0]} | "
            f"{'是' if param.get('required') else '否'} | {_cell(param.get('description'))} |"
        )
    body = (operation.get("requestBody") or {}).get("content", {})
    for media_type, media in body.items():
        schema = _resolve(spec, media.get("schema", {}))
        required = set(schema.get("required") or [])
        is_multipart = media_type.startswith("multipart")
        for name, prop in (schema.get("properties") or {}).items():
            text, _ = _type_of(spec, prop)
            location = "文件" if text == "文件" else ("表单字段" if is_multipart else "请求体")
            rows.append(
                f"| `{name}` | {location} | {text} | {'是' if name in required else '否'} | "
                f"{_cell(prop.get('description'))} |"
            )
    return rows if len(rows) > 2 else []


def _response_rows(spec: dict, operation: dict) -> list[str]:
    content = operation["responses"]["200"]["content"]
    schema = _resolve(spec, next(iter(content.values()))["schema"])
    result = _resolve(spec, (schema.get("properties") or {}).get("result", {}))
    rows = [
        "| 字段 | 类型 | 说明 |",
        "|---|---|---|",
        "| `code` | 整数 | 0=成功；非 0 见错误码表 |",
        "| `msg` | 字符串 | 面向用户的提示 |",
    ]
    if "anyOf" in result:  # 形如 <Model> | null：取有字段的那一支
        parts = [_resolve(spec, p) for p in result["anyOf"]]
        result = next((p for p in parts if "properties" in p), {})
    rows.extend(_field_rows(spec, result, "result."))
    return rows


def render_markdown(spec: dict, codes: list[ErrorCode]) -> str:
    lines = [
        f"# {spec['info']['title']}（v{spec['info']['version']}）",
        "",
        "> 本文档由 `webapp/backend/scripts/export_api_docs.py` 从后端代码自动生成，**不要手改**；",
        "> 改完接口在 `webapp/backend` 下重跑一次即可。"
        "线上最新版：服务跑起来看 `/docs`、`/scalar`、`/redoc`。",
        "",
        spec["info"].get("description", "").strip(),
        "",
        "## 基础约定",
        "",
        "- 基址 `http://localhost:8000`，版本前缀 `/api/v1`",
        "- 所有接口（含出错）都返回同一形状：`{code, result, msg}`，**HTTP 状态码 = code 前三位**",
        "- 图像接口用 `multipart/form-data`，文本接口用 `application/json`",
        "- 调用示例见 [`webapp/README.md` §三](https://github.com/serendip215-cell/Agent_ShopVision/blob/main/webapp/README.md)",
        "",
        "## 错误码表",
        "",
        "| 业务码 | HTTP | 默认提示 | 场景 |",
        "|---:|---:|---|---|",
    ]
    for code in codes:
        if code is ErrorCode.OK:
            continue
        lines.append(f"| `{int(code)}` | {code.http_status} | {code.message} | {code.name} |")
    lines.append("")

    tags = {tag["name"]: tag.get("description", "") for tag in spec.get("tags", [])}
    grouped: dict[str, list[tuple[str, str, dict]]] = {name: [] for name in tags} or {"接口": []}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in _METHODS:
                continue
            tag = (operation.get("tags") or ["接口"])[0]
            grouped.setdefault(tag, []).append((method.upper(), path, operation))

    lines.append("## 接口清单")
    lines.append("")
    for tag, endpoints in grouped.items():
        if not endpoints:
            continue
        lines.append(f"### {tag}")
        if tags.get(tag):
            lines.append("")
            lines.append(f"> {tags[tag]}")
        for method, path, operation in endpoints:
            lines.extend(["", f"#### `{method} {path}` — {operation.get('summary', '')}", ""])
            if operation.get("description"):
                lines.extend([_cell(operation["description"]), ""])
            table = _params_table(spec, operation)
            if table:
                lines.extend(["**请求**", "", *table, ""])
            lines.extend(["**返回**（`result` 结构如下；`code`/`msg` 见基础约定）", ""])
            lines.extend([*_response_rows(spec, operation), ""])
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    spec = app.openapi()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "openapi.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "API文档.md").write_text(render_markdown(spec, list(ErrorCode)), encoding="utf-8")
    print(f"已生成：{OUT_DIR}")


if __name__ == "__main__":
    main()
