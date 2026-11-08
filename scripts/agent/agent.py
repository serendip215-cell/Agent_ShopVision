"""实验5 Agent 骨架：组装工具 + 意图驱动的工具调用编排。

5.3 已实现的部分（解耦，不依赖 5.2）：
    - create_agent()：初始化 agent，注册白名单工具
    - run()：照标准流程「意图匹配工具 → 调工具 → 返回结果」跑一轮
    - 纯意图 dict 输入即可跑通，可用于工具链路 / 准确率统计测试

5.2 交付后已补上（见 scripts/agent/intent_parser.py）：
    - _parse_intent()：用户话 → {"tool", "arguments"}，走 Qwen3-4B LoRA 微调模型；
      工具名走白名单编辑距离纠错（修 text_search 被写成 tool_search 的实测问题）；
      模型不可用时自动降级到规则解析，前端永远有响应。
仍待补：
    - 多轮对话的槽位继承/记忆（见方案 §9 待定）
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from . import tools

logger = logging.getLogger("shopvision.agent")


@dataclass
class Agent:
    """极简 Agent：持有工具表，按结构化意图调用。不经 LangChain 也可独立跑。"""

    tool_registry: dict[str, dict[str, Any]] = field(default_factory=lambda: tools.TOOLS)

    def run_intent(self, intent: dict[str, Any]) -> dict[str, Any]:
        """给定结构化意图 {"tool": <名>, "arguments": {...}} 执行一轮。

        正常路径下 intent 由 _parse_intent 从用户话解析得到；
        这里直接接收 intent，也用于单测与准确率统计。
        """
        name = intent.get("tool") or intent.get("intent")
        args = intent.get("arguments") or {}
        entry = self.tool_registry.get(name)
        if entry is None:
            return {"ok": False, "reason": f"未找到工具：{name}", "tool": name}
        try:
            result = entry["fn"](**args)
            return {"ok": not result.get("error"), "tool": name, "arguments": args, "result": result}
        except TypeError as e:
            # 参数与函数签名不匹配（LLM 可能给出错误的参数名/缺失必填）
            return {"ok": False, "tool": name, "arguments": args,
                    "reason": f"工具参数异常：{e}"}


# 5.2 已交付：意图解析走微调模型，模型不可用时自动降级规则解析。
# 模型路径由环境变量提供，避免把权重路径写死进代码。
DEFAULT_MODEL = os.environ.get("SHOPVISION_AGENT_MODEL", "Qwen/Qwen3-4B-Instruct-2507")
DEFAULT_ADAPTER = os.environ.get("SHOPVISION_AGENT_ADAPTER") or None

_parser = None


def _get_parser():
    """懒加载单例，避免每次调用都重新载入 4B 权重。"""
    global _parser
    if _parser is None:
        from .intent_parser import IntentParser

        _parser = IntentParser(DEFAULT_MODEL, DEFAULT_ADAPTER)
    return _parser


def _parse_intent(user_input: str) -> dict[str, Any]:
    """用户话 → 结构化意图 {tool, arguments}。

    走 5.2 微调模型；模型加载或推理失败时自动降级到规则解析，前端永远有响应。

    **意图拿到后还要过一层确定性后处理**（category_map.fill_arguments）：
      - 规范化 query：模型常把「找」「有没有」留在 query 里
      - 补类目：训练数据里类目是明写的，模型没学会从商品名推断

    后处理放在这里而不是只放评测脚本，是为了保证**评测分与实际演示行为一致**。
    见 docs/实验五/08-5.3准确率根因与修复.md
    """
    intent = _get_parser().parse(user_input)

    try:
        from .category_map import fill_arguments

        args, notes = fill_arguments(intent.get("arguments") or {}, user_input)
        if isinstance(args, dict):
            intent = {**intent, "arguments": args}
        if notes:
            # 记录后处理动作，供 /chat 接口的 thinking 文案与调试用
            intent["post_process"] = notes
            logger.info("后处理：%s", notes)
    except Exception as e:  # noqa: BLE001
        # 后处理失败不能影响主链路
        logger.warning("后处理失败，返回原始意图：%s", e)

    return intent


def create_agent() -> Agent:
    """初始化 Agent（5.3：注册白名单工具）。"""
    logger.info("create_agent：注册 %d 个工具：%s",
                len(Agent().tool_registry), list(Agent().tool_registry))
    return Agent()


def run(user_input: str) -> dict[str, Any]:
    """注入入口：用户话 → 意图 → 工具 → 结果。

    5.4 的 /api/v1/agent/chat 接口调用此入口。
    """
    agent = create_agent()
    intent = _parse_intent(user_input)  # 5.2 后真实接入
    return agent.run_intent(intent)


__all__ = ["Agent", "create_agent", "run", "_parse_intent"]