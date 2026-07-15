"""Character-Agent MCP Server.

通过 streamable-http 协议暴露角色记忆检索和写入工具。
部署后可被任意 opencode 实例通过 type: "remote" MCP 连接调用。

启动方式:
    python mcp_server.py --host 0.0.0.0 --port 8765

opencode 配置:
    {
      "mcp": {
        "character-tools": {
          "type": "remote",
          "url": "http://localhost:8765/mcp",
          "enabled": true
        }
      }
    }
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent / "src"))

from memory.mem0_client import Mem0Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("character-mcp")

_client: Optional[Mem0Client] = None
_SEARCH_TOP_K = 20  # 每次搜索返回的记忆数量


def _get_client() -> Mem0Client:
    global _client
    if _client is None:
        _client = Mem0Client.from_yaml()
        logger.info("Mem0Client 已初始化: collection=%s host=%s:%s",
                     _client.config.collection_name,
                     _client.config.vector_store_host,
                     _client.config.vector_store_port)
    return _client


def _format_results(results: list[dict]) -> str:
    if not results:
        return "(未找到相关记忆)"
    lines = []
    for i, item in enumerate(results):
        score = item.get("final_score") or item.get("score", 0)
        memory = item.get("memory", "")
        metadata = item.get("metadata", {})
        mem_type = metadata.get("type", "")
        source = f" [{mem_type}]" if mem_type else ""
        created = item.get("created_at", "")
        time_info = f" {created[:10]}" if created else ""
        lines.append(f"{i + 1}. (score={score:.3f}){source}{time_info} {memory}")
    return "\n".join(lines)


# ============ 查询类工具 ============

def search_persona_memory(query: str, slug: str) -> str:
    """搜索角色人格记忆（时间加权排序）."""
    client = _get_client()
    results = client.search_with_temporal_weight(
        query, agent_id=f"{slug}-persona", top_k=_SEARCH_TOP_K,
    )
    return _format_results(results)


def search_capability_memory(query: str, slug: str) -> str:
    """搜索角色能力记忆（时间加权排序）."""
    client = _get_client()
    results = client.search_with_temporal_weight(
        query, agent_id=f"{slug}-capability", top_k=_SEARCH_TOP_K,
    )
    return _format_results(results)


def search_knowledge_memory(query: str, slug: str) -> str:
    """搜索角色知识记忆（时间加权排序）."""
    client = _get_client()
    results = client.search_with_temporal_weight(
        query, agent_id=f"{slug}-knowledge", top_k=_SEARCH_TOP_K,
    )
    return _format_results(results)


def search_all_memory(query: str, slug: str) -> str:
    """跨人格+能力+知识三层综合搜索，时间加权合并排序."""
    client = _get_client()

    all_results = []
    seen_ids = set()

    for layer in ["-persona", "-capability", "-knowledge"]:
        results = client.search_with_temporal_weight(
            query, agent_id=f"{slug}{layer}", top_k=_SEARCH_TOP_K,
        )
        for item in results:
            mem_id = item.get("id", "")
            if mem_id not in seen_ids:
                seen_ids.add(mem_id)
                all_results.append(item)

    all_results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    return _format_results(all_results[:_SEARCH_TOP_K])


# ============ 写入类工具 ============

def add_memory(content: str, slug: str, category: str) -> str:
    """统一写入入口，按 category 路由到不同记忆层.

    Args:
        content: 要存储的内容
        slug: 角色标识
        category: "persona" | "capability" | "knowledge"

    category 选择规则:
        - persona: 性格特征、表达风格、决策模式、雷区偏好
        - capability: 技术能力、工作流程、规范标准、专业经验
        - knowledge: 事实信息、对话摘要、事件记录、背景知识
        分不清时默认用 knowledge.
    """
    client = _get_client()
    valid = {"persona", "capability", "knowledge"}
    if category not in valid:
        return f"无效的 category: {category}，可选值: {', '.join(sorted(valid))}"

    client.add_memory(slug, content, category)
    return f"已写入 {category} 层记忆到角色 {slug}"


# ============ 工具注册表 ============

TOOLS = [
    {
        "fn": search_persona_memory,
        "name": "search_persona_memory",
        "description": "搜索角色的人格记忆（性格特征、表达风格、决策模式、人际行为、边界雷区）。语义搜索 + 时间加权，越新越重要的记忆排名越靠前。每次对话开始时必须调用。",
    },
    {
        "fn": search_capability_memory,
        "name": "search_capability_memory",
        "description": "搜索角色的能力记忆（技术栈、规范标准、工作流程、CR重点、经验知识库）。语义搜索 + 时间加权。处理技术任务前必须调用。",
    },
    {
        "fn": search_knowledge_memory,
        "name": "search_knowledge_memory",
        "description": "搜索角色的知识记忆（原始语料、对话历史、事实信息、事件记录）。语义搜索 + 时间加权。需要了解角色过往经历或对话上下文时调用。",
    },
    {
        "fn": search_all_memory,
        "name": "search_all_memory",
        "description": "综合搜索所有记忆（人格+能力+知识），跨三层合并去重并按时间加权排序。处理需要全面了解角色背景的查询时使用。",
    },
    {
        "fn": add_memory,
        "name": "add_memory",
        "description": "统一写入入口。按 category 路由到不同记忆层: persona(性格/风格/决策), capability(技术/规范/流程), knowledge(事实/对话/事件)。分不清时默认用 knowledge。",
    },
]


def register_tools(mcp_instance: FastMCP) -> None:
    """将所有工具注册到 MCP 实例."""
    for tool_def in TOOLS:
        mcp_instance.add_tool(
            fn=tool_def["fn"],
            name=tool_def["name"],
            description=tool_def["description"],
        )
    logger.info("已注册 %d 个 MCP 工具", len(TOOLS))


# ============ 入口 ============

def main():
    parser = argparse.ArgumentParser(description="Character-Agent MCP Server")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    args = parser.parse_args()

    mcp = FastMCP(
        "character-tools",
        instructions="角色蒸馏记忆系统 MCP Server",
        host=args.host,
        port=args.port,
    )

    register_tools(mcp)

    logger.info("启动 Character-Agent MCP Server: %s:%s", args.host, args.port)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
