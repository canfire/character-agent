"""Mem0 记忆系统核心封装.

提供统一的记忆写入、搜索、管理接口。
支持三层命名空间: user_id / agent_id / run_id.

存储架构:
    {slug}-persona    人格层 (metadata.type: initial | correction)
    {slug}-capability 能力层 (metadata.type: initial | update)
    {slug}-knowledge  知识层 (metadata.type: corpus | conversation | fact)

搜索排序: final_score = similarity × time_decay × type_boost
    time_decay: exp(-0.01 × days_old)
    type_boost: correction=2.0, conversation=1.5, update=1.3, 其余=1.0

配置来源优先级:
  1. 直接传入 Mem0Config
  2. 从 settings.yaml 读取
  3. 从环境变量读取
"""

import math
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from mem0 import Memory

logger = logging.getLogger(__name__)

# 时间衰减系数 (λ=0.01, 约70天半衰)
TIME_DECAY_LAMBDA = 0.01

# 类型加权系数
TYPE_BOOST = {
    "correction": 2.0,
    "conversation": 1.5,
    "update": 1.3,
}


@dataclass
class Mem0Config:
    """Mem0 连接配置."""

    # LLM 配置
    api_key: str = ""
    base_url: str = ""
    memory_model: str = "gpt-4o-mini"
    memory_temperature: float = 0.1
    memory_max_tokens: int = 1024

    # Embedder 配置（可能与 LLM 使用不同的服务和 key）
    embedder_api_key: str = ""
    embedder_base_url: str = ""
    embedder_model: str = "text-embedding-3-small"

    # Qdrant 配置
    vector_store_host: str = "localhost"
    vector_store_port: int = 6333
    collection_name: str = "character_agent"
    embedding_dims: int = 1536

    search_top_k: int = 5
    search_hybrid: bool = True

    @classmethod
    def from_yaml(cls, path: str = None) -> "Mem0Config":
        """从 settings.yaml 读取配置."""
        if path is None:
            path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
        if not Path(path).exists():
            return cls.from_env()

        with open(path) as f:
            data = yaml.safe_load(f)

        llm = data.get("llm", {})
        embedder = data.get("embedder", {})
        qdrant = data.get("qdrant", {})
        search = data.get("search", {})

        return cls(
            api_key=llm.get("api_key", ""),
            base_url=llm.get("base_url", ""),
            memory_model=llm.get("memory_model", "gpt-4o-mini"),
            memory_temperature=llm.get("memory_temperature", 0.1),
            memory_max_tokens=llm.get("memory_max_tokens", 1024),
            embedder_api_key=embedder.get("api_key", llm.get("api_key", "")),
            embedder_base_url=embedder.get("base_url", llm.get("base_url", "")),
            embedder_model=embedder.get("model", "text-embedding-3-small"),
            vector_store_host=qdrant.get("host", "localhost"),
            vector_store_port=qdrant.get("port", 6333),
            collection_name=qdrant.get("collection_name", "character_agent"),
            embedding_dims=qdrant.get("embedding_dims", 1536),
            search_top_k=search.get("top_k", 5),
            search_hybrid=search.get("hybrid", True),
        )

    @classmethod
    def from_env(cls) -> "Mem0Config":
        """从环境变量构建配置."""
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", ""),
            memory_model=os.getenv("MEM0_LLM_MODEL", "gpt-4o-mini"),
            embedder_model=os.getenv("MEM0_EMBEDDER_MODEL", "text-embedding-3-small"),
            vector_store_host=os.getenv("QDRANT_HOST", "localhost"),
            vector_store_port=int(os.getenv("QDRANT_PORT", "6333")),
        )


