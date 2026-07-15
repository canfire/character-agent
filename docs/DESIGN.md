# Character-Agent 技术方案设计

> 从人的语料中蒸馏角色，生成 opencode 原生 Agent
> 蒸馏引擎处理"人格提取"，opencode 处理"Agent 运行时"，MCP Server 提供"记忆检索"

---

## 一、项目背景与动机

### 1.1 问题

现有的人格蒸馏方案（如 dot-skill）生成的是**静态 Skill**——只能一问一答，没有记忆、没有工具调用、不具备自主规划能力。

如果要将蒸馏角色变成真正的 Agent，需要解决三个问题：

1. **运行时**：Agent 需要能自主规划任务、调用工具（shell/文件读写/网络请求等）
2. **记忆**：Agent 需要长期记忆系统，在对话间保持角色一致性
3. **集成**：蒸馏产物需要能被 Agent 运行时消费

### 1.2 方案选择

我们评估了两种架构：

| 方案 | 做法 | 优劣 |
|------|------|------|
| A. 自建 Python runtime | 完整复刻 opencode 的 Agent 循环（ReAct、工具注册、会话管理、权限、TUI 等） | 重复造轮子，代码量巨大，无法享受 opencode 生态的持续更新 |
| B. 蒸馏引擎 + opencode 集成 | distillation 只做蒸馏，opencode 承担所有运行时职责，MCP Server 提供记忆检索 | 每种技术各司其职，轻量高效 |

**最终选择方案 B**。

### 1.3 架构思路

```
Character-Agent 不"运行" Agent。
Character-Agent 只"生成" Agent 的定义文件，并在后端提供记忆检索服务。
Agent 的实际运行由 opencode 完成。

┌──────────────────────────────────────────────────────────────┐
│                     Character-Agent                           │
│                                                              │
│   ┌─────────────────────┐    ┌──────────────────────────┐   │
│   │   蒸馏引擎 (Python)   │    │   MCP Server (Python)     │   │
│   │                     │    │                          │   │
│   │  语料 → LLM → persona│    │  HTTP/SSE → opencode     │   │
│   │  语料 → LLM → work  │    │  search_persona_memory   │   │
│   │  → agent.md         │    │  search_work_memory      │   │
│   │  → Mem0 初始记忆     │    │  search_knowledge_memory │   │
│   └─────────┬───────────┘    │  add_*_memory            │   │
│             │                └────────────┬─────────────┘   │
│             │                             │                  │
│             ▼                             ▼                  │
│   ┌─────────────────────────────────────────────────────┐   │
│   │              Mem0 + Qdrant                           │   │
│   │  agent_id: "{slug}-persona"  ← 人格向量              │   │
│   │  agent_id: "{slug}-work"     ← 工作能力向量           │   │
│   │  agent_id: "{slug}-knowledge" ← 原始语料向量           │   │
│   │  agent_id: "{slug}"          ← 对话交互记录           │   │
│   └─────────────────────────────────────────────────────┘   │
└──────────────────────────┬───────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
    ┌──────────────────┐    ┌──────────────────────┐
    │  agent.md         │    │  opencode.jsonc      │
    │  (.opencode/      │    │  {                   │
    │   agent/          │    │    "mcp": {          │
    │   zhang-san.md)   │    │      "character-     │
    │                   │    │       tools": {...}   │
    │   frontmatter:    │    │    }                 │
    │     mode: primary │    │  }                   │
    │     description   │    └──────────────────────┘
    │                   │              │
    │   body:           │              │
    │     角色简介      │              │ MCP 工具
    │     slug 标识     │              │
    │     记忆检索规范  │              │
    └──────────────────┘              │
              │                       │
              └───────────┬───────────┘
                          ▼
                ┌──────────────────┐
                │     opencode      │
                │                   │
                │  带张三人设的      │
                │  完整 Agent        │
                │  (bash/read/edit  │
                │   + MCP 记忆检索) │
                └──────────────────┘
```

---

## 二、蒸馏引擎

### 2.1 核心流程

