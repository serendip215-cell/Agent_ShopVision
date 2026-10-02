"""Load JSON defaults, with explicit command-line arguments taking priority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_configured_args(parser: argparse.ArgumentParser, section: str, root: Path):
    parser.add_argument("--config", default="configs/retrieval.json", help="配置文件，相对项目根目录。")
    probe = argparse.ArgumentParser(add_help=False)
    probe.add_argument("--config", default="configs/retrieval.json")
    selected, _ = probe.parse_known_args()
    path = Path(selected.config)
    if not path.is_absolute():
        path = root / path
    try:
        with path.open(encoding="utf-8-sig") as handle:
            configuration = json.load(handle)
        if not isinstance(configuration, dict):
            raise ValueError("配置文件顶层必须是 JSON 对象")
        defaults = configuration.get(section, {})
        if not isinstance(defaults, dict):
            raise ValueError(f"{section} 必须是 JSON 对象")
        actions = {action.dest: action for action in parser._actions if action.option_strings}
        for key, value in defaults.items():
            if key not in actions or key in {"help", "config"}:
                raise ValueError(f"{section} 中存在不支持的字段：{key}")
            action = actions[key]
            if isinstance(action, argparse._StoreTrueAction):
                if not isinstance(value, bool):
                    raise ValueError(f"{section}.{key} 必须是布尔值")
            elif action.type is int:
                if type(value) is not int or value < 0:
                    raise ValueError(f"{section}.{key} 必须是非负整数")
            elif not isinstance(value, str):
                raise ValueError(f"{section}.{key} 必须是字符串")
            if action.choices and value not in action.choices:
                raise ValueError(f"{section}.{key} 必须是 {action.choices} 之一")
        parser.set_defaults(**defaults)
    except (OSError, ValueError) as exc:
        parser.error(f"无法读取检索配置 {selected.config}：{exc}")
    return parser.parse_args()
