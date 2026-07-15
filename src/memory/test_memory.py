"""Memory 层基础功能测试脚本.

Usage:
    source ~/miniconda3/etc/profile.d/conda.sh && conda activate cagent
    python -m memory.test_memory
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from memory.mem0_client import Mem0Client

TEST_USER = "test_user"


def test_init():
    print("=== 1. 从 config/settings.yaml 初始化 ===")
    client = Mem0Client.from_yaml()
    c = client.config
    print(f"  LLM model: {c.memory_model}")
    print(f"  LLM base_url: {c.base_url}")
    print(f"  Embedder model: {c.embedder_model}")
    print(f"  Embedder base_url: {c.embedder_base_url}")
    print()
    return client


def test_add_memory(client):
    print("=== 2. 测试写入交互记忆 ===")
    result = client.add(
        messages=[
            {"role": "user", "content": "我喜欢喝黑咖啡，不加糖"},
            {"role": "assistant", "content": "记住了，你喜欢纯黑咖啡"},
        ],
        user_id=TEST_USER,
    )
    for r in result.get("results", []):
        print(f"  [{r['event']}] {r['memory']}")
    print()
    return result


def test_search(client):
    print("=== 3. 测试搜索记忆 ===")
    result = client.search("喝什么", user_id=TEST_USER)
    for m in result.get("results", []):
        print(f"  [{m.get('score', 0):.3f}] {m.get('memory', '')}")
    print()
    return result


def test_get_all(client):
    print("=== 4. 测试获取全部记忆 ===")
    result = client.get_all(user_id=TEST_USER)
    count = len(result.get("results", []))
    print(f"  共 {count} 条记忆")
    print()
    return result


def test_add_interaction(client):
    print("=== 5. 测试 add_interaction 便捷方法 ===")
    client.add_interaction(
        user_msg="我叫张三，是后端工程师",
        assistant_msg="你好张三，记住了你的职业",
        user_id=TEST_USER,
    )
    print("  写入成功")
    print()


def test_search_context(client):
    print("=== 6. 测试 search_context 便捷方法 ===")
    context = client.search_context("职业", user_id=TEST_USER)
    print(f"  {context}")
    print()


def test_add_persona(client):
    print("=== 7. 测试写入 Persona 记忆 ===")
    persona = """## Layer 0: 核心性格
- 被人质疑时反问"你的判断依据是什么"
- 开会前先对齐 context

## Layer 1: 身份
- 张三，字节跳动，2-1 后端工程师，INTJ"""
    client.add_persona("zhang-san", persona)
    print("  写入成功")
    print()


def test_add_work(client):
    print("=== 8. 测试写入 Work 记忆 ===")
    work = "技术栈: Go、Python、Redis、Kafka\n职责: 用户增长后台"
    client.add_work("zhang-san", work)
    print("  写入成功")
    print()


def test_add_tool(client):
    print("=== 9. 测试写入 Tool 记忆 ===")
    client.add_tool_memory(
        "zhang-san", "code_review", "审查代码质量和安全性，检查并发安全、数据库索引、错误处理"
    )
    client.add_tool_memory(
        "zhang-san", "bash", "执行 shell 命令，用于构建、测试、部署等操作"
    )
    print("  写入成功")
    print()


def test_search_persona(client):
    print("=== 10. 测试搜索 Persona 记忆 ===")
    result = client.search("质疑时怎么回应", agent_id="zhang-san-persona")
    for m in result.get("results", []):
        print(f"  [{m.get('score', 0):.3f}] {m.get('memory', '')}")
    print()


def test_search_tools(client):
    print("=== 11. 测试搜索 Tool 记忆 ===")
    result = client.search("代码审查", agent_id="zhang-san-tools")
    for m in result.get("results", []):
        print(f"  [{m.get('score', 0):.3f}] {m.get('memory', '')}")
    print()


def main():
    client = test_init()
    test_add_memory(client)
    test_search(client)
    test_get_all(client)
    test_add_interaction(client)
    test_search_context(client)
    test_add_persona(client)
    test_add_work(client)
    test_add_tool(client)
    test_search_persona(client)
    test_search_tools(client)
    print("=== 全部测试通过 ===")


if __name__ == "__main__":
    main()
