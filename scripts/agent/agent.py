"""实验5 Agent 骨架：组装工具 + 意图驱动的工具调用编排。

5.3 已实现的部分（解耦，不依赖 5.2）：
    - create_agent()：初始化 agent，注册白名单工具
    - run()：照标准流程「意图匹配工具 → 调工具 → 返回结果」跑一轮
    - 纯意图 dict 输入即可跑通，可用于工具链路 / 准确率统计测试

5.3 严格留 TODO（依赖 5.2 微调模型，未交付前不写实现）：
    - _parse_intent()：把用户自然语言解析为 {"tool", "arguments"} 结构化意图
      ——这一步要接 5.2 微调后的 LLM（模型学会输出 text_search 调用格式）。
      未接前，run() 的入参直接给结构化意图 dict 占位。
    - 多轮对话的槽位继承/记忆（见方案 §9 待定）
    - 无 LLM 时的规则降级解析（若组内决定在 5.3 提前做，另行补）
"""

from __future__ import annotations

import logging
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

        TODO(5.2)：真实路径里 intent 由 LLM 从用户话解析得到（_parse_intent）；
        这里直接接收 intent，用于 5.3 的工具链路测试与准确率统计。
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


# TODO(5.2)：接微调后的 LLM。当前桩：接受结构化意图 dict（或能转成 dict 的对象）。
def _parse_intent(user_input: str) -> dict[str, Any]:
    raise NotImplementedError(
        "5.2 微调模型未交付：意图解析(用户话→{tool,arguments})尚未接入。"
        "5.3 阶段请直接调用 agent.run_intent(intent) 测试工具链路。"
    )


def create_agent() -> Agent:
    """初始化 Agent（5.3：注册白名单工具）。"""
    logger.info("create_agent：注册 %d 个工具：%s",
                len(Agent().tool_registry), list(Agent().tool_registry))
    return Agent()


def run(user_input: str) -> dict[str, Any]:
    """注入入口：用户话 → 意图 → 工具 → 结果。

    TODO(5.2)：接 _parse_intent 后启用真意图解析；当前桩直接抛 NotImplementedError，
    run() 在 5.2 交付后才会被 5.4 的 /chat 接口调用。
    """
    agent = create_agent()
    intent = _parse_intent(user_input)  # 5.2 后真实接入
    return agent.run_intent(intent)


__all__ = ["Agent", "create_agent", "run", "_parse_intent"]