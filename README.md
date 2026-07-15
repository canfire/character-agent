# Character-Agent

从人的语料中蒸馏角色，生成 [opencode](https://opencode.ai) 原生 Agent。

- **蒸馏**：从语料中提取角色的人格画像和工作能力，存入 Mem0 记忆数据库
- **导出**：自动生成 opencode 可识别的 agent.md 文件，直接放入 `.opencode/agent/` 目录即可使用
- **记忆检索**：通过 MCP Server 提供语义搜索和写入接口，Agent 运行时动态检索角色记忆

灵感来源于 [dot-skill（colleague-skill）](https://github.com/titanwings/colleague-skill)，将其从独立 Skill 升级为与 opencode 深度集成的蒸馏引擎。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                     Character-Agent                      │
│                                                         │
│  ┌──────────────────┐    ┌───────────────────────────┐  │
│  │   蒸馏引擎         │    │      MCP Server           │  │
│  │  (distillation/)  │    │   (mcp_server.py)         │  │
│  │                   │    │                           │  │
│  │  语料 → LLM分析   │    │  streamable-http 协议     │  │
│  │  → persona.md    │    │  6个记忆工具              │  │
│  │  → work.md       │    │  (查询 + 写入)            │  │
│  │  → agent.md ✓    │    │                           │  │
│  │  → Mem0 写入     │    └──────────┬────────────────┘  │
│  └────────┬─────────┘               │                   │
│           │                         │                   │
│           ▼                         ▼                   │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Mem0 + Qdrant 记忆数据库              │   │
│  │   persona / work / knowledge / interaction       │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
└──────────────────────┬──────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌────────────────┐    ┌───────────────────────────┐
│  agent.md      │    │  opencode.jsonc           │
│  (.opencode/   │    │  { mcp: { servers:        │
│   agent/)      │    │      "character-tools" }}  │
└────────────────┘    └───────────────────────────┘
         │                           │
         └───────────┬───────────────┘
                     ▼
            ┌────────────────┐
            │    opencode     │
            │  (角色 Agent)   │
            └────────────────┘
```

## 项目结构

```
character-agent/
├── src/
│   ├── distillation/            # 蒸馏引擎
│   │   ├── intake.py            #   CLI 入口（交互式信息采集）
│   │   ├── generator.py         #   产物生成器（含 agent.md 输出）
│   │   ├── persona_analyzer.py  #   人格分析器（6层结构）
│   │   ├── work_analyzer.py     #   工作能力分析器
│   │   ├── relationship_analyzer.py  # 关系模式分析器
│   │   └── llm_utils.py         #   LLM 调用工具
│   └── memory/                  # 记忆系统
│       ├── mem0_client.py       #   Mem0 客户端（Qdrant + LLM + Embedder）
│       └── test_memory.py       #   记忆测试脚本
├── mcp_server.py                # MCP Server（streamable-http）
├── scripts/
│   └── regenerate.py            # 编辑素材后重新生成 agent.md
├── config/
│   ├── settings.yaml            # LLM / Embedder / Qdrant 配置
│   └── prompts/                 # 蒸馏提示词模板
├── outputs/agents/              # 蒸馏产物
│   └── colleague/               #   同事族
│       └── zhang-san/
│           ├── agent.md          #   ★ opencode 原生 agent 文件
│           ├── persona.md        #   人格画像（可编辑素材）
│           ├── work.md           #   工作能力画像（可编辑素材）
│           └── meta.json         #   元数据
├── data/qdrant/                 # Qdrant 向量数据库数据
├── docker-compose.yml           # Qdrant 容器
├── requirements.txt
└── demo/                        # 参考项目（opencode 源码 + colleague-skill）
```

## 快速开始

### 1. 环境准备

```bash
# Python 环境
conda create -n cagent python=3.12 -y
conda activate cagent
pip install -r requirements.txt

# 启动记忆服务（Qdrant）
docker compose up -d
```

### 2. 蒸馏角色

```bash
# 一条命令蒸馏（从 txt 文件）
python -m distillation.intake \
  --family colleague \
  --slug zhang-san \
  --corpus-file corpus_example.txt

# 指定角色信息（不填则由 LLM 从语料自动推断）
python -m distillation.intake \
  --family colleague \
  --slug zhang-san \
  --corpus-file corpus_example.txt \
  --name 张三 \
  --tags "数据驱动,黑咖啡成瘾" \
  --impression "字节2-1后端，黑咖啡成瘾，理性直男"

# 从 stdin 输入语料
cat chat.txt | python -m distillation.intake --family colleague --slug zhang-san --stdin

# CLI 参数列表
#   --family       必需: colleague | relationship
#   --slug         必需: 角色标识（如 zhang-san）
#   --corpus-file  语料文件路径
#   --stdin        从标准输入读取语料
#   --name         角色名称（不填由 LLM 从语料推断）
#   --company      公司名称
#   --level        职级
#   --role         职位/角色
#   --mbti         MBTI 类型
#   --gender       性别
#   --tags         个性标签，逗号分隔
#   --impression   主观印象/一句话描述
```

输出产物：

```
outputs/agents/colleague/zhang-san/
├── agent.md       ← opencode 原生 agent 文件
├── persona.md     ← 人格画像（可编辑素材）
├── work.md        ← 工作能力画像（可编辑素材）
└── meta.json
```

### 3. 编辑素材（可选）

如果 LLM 分析的人格不够准确，直接编辑 persona.md 或 work.md，然后重新生成 agent.md：

```bash
python scripts/regenerate.py --slug zhang-san --family colleague
```

### 4. 启动 MCP Server

```bash
python mcp_server.py --host 0.0.0.0 --port 8765
```

### 5. 在 opencode 中配置

将 agent.md 复制到 opencode 项目，配置 MCP 连接：

```bash
# 项目目录下
mkdir -p .opencode/agent
cp outputs/agents/colleague/zhang-san/agent.md .opencode/agent/zhang-san.md
```

`.opencode/opencode.jsonc`：

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

重启 opencode，在 agent 列表中选择"张三"即可开始对话。

## 蒸馏 Family

| Family | CLI 参数 | 分析维度 | 输出 |
|--------|----------|---------|------|
| colleague | `--family colleague` | 人格 + 工作能力 | persona.md + work.md |
| relationship | `--family relationship` | 人格 + 关系模式 | persona.md + work.md (关系内容) |

## MCP 工具列表

| 工具 | 类型 | 说明 |
|------|------|------|
| `search_persona_memory` | 查询 | 在人格记忆中语义搜索（性格、表达风格、决策模式） |
| `search_work_memory` | 查询 | 在工作能力记忆中语义搜索（技术栈、规范、流程） |
| `search_knowledge_memory` | 查询 | 在原始语料记忆中语义搜索 |
| `search_all_memory` | 查询 | 综合搜索三类记忆并合并去重 |
| `add_conversation_memory` | 写入 | 记录对话交互到长期记忆 |
| `add_correction_memory` | 写入 | 添加或更正人设记忆 |

启动参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `0.0.0.0` | 监听地址 |
| `--port` | `8765` | 监听端口 |

## 配置说明 (`config/settings.yaml`)

```yaml
# LLM 配置（蒸馏分析和 MCP 记忆搜索共用）
llm:
  api_key: "your-api-key"
  base_url: "https://api.openai.com/v1"
  memory_model: gpt-4o-mini
  memory_temperature: 0.1
  memory_max_tokens: 1024

# Embedding 配置（向量化文本）
embedder:
  api_key: "your-api-key"
  base_url: "https://api.openai.com/v1"
  model: text-embedding-3-small
  embedding_dims: 1536

# Qdrant 向量数据库
qdrant:
  host: localhost
  port: 6333
  collection_name: character_agent
  embedding_dims: 1536

# 搜索配置
search:
  top_k: 5      # 每次搜索返回最大数量
  hybrid: true  # 混合搜索（语义 + 关键词）
```

## Agent 工作流程

生成的 agent.md 在 system prompt 中强制要求 Agent 遵循以下流程：

1. **首次对话**：调用 `search_persona_memory` 检索核心性格
2. **处理技术任务前**：调用 `search_work_memory` 检索技术规范
3. **做判断/决策前**：调用 `search_all_memory` 检索相关上下文
4. **回复风格**：严格匹配检索到的记忆中的表达风格
5. **对话结束**：调用 `add_conversation_memory` 记录关键交互
6. **人设被纠正时**：调用 `add_correction_memory` 添加修正

## 技术栈

| 模块 | 技术 |
|------|------|
| 蒸馏引擎 | Python 3.12 + OpenAI API |
| 记忆系统 | Mem0 + Qdrant |
| MCP Server | Python MCP SDK (streamable-http) |
| Agent 运行时 | opencode (TypeScript + Bun) |
| 向量化 | Qwen3-Embedding-0.6B（可替换） |
| 基础设施 | Docker (Qdrant) |

## 文档

- [技术方案设计](docs/DESIGN.md)
