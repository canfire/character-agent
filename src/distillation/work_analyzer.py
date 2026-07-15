"""Work 分析器.

从语料中提取角色工作能力画像（同事族）.
"""

from pathlib import Path

from .llm_utils import call_llm_json


def _load_prompt() -> str:
    path = Path(__file__).parent.parent.parent / "config" / "prompts" / "work_analyzer.md"
    return path.read_text(encoding="utf-8")


def analyze_work(basic_info: dict, corpus: str) -> dict:
    """分析工作能力.

    Args:
        basic_info: {name, company, level, role, ...}
        corpus: 原始语料文本

    Returns:
        {scope, tech_spec, workflow, output_style, knowledge}
    """
    system_prompt = _load_prompt()

    user_prompt = f"""## 基本信息
- 姓名: {basic_info.get('name', '')}
- 公司: {basic_info.get('company', '')}
- 职级: {basic_info.get('level', '')}
- 职位: {basic_info.get('role', '')}

## 原始语料
{corpus}

请根据以上信息提取工作能力画像，严格按 JSON 格式输出。"""

    return call_llm_json(system_prompt, user_prompt, max_tokens=4096)
