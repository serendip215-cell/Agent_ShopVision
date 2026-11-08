"""Serve the fine-tuned ShopVision model through an OpenAI-compatible API.

The server loads the Qwen3 base model and the v2 LoRA adapter once, then
exposes ``/v1/chat/completions`` for the LangChain Agent on another LAN host.
Paths are relative to the repository root unless overridden by environment
variables.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_MODEL = (
    REPO_ROOT
    / "models/models/Qwen--Qwen3-4B-Instruct-2507/snapshots/master"
)
DEFAULT_ADAPTER = REPO_ROOT / "dist/lora_adapter_v2"

MODEL_NAME = os.getenv("SHOPVISION_MODEL_NAME", "shopvision-v2")
PUBLIC_HOST = os.getenv("SHOPVISION_MODEL_PUBLIC_HOST", "10.77.7.4")


def _resolve_path(value: str, default: Path) -> Path:
    path = Path(value) if value else default
    return path if path.is_absolute() else REPO_ROOT / path


BASE_MODEL_PATH = _resolve_path(
    os.getenv("SHOPVISION_BASE_MODEL", ""), DEFAULT_BASE_MODEL
)
ADAPTER_PATH = _resolve_path(os.getenv("SHOPVISION_ADAPTER", ""), DEFAULT_ADAPTER)

app = FastAPI(title="ShopVision Fine-tuned Model Server", version="1.0.0")
_tokenizer: Any = None
_model: Any = None
_generation_lock = asyncio.Semaphore(1)


class ChatMessage(BaseModel):
    role: str
    content: Any = ""


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_NAME
    messages: list[ChatMessage]
    temperature: float = 0.0
    max_tokens: int = Field(default=256, ge=1, le=512)
    stream: bool = False


def _load_model() -> None:
    global _tokenizer, _model
    if _model is not None:
        return
    if not BASE_MODEL_PATH.exists():
        raise RuntimeError(f"基座模型路径不存在：{BASE_MODEL_PATH}")
    if not ADAPTER_PATH.exists():
        raise RuntimeError(f"LoRA 适配器路径不存在：{ADAPTER_PATH}")

    _tokenizer = AutoTokenizer.from_pretrained(
        str(BASE_MODEL_PATH), trust_remote_code=True
    )
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    base = AutoModelForCausalLM.from_pretrained(
        str(BASE_MODEL_PATH),
        quantization_config=quant_config,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    _model = PeftModel.from_pretrained(base, str(ADAPTER_PATH))
    _model.eval()


def _last_user_text(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return str(message.content)
    return ""


def _parse_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _tool_call_response(parsed: dict[str, Any]) -> dict[str, Any] | None:
    tool_name = parsed.get("tool") or parsed.get("name")
    arguments = parsed.get("arguments") or parsed.get("args")
    if not tool_name or not isinstance(arguments, dict):
        return None
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": str(tool_name),
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        ],
    }


def _final_reply(messages: list[ChatMessage]) -> str | None:
    for message in reversed(messages):
        if message.role != "tool":
            continue
        try:
            result = json.loads(str(message.content))
            items = result.get("items") or []
            if items:
                first = items[0]
                return f"已为您找到 {len(items)} 件商品，最匹配的是{first.get('item_name', '相关商品')}。"
            return "暂未找到匹配商品，请换一个关键词试试。"
        except (TypeError, json.JSONDecodeError):
            return "已完成商品检索。"
    return None


def _generate(messages: list[ChatMessage], max_tokens: int) -> str:
    assert _tokenizer is not None and _model is not None
    user_text = _last_user_text(messages)
    prompt_messages = [
        {
            "role": "user",
            "content": (
                "把用户需求转换为白名单检索工具调用参数，只输出 JSON。\n"
                "白名单工具：text_search\n\n" + user_text
            ),
        }
    ]
    prompt = _tokenizer.apply_chat_template(
        prompt_messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    inputs = _tokenizer(prompt, return_tensors="pt").to(_model.device)
    with torch.inference_mode():
        output = _model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=False,
            pad_token_id=_tokenizer.pad_token_id or _tokenizer.eos_token_id,
        )
    return _tokenizer.decode(
        output[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
    ).strip()


@app.on_event("startup")
def startup() -> None:
    _load_model()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if _model is not None else "loading",
        "model": MODEL_NAME,
        "base_model": str(BASE_MODEL_PATH),
        "adapter": str(ADAPTER_PATH),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "public_base_url": f"http://{PUBLIC_HOST}:8100/v1",
    }


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "owned_by": "shopvision",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> dict[str, Any]:
    if request.stream:
        raise HTTPException(status_code=400, detail="暂不支持 stream=true")
    if not request.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")
    _load_model()
    async with _generation_lock:
        final_reply = _final_reply(request.messages)
        if final_reply is not None:
            message = {"role": "assistant", "content": final_reply}
        else:
            raw = await asyncio.to_thread(_generate, request.messages, request.max_tokens)
            message = _tool_call_response(_parse_json(raw)) or {
                "role": "assistant",
                "content": raw,
            }

    return {
        "id": f"chatcmpl_{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model or MODEL_NAME,
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("scripts.agent.model_server:app", host="0.0.0.0", port=8100, workers=1)
