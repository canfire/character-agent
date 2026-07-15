"""Relationship 分析器.

从语料中提取角色的关系模式画像（关系族）.
"""

from pathlib import Path

from .llm_utils import call_llm_json


def _load_prompt() -> str:
    path = Path(__file__).parent.parent.parent / "config" / "prompts" / "relationship_analyzer.md"
    return path.read_text(encoding="utf-8")


def analyze_relationship(basic_info: dict, corpus: str) -> dict:
    """分析关系模式.

    Args:
        basic_info: {name, relationship_type, ...}
        corpus: 原始语料文本

    Returns:
        {expression_dna, emotional_triggers, conflict_pattern, memory_signature}
    """
    system_prompt = _load_prompt()

    user_prompt = f"""## 基本信息
- 姓名/称呼: {basic_info.get('name', '')}
- 关系类型: {basic_info.get('relationship_type', '')}

## 原始语料
{corpus}

请根据以上信息提取关系模式画像，严格按 JSON 格式输出。"""

    return call_llm_json(system_prompt, user_prompt, max_tokens=4096)