```
python -m distillation.intake --family colleague

Step 1: 交互式信息采集
  → 姓名/花名、公司、职级、职位、MBTI、性别
  → 个性标签（逗号分隔）
  → 主观印象/描述
  → 原始语料（文件路径或直接粘贴）

Step 2: LLM 分析
  → persona_analyzer.py: 从语料提取 6 层人格结构（JSON 模式）
  → work_analyzer.py: 从语料提取工作能力画像（JSON 模式）
  → [relationship_analyzer.py]: 关系族专用，提取关系模式

Step 3: 生成产物
  → persona.md    — LLM 分析结果的 Markdown 格式（可编辑素材）
  → work.md       — LLM 分析结果的 Markdown 格式（可编辑素材）
  → meta.json     — 角色元数据（名称/slug/tags/时间戳）
  → agent.md      — ★ opencode 原生 agent 文件（frontmatter + system prompt）
  → Mem0          — 将 persona/work/knowledge 写入 Qdrant 向量数据库
```

### 2.2 六层人格结构

| 层 | 定义 | 示例 |
|----|------|------|
| **Layer 0** | 核心性格（最高优先级） | "开口必讲impact和context"，"决策必须有数据支撑" |
| **Layer 1** | 身份信息 | 姓名、公司、职级、职位、MBTI |
| **Layer 2** | 表达风格 | 口头禅、句式特征、Emoji 习惯、回复示例 |
| **Layer 3** | 决策与判断 | 优先级排序、推进/推掉条件、说不方式 |
| **Layer 4** | 人际行为 | 对上级/下级/平级的行为模式、压力反应 |
| **Layer 5** | 边界与雷区 | 禁忌话题、回避方式、拒绝风格 |

### 2.3 两种 Family

| Family | 入口 | 分析器 | 产物 |
|--------|------|--------|------|
| **colleague** | `intake.py --family colleague` | persona_analyzer + work_analyzer | persona.md (人格) + work.md (工作能力) |
| **relationship** | `intake.py --family relationship` | persona_analyzer + relationship_analyzer | persona.md (人格) + work.md (关系模式) |

### 2.4 agent.md 生成策略

agent.md 的 body **不嵌入 persona/work 的完整文本**，而是注入：

1. **角色基本信息**（姓名、公司、职级、标签、slug）
2. **MCP 工具列表和使用规范**（强制要求 agent 通过 MCP 检索记忆）
3. **搜索策略指南**（何时搜、怎么搜、搜什么维度）

角色的人格和工作能力全部存储在 Qdrant 中，agent 通过 MCP Server 按需检索。这样：
- agent.md 保持轻量（约 50 行）
- 角色记忆可以在线动态更新（通过 add_correction_memory 工具）
- 多个角色共享同一个 MCP Server，通过 slug 参数隔离

### 2.5 素材编辑与重生成

蒸馏产物的 persona.md 和 work.md 保留为**可编辑素材**。用户编辑后运行：

```bash
python scripts/regenerate.py --slug zhang-san --family colleague
```

regenerate.py 读取已编辑的 persona.md + work.md + meta.json，调用 `build_agent_md()` 重新融合为 agent.md。

---

## 三、MCP Server

### 3.1 设计目标

MCP Server 是蒸馏角色和 opencode Agent 之间的**记忆桥梁**：

- **语言无关**：Python 编写，可复用蒸馏引擎的所有代码
- **独立部署**：HTTP 服务，本地开发通过 `localhost`，生产环境可独立部署
- **多角色共享**：一个 MCP Server 服务多个角色的记忆检索，通过 slug 参数隔离
- **协议标准**：MCP streamable-http 协议，与 opencode 原生兼容

### 3.2 技术选择

| 方案 | 说明 | 选择 |
|------|------|:--:|
| stdio MCP | opencode spawn 子进程，通过 stdin/stdout JSON-RPC 通信 | ❌ 生产环境部署不便 |
| **HTTP MCP** | 独立 HTTP 服务，通过 streamable-http 协议连接 | ✅ |
| Plugin | opencode 内嵌 TypeScript 代码 | ❌ 不能复用 Python 生态 |

### 3.3 连接流程