class Mem0Client:
    """Mem0 记忆系统客户端.

    Usage:
        client = Mem0Client.from_env()
        client.add_interaction(user_id="alice", user_msg="...", assistant_msg="...")
        results = client.search("query", user_id="alice")
    """

    def __init__(self, config: Optional[Mem0Config] = None):
        self.config = config or Mem0Config()
        self._memory = None

    @classmethod
    def from_yaml(cls, path: str = None) -> "Mem0Client":
        """从 settings.yaml 创建客户端."""
        return cls(Mem0Config.from_yaml(path))

    @classmethod
    def from_env(cls) -> "Mem0Client":
        """从环境变量创建客户端."""
        return cls(Mem0Config.from_env())

    @property
    def memory(self) -> Memory:
        """延迟初始化 Mem0 Memory 实例."""
        if self._memory is None:
            c = self.config
            self._memory = Memory.from_config({
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "collection_name": c.collection_name,
                        "host": c.vector_store_host,
                        "port": c.vector_store_port,
                        "embedding_model_dims": c.embedding_dims,
                    },
                },
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": c.memory_model,
                        "temperature": c.memory_temperature,
                        "max_tokens": c.memory_max_tokens,
                        "api_key": c.api_key,
                        "openai_base_url": c.base_url,
                    } if c.api_key and c.base_url else {
                        "model": c.memory_model,
                        "temperature": c.memory_temperature,
                        "max_tokens": c.memory_max_tokens,
                    },
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": c.embedder_model,
                        "api_key": c.embedder_api_key or c.api_key,
                        "openai_base_url": c.embedder_base_url or c.base_url,
                    } if (c.embedder_api_key or c.api_key) and (c.embedder_base_url or c.base_url) else {
                        "model": c.embedder_model,
                    },
                },
            })
            logger.info("Mem0Client initialized: collection=%s host=%s:%s",
                        c.collection_name, c.vector_store_host, c.vector_store_port)
        return self._memory

    # ============ 记忆写入 ============

    def add(
        self,
        messages: list[dict[str, str]],
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        infer: bool = True,
    ) -> dict:
        """写入记忆."""
        return self.memory.add(
            messages,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            metadata=metadata,
            infer=infer,
        )

    def add_persona(self, slug: str, persona_content: str) -> dict:
        """写入人格记忆（切片后逐片 infer=True，减少 DeepSeek JSON 失败概率）."""
        return self._add_chunked(
            persona_content,
            agent_id=f"{slug}-persona",
            metadata={"type": "initial", "agent_slug": slug},
            label=f"persona({slug})",
        )

    def add_capability(self, slug: str, capability_content: str) -> dict:
        """写入能力记忆（切片后逐片 infer=True）."""
        return self._add_chunked(
            capability_content,
            agent_id=f"{slug}-capability",
            metadata={"type": "initial", "agent_slug": slug},
            label=f"capability({slug})",
        )

    def add_knowledge(self, slug: str, corpus: str, metadata: dict = None) -> dict:
        """写入知识记忆（切片后逐片 infer=True）."""
        return self._add_chunked(
            corpus,
            agent_id=f"{slug}-knowledge",
            metadata={"type": "corpus", "agent_slug": slug, **(metadata or {})},
            label=f"knowledge({slug})",
        )

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 800) -> list[str]:
        """按双换行分块，单段超长时按单换行再切."""
        sections = [s.strip() for s in text.split("\n\n") if s.strip()]
        chunks = []
        for section in sections:
            if len(section) <= max_chars:
                chunks.append(section)
            else:
                current = ""
                for line in section.split("\n"):
                    if len(current) + len(line) > max_chars and current:
                        chunks.append(current.strip())
                        current = line + "\n"
                    else:
                        current += line + "\n"
                if current.strip():
                    chunks.append(current.strip())
        return [c for c in chunks if len(c) > 20]

    def _add_chunked(
        self, content: str, *, agent_id: str, metadata: dict, label: str = ""
    ) -> dict:
        """切片后逐片写入，每片重试 2 次，失败 fallback 到 infer=False."""
        chunks = self._chunk_text(content)
        if not chunks:
            chunks = [content]
        logger.info(f"[{label}] 切为 {len(chunks)} 块，逐块 infer=True...")
        all_results = []
        for i, chunk in enumerate(chunks):
            r = self._add_with_retry(
                chunk,
                agent_id=agent_id,
                metadata=metadata,
                label=f"{label}#{i+1}/{len(chunks)}",
                max_retries=2,
            )
            all_results.extend(r.get("results", []))
        logger.info(f"[{label}] 完成: {len(all_results)} 条记忆")
        return {"results": all_results}

    def _add_with_retry(
        self, content: str, *, agent_id: str, metadata: dict, label: str = "", max_retries: int = 5
    ) -> dict:
        """带重试的记忆写入，解决 DeepSeek/v4-pro JSON 输出不稳定的问题."""
        for attempt in range(1, max_retries + 1):
            try:
                result = self.memory.add(
                    content,
                    agent_id=agent_id,
                    metadata=metadata,
                    infer=True,
                )
            except Exception as e:
                logger.warning(f"[{label}] 第 {attempt} 次写入 LLM 调用异常: {e}")
                if attempt < max_retries:
                    continue
                raise

            if result.get("results"):
                if attempt > 1:
                    logger.info(f"[{label}] 第 {attempt} 次重试成功，写入 {len(result['results'])} 条")
                return result

            logger.warning(f"[{label}] 第 {attempt} 次写入返回空（JSON 解析失败），重试中...")

        logger.error(f"[{label}] 重试 {max_retries} 次后仍为空，fallback 到 infer=False 原样存储")
        return self.memory.add(
            content,
            agent_id=agent_id,
            metadata=metadata,
            infer=False,
        )

    def add_memory(
        self,
        slug: str,
        content: str,
        category: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """统一写入入口，按 category 路由到不同 agent_id.

        Args:
            slug: 角色标识
            content: 要存储的内容
            category: "persona" | "capability" | "knowledge"
            metadata: 额外元数据
        """
        type_default = {
            "persona": "correction",
            "capability": "update",
            "knowledge": "conversation",
        }
        type_value = (metadata or {}).get("type") or type_default.get(category, "conversation")

        return self.memory.add(
            content,
            agent_id=f"{slug}-{category}",
            metadata={"type": type_value, "agent_slug": slug, **(metadata or {})},
            infer=False,
        )

    def add_interaction(
        self,
        user_msg: str,
        assistant_msg: str,
        *,
        slug: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """保存一次对话交互到知识层（infer=False 避免中文被转译）."""
        target_agent_id = agent_id or (f"{slug}-knowledge" if slug else None)
        return self.memory.add(
            [
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ],
            user_id=user_id,
            agent_id=target_agent_id,
            run_id=run_id,
            metadata={"type": "conversation", **(metadata or {})},
            infer=False,
        )

    # ============ 记忆检索 ============

    def search(
        self,
        query: str,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        top_k: Optional[int] = None,
        threshold: float = 0.1,
        filters: Optional[dict] = None,
    ) -> dict[str, Any]:
        """原始语义搜索（不加权）."""
        search_filters = _build_filters(user_id, agent_id, run_id)
        if filters:
            search_filters = _merge_filters(search_filters, filters)

        return self.memory.search(
            query,
            top_k=top_k or self.config.search_top_k,
            filters=search_filters,
            threshold=threshold,
        )

    def search_with_temporal_weight(
        self,
        query: str,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        top_k: Optional[int] = None,
        threshold: float = 0.1,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """搜索记忆 + 时间衰减 + 类型加权.

        先从 Qdrant 取 top_k × 3 条结果，重新计算 final_score 后排序返回 top_k 条.

        final_score = similarity_score × time_decay × type_boost

        Returns:
            排序后的结果列表 [{"memory": ..., "score": ..., "final_score": ..., ...}]
        """
        fetch_count = (top_k or self.config.search_top_k) * 3
        result = self.search(
            query,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            top_k=fetch_count,
            threshold=threshold,
            filters=filters,
        )

        items = result.get("results", [])
        if not items:
            return []

        now = datetime.now(timezone.utc)
        scored = []
        for item in items:
            sim = item.get("score", 0)

            created_str = item.get("created_at")
            days_old = 0
            if created_str:
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    days_old = (now - created).days
                except (ValueError, TypeError):
                    pass
            time_weight = math.exp(-TIME_DECAY_LAMBDA * days_old)

            mem_type = (item.get("metadata") or {}).get("type", "")
            type_weight = TYPE_BOOST.get(mem_type, 1.0)

            final_score = sim * time_weight * type_weight
            item["final_score"] = final_score
            scored.append(item)

        scored.sort(key=lambda x: x["final_score"], reverse=True)
        return scored[: (top_k or self.config.search_top_k)]

    def search_memories(
        self,
        query: str,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        top_k: Optional[int] = None,
        threshold: float = 0.1,
    ) -> list[str]:
        """便捷方法: 搜索并返回记忆文本列表（加权）."""
        result = self.search_with_temporal_weight(
            query,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            top_k=top_k,
            threshold=threshold,
        )
        return [item["memory"] for item in result]

    def search_context(
        self,
        query: str,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> str:
        """便捷方法: 搜索并返回拼接好的上下文文本."""
        memories = self.search_memories(
            query, user_id=user_id, agent_id=agent_id, top_k=top_k,
        )
        if not memories:
            return ""
        return "\n".join(f"- {m}" for m in memories)

    # ============ 记忆管理 ============

    def get_all(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> dict:
        """获取所有记忆."""
        filters = _build_filters(user_id, agent_id, run_id)
        return self.memory.get_all(filters=filters)

    def update(self, memory_id: str, data: str) -> dict:
        """更新指定记忆."""
        return self.memory.update(memory_id, data)

    def delete(self, memory_id: str) -> dict:
        """删除指定记忆."""
        return self.memory.delete(memory_id)


# ============ 过滤条件构建 ============

def _build_filters(
    user_id: Optional[str],
    agent_id: Optional[str],
    run_id: Optional[str],
) -> dict:
    """构建 Mem0 过滤条件字典."""
    filters = {}
    if user_id:
        filters["user_id"] = user_id
    if agent_id:
        filters["agent_id"] = agent_id
    if run_id:
        filters["run_id"] = run_id
    return filters


def _merge_filters(base: dict, extra: dict) -> dict:
    """合并过滤条件."""
    result = base.copy()
    for key, value in extra.items():
        if key in result:
            result["AND"] = [{key: result[key]}, {key: value}]
        else:
            result[key] = value
    return result
