"""Persona 分析器.

从语料和标签中提取 6 层人格结构.
"""

from pathlib import Path

from .llm_utils import call_llm_json


def _load_prompt() -> str:
    path = Path(__file__).parent.parent.parent / "config" / "prompts" / "persona_analyzer.md"
    return path.read_text(encoding="utf-8")


def analyze_persona(
    basic_info: dict,
    tags: list[str],
    corpus: str,
) -> dict:
    """分析人格，返回 6 层结构 dict.

    Args:
        basic_info: {name, company, level, role, mbti, gender, ...}
        tags: ["甩锅高手", "字节范", ...]
        corpus: 原始语料文本

    Returns:
        {layer_0: [...], layer_1: {...}, layer_2: {...}, ...}
    """
    system_prompt = _load_prompt()

    user_prompt = f"""## 基本信息
{_format_dict(basic_info)}

## 个性标签
{", ".join(tags) if tags else "（无标签）"}

## 原始语料
{corpus}

请根据以上信息提取 6 层人格结构，严格按 JSON 格式输出。"""

    return call_llm_json(system_prompt, user_prompt, max_tokens=4096)


def _format_dict(d: dict) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in d.items() if v)