```
opencode 启动
  │
  ├─ 读取 opencode.jsonc → mcp.character-tools
  │
  ├─ HTTP POST http://localhost:8765/mcp (initialize)
  ├─ HTTP POST http://localhost:8765/mcp (tools/list)
  │   ← 返回: search_persona_memory, search_work_memory, ...
  │
  └─ Agent 调用工具时:
      ├─ POST /mcp {"method": "tools/call", "params": {"name": "search_persona_memory", "arguments": {...}}}
      ├─ MCP Server:
      │   1. 接收请求
      │   2. Mem0Client.search(query, agent_id="{slug}-persona")
      │   3. Qdrant 向量搜索
      │   4. 返回格式化结果
      └─ → opencode 将结果返回给 Agent
```

### 3.4 工具清单

#### 查询类

| 工具 | description | 典型使用场景 |
|------|------------|-------------|
| `search_persona_memory` | 语义搜索人格画像 | 首次对话检索性格特征；判断决策模式 |
| `search_work_memory` | 语义搜索工作能力 | 技术任务前检索技术栈/规范/流程 |
| `search_knowledge_memory` | 语义搜索原始语料 | 需要从聊天记录/文档中找特定信息 |
| `search_all_memory` | 跨三类记忆综合搜索 | 综合了解角色背景 |

#### 写入类

| 工具 | description | 典型使用场景 |
|------|------------|-------------|
| `add_conversation_memory` | 记录对话交互到长期记忆 | 对话结束后积累交互历史 |
| `add_correction_memory` | 添加/更正人设记忆 | 用户纠正角色表述时修正 |

### 3.5 记忆隔离策略

每种记忆使用不同的 `agent_id` 命名空间：

| 记忆类型 | agent_id | metadata |
|---------|----------|----------|
| 人格记忆 | `{slug}-persona` | `{"type": "persona"}` |
| 工作记忆 | `{slug}-work` | `{"type": "work"}` |
| 原始语料 | `{slug}-knowledge` | `{"type": "knowledge"}` |
| 对话交互 | `{slug}` | （由 Mem0 infer 自动提取） |
| 人格修正 | `{slug}-persona` | `{"type": "correction"}` |

所有数据存储在同一个 Qdrant collection 中，通过 `agent_id` filter 实现角色隔离。

### 3.6 部署配置

**本地开发**：

```bash
python mcp_server.py --host 0.0.0.0 --port 8765
```

**opencode 配置**：

```jsonc
{
  "mcp": {
    "character-tools": {
      "type": "remote",
      "url": "http://localhost:8765/mcp",
      "enabled": true
    }
  }
}
```

**生产部署**：

```bash
# 修改 config/settings.yaml 中的 qdrant.host 指向生产 Qdrant
# 使用 systemd/supervisor 管理进程
python mcp_server.py --host 0.0.0.0 --port 8765
```

---

## 四、Agent 行为规范

### 4.1 System Prompt 结构

`build_agent_md()` 生成的 agent.md body 包含以下结构：

1. **角色身份声明** — "你是 {name} 的蒸馏克隆体，完整人格存储于远程记忆数据库"
2. **基本信息** — 姓名、公司、职级、MBTI、标签、slug
3. **MCP 工具列表** — 6 个工具的名称和用途
4. **强制规则** — 8 条记忆检索规则
5. **搜索策略** — 每次任务至少搜索 2-3 次，不同维度用不同关键词

### 4.2 强制规则详解

| 规则 | 目的 |
|------|------|
| 首次对话先搜索人格记忆 | 确保 agent 表现出正确的人设 |
| 技术任务前搜索工作记忆 | 确保技术决策符合角色规范 |
| 判断决策前搜综合记忆 | 确保决策考虑了角色的完整背景 |
| 回复风格匹配记忆 | 确保语言风格一致性 |
| 技术决策符合记忆 | 确保技术选型符合角色的经验知识 |
| 不编造角色特征 | 防幻觉，以检索到的记忆为准 |
| 对话结束后记录交互 | 积累长期记忆 |
| 被纠正时添加修正 | 持续进化 |

---

## 五、记忆系统

### 5.1 Mem0 架构

