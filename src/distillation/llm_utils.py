"""LLM 调用工具.

从 config/settings.yaml 读取配置，提供统一的 OpenAI 兼容 API 调用接口。
支持普通对话和 JSON 结构化输出两种模式。
"""

import json
import logging
from pathlib import Path
from typing import Optional

import yaml
from openai import OpenAI

logger = logging.getLogger(__name__)


def _load_llm_config():
    """从 settings.yaml 加载 LLM 配置."""
    config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    llm = data.get("llm", {})
    return {
        "api_key": llm.get("api_key", ""),
        "base_url": llm.get("base_url", ""),
        "model": llm.get("memory_model", "gpt-4o-mini"),
        "temperature": llm.get("memory_temperature", 0.1),
        "max_tokens": llm.get("memory_max_tokens", 4096),
    }


_config = None
_client = None


def _get_client() -> OpenAI:
    global _config, _client
    if _client is None:
        _config = _load_llm_config()
        _client = OpenAI(api_key=_config["api_key"], base_url=_config["base_url"])
        logger.info("LLM client initialized: model=%s base_url=%s",
                     _config["model"], _config["base_url"])
    return _client


def call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    json_mode: bool = False,
) -> str:
    """调用 LLM.

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户输入
        temperature: 温度（None 则用配置默认值）
        max_tokens: 最大输出 token（None 则用配置默认值）
        json_mode: 是否要求 LLM 输出纯 JSON

    Returns:
        LLM 返回的文本
    """
    config = _load_llm_config()
    client = _get_client()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    kwargs = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature if temperature is not None else config["temperature"],
        "max_tokens": max_tokens if max_tokens is not None else config["max_tokens"],
    }

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    logger.debug("Calling LLM: model=%s messages_len=%s json_mode=%s",
                 config["model"], len(user_prompt), json_mode)

    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content
    return content


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> dict:
    """调用 LLM 并解析为 JSON dict."""
    result = call_llm(
        system_prompt, user_prompt,
        temperature=temperature, max_tokens=max_tokens,
        json_mode=True,
    )
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()
        return json.loads(result)


def get_agent_config() -> dict:
    """获取 Agent 对话的模型配置（使用 settings.yaml 中 agent 段）."""
    config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    llm = data.get("llm", {})
    agent = data.get("agent", {})
    return {
        "api_key": llm.get("api_key", ""),
        "base_url": llm.get("base_url", ""),
        "model": agent.get("model", llm.get("memory_model", "gpt-4o-mini")),
        "temperature": agent.get("temperature", 0.7),
        "max_tokens": agent.get("max_tokens", 4096),
    }