```
Mem0Client (mem0_client.py)
│
├─ mem0.Memory
│   ├─ vector_store: Qdrant (localhost:6333)
│   ├─ llm: OpenAI 兼容 API (记忆提取/推理)
│   └─ embedder: Qwen3-Embedding-0.6B (向量化)
│
├─ 写入方法
│   ├── add(messages)          — 通用写入（自动 LLM 推理提取关键事实）
│   ├── add_interaction()      — 便捷方法：保存对话交互
│   ├── add_persona(slug)      — 写入人格记忆（infer=False，原样存储）
│   ├── add_work(slug)         — 写入工作记忆
│   └── add_knowledge(slug)    — 写入原始语料
│
└─ 检索方法
    ├── search(query, ...)     — 语义搜索（向量 + 关键词混合）
    ├── search_memories()      — 返回记忆文本列表
    └── search_context()       — 返回拼接好的上下文文本
```

### 5.2 记忆写入时机

| 时机 | 写入方法 | 数据 |
|------|---------|------|
| 蒸馏完成 | `add_persona` `add_work` `add_knowledge` | persona.md / work.md / 原始语料 |
| 对话结束 | `add_interaction` | 用户消息 + agent 回复 |
| 人设纠正 | `add(metadata={"type": "correction"})` | 纠正文本 |

### 5.3 混合搜索

Mem0 支持混合搜索（`search: { hybrid: true }`），同时使用：

- **语义搜索**：通过 Qwen3-Embedding 将查询向量化，在 Qdrant 中余弦相似度搜索
- **关键词搜索**：BM25 稀疏向量搜索，对精确术语匹配更友好

两种结果的分数加权合并，返回 top_k 条结果。

---

## 六、技术选型

### 6.1 核心依赖

| 模块 | 包 | 版本 | 用途 |
|------|----|----|------|
| 记忆系统 | mem0ai | latest | 记忆管理框架（Qdrant + LLM + Embedder 集成） |
| LLM | openai | latest | 蒸馏分析 + MCP 记忆搜索 |
| MCP Server | mcp | latest | streamable-http 协议服务 |
| 向量存储 | qdrant-client | latest | Qdrant HTTP 客户端 |
| 配置 | pyyaml | latest | settings.yaml 解析 |
| HTTP | httpx | latest | HTTP 客户端 |

### 6.2 基础设施

| 模块 | 技术 | 说明 |
|------|------|------|
| Agent 运行时 | opencode (TypeScript + Bun) | 所有 ReAct 循环、工具执行、会话管理 |
| 蒸馏引擎 | Python 3.12 | LLM 分析 + 产物生成 |
| MCP Server | Python 3.12 + MCP SDK | 记忆检索 HTTP 服务 |
| 向量数据库 | Qdrant (Docker) | 自托管，数据持久化在 `data/qdrant/` |
| 嵌入模型 | Qwen3-Embedding-0.6B | OpenAI 兼容 API，1024 维 |

### 6.3 关键设计决策

| 决定 | 原因 |
|------|------|
| **不嵌入 persona/work 全文到 agent.md** | 1. 减少 agent.md 体积 2. 记忆可在线动态更新 3. 多角色共享 MCP |
| **MCP Server 用 HTTP 不用 stdio** | 1. 独立部署 2. 生产环境可用 3. 多个 opencode 实例可共享 |
| **蒸馏产物保留 persona.md / work.md** | 1. LLM 分析结果可供人工审核 2. 编辑后可通过 regenerate.py 重新生成 agent.md |
| **所有角色数据存入同一 Qdrant collection** | 1. 简化运维 2. agent_id filter 天然隔离 3. 未来可做跨角色检索 |

---

## 七、后续计划

- [ ] **多维度知识写入**：支持 role-specific 知识（邮箱、日程、偏好等结构化信息）
- [ ] **MCP 工具扩展**：语义聚合总结（压缩记忆、提取摘要）、跨角色综合分析
- [ ] **批量蒸馏**：批量导入语料文件，一步生成多个角色的 agent.md
- [ ] **RAG 评估**：检索质量监控（精准率/召回率）、自动优化搜索参数
