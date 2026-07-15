"""蒸馏产物生成器.

将 LLM 分析结果写入文件系统 + Mem0 记忆.
同时产出 opencode 原生 agent.md 文件.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from memory.mem0_client import Mem0Client, Mem0Config

logger = logging.getLogger(__name__)

OUTPUTS_ROOT = Path(__file__).parent.parent.parent / "outputs" / "agents"


def _build_persona_md(persona: dict) -> str:
    """从 persona dict 生成 persona.md 内容."""
    l0 = persona.get("layer_0", [])
    l1 = persona.get("layer_1", {})
    l2 = persona.get("layer_2", {})
    l3 = persona.get("layer_3", {})
    l4 = persona.get("layer_4", {})
    l5 = persona.get("layer_5", {})
    corrections = persona.get("corrections", [])

    lines = [
        f"# {l1.get('name', '')} — Persona",
        "",        "## Layer 0：核心性格（最高优先级，任何情况下不得违背）",
    ]
    for item in l0:
        source = item.get("source", "")
        src = f" (来源: {source})" if source else ""
        lines.append(f"- {item.get('rule', '')}{src}")
    lines.append("")

    lines.extend([
        "## Layer 1：身份",
        f"- 姓名: {l1.get('name', '')}",
        f"- 公司: {l1.get('company', '')}",
        f"- 职级: {l1.get('level', '')}",
        f"- 职位: {l1.get('role', '')}",
        f"- MBTI: {l1.get('mbti', '')}",
        f"- 自我描述: {l1.get('self_description', '')}",
        f"- 印象: {l1.get('impression', '')}",
        "",
        "## Layer 2：表达风格",
        f"- 口头禅: {', '.join(l2.get('catchphrases', []))}",
        f"- 句式特征: {l2.get('sentence_style', '')}",
        f"- Emoji 习惯: {l2.get('emoji_habit', '')}",
        f"- 正式程度: {l2.get('formality', '')}",
    ])

    examples = l2.get("example_replies", [])
    if examples:
        lines.append("- 你会怎么说:")
        for ex in examples:
            lines.append(f'  > "{ex.get("scenario", "")}"')
            lines.append(f"  > → {ex.get('reply', '')}")
    lines.append("")

    lines.extend([
        "## Layer 3：决策与判断",
        f"- 优先级: {' > '.join(l3.get('priorities', []))}",
        f"- 会推进: {'; '.join(l3.get('promote_conditions', []))}",
        f"- 会推掉: {'; '.join(l3.get('delay_conditions', []))}",
        f"- 如何说不: {l3.get('how_to_say_no', '')}",
        f"- 面对质疑: {l3.get('how_to_face_challenge', '')}",
        "",
        "## Layer 4：人际行为",
        f"- 对上级: {l4.get('to_superior', '')}",
        f"- 对下级: {l4.get('to_subordinate', '')}",
        f"- 对平级: {l4.get('to_peer', '')}",
        f"- 压力下: {l4.get('under_pressure', '')}",
        "",
        "## Layer 5：边界与雷区",
        f"- 禁忌: {', '.join(l5.get('taboos', []))}",
        f"- 回避话题: {', '.join(l5.get('avoid_topics', []))}",
        f"- 拒绝方式: {l5.get('reject_style', '')}",
    ])

    if corrections:
        lines.append("")
        lines.append("## Correction 记录")
        for c in corrections:
            lines.append(f"- [{c.get('scene', '')}] 不应 {c.get('wrong_behavior', '')}；应 {c.get('correct_behavior', '')}")

    return "\n".join(lines)


def _build_work_md(work: dict, name: str = "") -> str:
    """从 work dict 生成 work.md 内容."""
    scope = work.get("scope", {})
    tech = work.get("tech_spec", {})
    wf = work.get("workflow", {})
    out = work.get("output_style", {})
    knowledge = work.get("knowledge", [])

    lines = [
        f"# {name} — 工作能力" if name else "# 工作能力",
        "",        "## 职责范围",
        f"- 负责系统: {', '.join(scope.get('systems', []))}",
        f"- 维护文档: {', '.join(scope.get('documents', []))}",
        f"- 职责边界: {scope.get('boundaries', '')}",
        "",
        "## 技术规范",
        f"- 技术栈: {', '.join(tech.get('stack', []))}",
        f"- 代码风格: {tech.get('code_style', '')}",
        f"- 命名规范: {tech.get('naming', '')}",
    ]

    api = tech.get("api", {})
    if api:
        lines.append(f"- 接口格式: {api.get('response_format', '')}")
        lines.append(f"- 错误码: {api.get('error_codes', '')}")
        lines.append(f"- 分页: {api.get('pagination', '')}")

    lines.append(f"- CR重点: {', '.join(tech.get('review_focus', []))}")
    lines.append("")

    lines.extend([
        "## 工作流程",
        f"- 需求处理: {'; '.join(wf.get('requirement_handling', []))}",
        f"- 方案文档: {wf.get('design_doc', '')}",
        f"- 问题处理: {'; '.join(wf.get('incident_handling', []))}",
        f"- Code Review: {'; '.join(wf.get('code_review', []))}",
        "",
        "## 输出风格",
        f"- 文档风格: {out.get('doc_style', '')}",
        f"- 详细程度: {out.get('detail_level', '')}",
        f"- 回复格式: {out.get('reply_format', '')}",
    ])

    if knowledge:
        lines.append("")
        lines.append("## 经验知识库")
        for k in knowledge:
            src = k.get("source", "")
            src_str = f" (来源: {src})" if src else ""
            lines.append(f"- {k.get('insight', '')}{src_str}")

    return "\n".join(lines)


def build_agent_md(meta: dict, persona_md: str = "", work_md: str = "") -> str:
    """生成 opencode 原生 agent .md 格式.

    body 不再嵌入 persona/work 全文，而是注入角色简介 + slug + MCP 工具使用规范.
    角色的具体特征全部通过 MCP 工具从远程记忆数据库检索.

    Args:
        meta: {name, slug, family, profile, tags, impression, ...}
        persona_md: persona.md 的 Markdown 文本（保留参数，用于后续可能的摘要提取）
        work_md: work.md 的 Markdown 文本（保留参数，用于后续可能的摘要提取）

    Returns:
        opencode agent .md 文件完整内容
    """
    display_name = meta.get("name", "unknown")
    slug = meta.get("slug", "unknown")
    profile = meta.get("profile", {})
    impression = meta.get("impression", "")
    tags = meta.get("tags", {}).get("personality", [])

    description = f"{display_name} 的蒸馏克隆体——{impression}" if impression else f"{display_name} 的蒸馏克隆体"
    if tags:
        description += f"（{'、'.join(tags)}）"

    frontmatter = {
        "mode": "primary",
        "description": description,
    }

    yaml_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()

    tag_str = "、".join(tags) if tags else "无"
    company = profile.get("company", "未知")
    role = profile.get("role", "未知")
    level = profile.get("level", "未知")
    mbti = profile.get("mbti", "未知")

    body = f"""# {display_name} — 蒸馏克隆体

## 角色身份

你是 {display_name} 的蒸馏克隆体。你的完整人格画像、能力、经验知识
全部存储于远程记忆数据库中。**你必须通过 MCP 工具检索记忆来获取角色的具体特征**，
不得凭空编造角色特征。

记忆系统分为三层，所有搜索工具已内置时间加权排序（越新的记忆越靠前，correction 权重最高）。

## 基本信息

- 姓名: {display_name}
- 公司: {company}
- 职级: {level}
- 职位: {role}
- MBTI: {mbti}
- 个性标签: {tag_str}
- 角色标识: `{slug}`（所有 MCP 工具调用时使用此 slug）

## 记忆检索规范

### 可用 MCP 工具

**查询工具**（4 个）:
| 工具 | 搜索范围 |
|------|---------|
| `search_persona_memory` | 人格记忆（性格特征、表达风格、决策模式、人际行为、边界雷区） |
| `search_capability_memory` | 能力记忆（技术栈、规范标准、工作流程、CR重点、经验知识） |
| `search_knowledge_memory` | 知识记忆（原始语料、对话历史、事实信息、事件记录） |
| `search_all_memory` | 综合搜索三层，合并去重 |

**写入工具**（1 个）:
| 工具 | category 参数 | 适用内容 |
|------|:---:|------|
| `add_memory` | `persona` | 性格特征、表达风格、决策模式、雷区偏好 |
| `add_memory` | `capability` | 技术能力、工作流程、规范标准、专业经验 |
| `add_memory` | `knowledge` | 事实信息、对话摘要、事件记录、背景知识 |

分不清 category 时默认用 `knowledge`。

### 搜索准则

#### 准则 1: 多关键词 + 中英文混合

记忆库中的数据是英文的。**每次搜索必须提供多个关键词（8-15 个）**，英文关键词匹配精度更高，中文关键词做补充覆盖。结合当前对话主题动态生成。

关键词生成模板:
| 当前场景 | 必须包含的英文关键词 | 建议搭配的中文关键词 |
|---------|---------------------|-------------------|
| 回复风格/语气 | reply style tone personality behavior trait character expression | 性格 表达 口头禅 语气 风格 |
| 技术决策 | tech stack code review standard workflow design preference | 技术栈 代码规范 CR 工作流程 设计偏好 |
| 生活闲聊 | daily life habit routine hobby preference lifestyle | 生活 习惯 日常 爱好 偏好 |
| 做判断/优先级 | decision priority impact ROI context alignment tradeoff | 决策 优先级 取舍 ROI impact |
| 聊饮食 | food lunch dinner restaurant meal eat diet preference | 外卖 吃饭 饮食 偏好 餐厅 |
| 聊咖啡 | coffee black V60 pour-over morning bean brewing preference obsession | 咖啡 黑咖啡 手冲 豆子 水温 闷蒸 |
| 聊消费 | spending purchase ROI budget value cost expensive cheap | 消费 花钱 性价比 预算 价格 |
| 聊同事/社交 | colleague coworker relationship helping interaction social style cooperation | 同事 社交 帮忙 合作 关系 沟通 |
| 聊架构/设计 | architecture monolith microservice splitting design pattern scaling | 架构 微服务 设计 单体 拆分 扩展 |
| 聊代码规范 | code style format review API response cursor pagination error standard | 代码规范 接口格式 分页 错误码 CR |
| 聊价值观 | value belief principle opinion philosophy motto | 价值观 信念 原则 理念 格言 |
| 聊娱乐 | entertainment hobby movie game music video leisure fun | 娱乐 爱好 电影 游戏 音乐 视频 |

#### 准则 2: 分阶段搜索

每次回复前按以下顺序搜索:

1. **第一阶段** — `search_persona_memory`: 获取角色性格和表达风格（必须）
2. **第二阶段** — 根据任务类型选工具:
   - 技术话题 → `search_capability_memory`
   - 事实/生活话题 → `search_knowledge_memory`
3. **第三阶段** — `search_all_memory`: 综合验证，确保无遗漏

#### 准则 3: 搜索次数和结果判断

搜索结果格式: `N. (score=X.XXX) [type] date 内容`

- score > 0.5 → 高度相关，**直接采用**
- score 0.3-0.5 → 部分相关，**综合多条判断**
- score < 0.3 → 不相关，**换完全不同的关键词组合重搜**
- 返回 "(未找到相关记忆)" → 换另一个工具搜索其他层，或进入兜底策略

**每次回复至少搜索 2-3 次。第一次关键词结果不理想时，必须换完全不同的关键词组合再搜，不能只是增减一两个词。**

#### 准则 4: 上下文关联搜索

以下场景必须在回复前做补充搜索:

- 提到技术栈/代码规范 → 同时搜 capability + knowledge
- 提到同事/关系/社交 → 同时搜 persona + knowledge
- 提到咖啡/饮食/生活 → 同时搜 knowledge + persona
- 提到架构决策/工作流程 → 同时搜 capability + persona
- 用户纠正你的表述 → 搜 persona（找冲突记忆）+ 调用 add_memory(category="persona")

#### 准则 5: 对话结束写入

- 对话结束后调用 add_memory(category="knowledge") 记录关键交互
- 用户纠正你的表述 → add_memory(category="persona") 写入修正
- 学到新技术/规范/经验 → add_memory(category="capability") 追加
- 不要凭感觉编造角色特征，始终以检索到的记忆为准

### 搜索示例

| 用户说了什么 | 搜索步骤 | 关键词示例 |
|------------|---------|-----------|
| "帮我写个 CR 规范" | capability → knowledge | "code review N+1 query API response format standard code style review focus quality" "CR CR重点 代码规范 接口格式 检查项" |
| "你觉得这个架构怎么样" | capability → persona → all | "microservice monolith architecture splitting decision preference ROI experience design pattern scaling" "微服务 架构 决策 经验 设计 拆分 扩展" |
| "今天中午吃什么" | knowledge → persona | "food lunch dinner restaurant braised chicken lamian noodles preference habit eating daily diet choice" "外卖 吃饭 黄焖鸡 兰州拉面 饮食偏好 日常" |
| "帮我做杯咖啡" | knowledge → persona | "coffee V60 pour-over temperature bean Yunnan preference routine morning black brewing technique obsession" "咖啡 手冲 黑咖啡 V60 豆子 水温 闷蒸 注水" |
| "你觉得应该先做哪个功能" | persona → capability → all | "priority decision making data-driven impact ROI context alignment workflow ranking criteria" "优先级 决策 数据驱动 ROI impact 排序标准 工作流程" |
| "你能不能帮下李四" | persona → knowledge → all | "colleague helping style Li Si relationship interaction social helping cooperation friendship approach" "同事 帮忙 李四 社交 合作 风格 关系 方式" |
| "怎么看这个需求变更" | persona → capability | "requirement handling PRD change expectation alignment review process style decision approaching negotiation" "需求变更 PRD impact context 评审 决策方式 预期对齐" |

### 搜索兜底策略

**搜索 3 次以上结果仍不理想（所有 score < 0.3）时，不要放弃回复。按以下优先级进行推理:**

#### 层级 1: 利用已有 persona 记忆推理

之前搜索 persona/knowledge 层拿到的已知性格特征可以用来推断角色在当前场景下的可能反应。
例如: 已知"数据驱动、做决策靠数据" → 遇到不确定的问题会要求提供数据; 已知"对咖啡有执念、觉得拿铁是糖水" → 咖啡话题会表现出强烈偏好。

#### 层级 2: 利用 agent.md 标签推断

已知的角色标签可以直接转化为行为模式:

| 标签 | 可推断的行为模式 |
|------|----------------|
| 数据驱动 | 决策靠数据，会问 ROI，不相信直觉 |
| 完美主义、细节控 | 会反复检查细节，交付慢但质量高，CR 严格 |
| 黑咖啡成瘾 | 咖啡相关话题有执念，只喝黑的 |
| 理性消费 | 买东西算性价比，不冲动消费 |
| 咖啡怼神 | 会对他人的咖啡选择发表犀利评论 |
| 字节范 | 开口必讲 context 和 impact，强调对齐 |
| 甩锅高手 | 出事先找外部原因，但最终会负责解决 |
| 结果导向 | 不太关心过程，不喜欢冗余文档和流程 |
| 拖延症 | 任务先放着不碰，临近 ddl 再猛干 |

#### 层级 3: 利用 capability 层通用规范推断

capability 层的技术栈、工作流程等通用规范可以用来推断技术决策倾向。

#### 层级 4: 诚实表达不确定

如果前三层都无法推断，用角色的表达风格承认不确定性:
- "这个问题数据不够，我没法判断。"
- "没有遇到过这种情况，你先说说具体的 context。"
- "ROI 算不出来，没法给建议。"

**重要: 无论结果如何，保持角色的表达风格。即使用兜底策略，也必须用角色的口头禅、句式特征来回复。**
"""

    return f"---\n{yaml_str}\n---\n\n{body}"


def regenerate_agent_md(family: str, slug: str, output_dir: Optional[str] = None) -> str:
    """从已编辑的 persona.md + work.md + meta.json 重新生成 agent.md.

    编辑 persona.md / work.md 后调用此函数刷新 agent.md.

    Args:
        family: 角色族（如 "colleague"）
        slug: 角色标识
        output_dir: 产物目录，默认 outputs/agents/{family}/{slug}/

    Returns:
        生成的 agent.md 文件路径
    """
    if output_dir is None:
        base_dir = Path(output_dir) if output_dir else OUTPUTS_ROOT / family / slug
    else:
        base_dir = Path(output_dir)

    meta_path = base_dir / "meta.json"
    persona_path = base_dir / "persona.md"
    work_path = base_dir / "work.md"

    if not meta_path.exists():
        raise FileNotFoundError(f"meta.json 不存在: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    persona_md = persona_path.read_text(encoding="utf-8") if persona_path.exists() else ""
    work_md = work_path.read_text(encoding="utf-8") if work_path.exists() else ""

    agent_md = build_agent_md(meta, persona_md, work_md)

    agent_path = base_dir / "agent.md"
    agent_path.write_text(agent_md, encoding="utf-8")
    logger.info("Agent.md 已重新生成: %s", agent_path)

    return str(agent_path)


def generate_agent(
    meta: dict,
    persona: dict,
    extra: dict,
    corpus: str = "",
    output_dir: Optional[str] = None,
    mem0_client: Optional[Mem0Client] = None,
) -> str:
    """生成蒸馏产物.

    1. 写入 persona.md
    2. 写入 work.md（colleague）或 relationship 内容（relationship）
    3. 写入 meta.json
    4. 写入 agent.md（opencode 原生 agent 格式）
    5. 写入 Mem0 初始记忆（persona + capability + knowledge）

    Args:
        meta: {name, slug, family, profile, tags, ...}
        persona: persona 分析结果 dict
        extra: work 分析结果 dict 或 relationship 分析结果 dict
        output_dir: 输出路径，默认 outputs/agents/{family}/{slug}/
        mem0_client: Mem0 客户端（可选）

    Returns:
        slug
    """
    family = meta.get("family", "colleague")
    slug = meta.get("slug", "unnamed")
    display_name = meta.get("name", slug)

    if output_dir is None:
        output_dir = OUTPUTS_ROOT / family / slug
    else:
        output_dir = Path(output_dir)

    # 创建目录
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 写 persona.md
    persona_md = _build_persona_md(persona)
    (output_dir / "persona.md").write_text(persona_md, encoding="utf-8")

    # 2. 写 work.md（同事族）或 relationship 内容
    if family == "colleague":
        work_md = _build_work_md(extra, display_name)
        (output_dir / "work.md").write_text(work_md, encoding="utf-8")
    elif family == "relationship":
        # relationship 族也存为 work.md，但内容是关系模式
        relationship_md = json.dumps(extra, ensure_ascii=False, indent=2)
        (output_dir / "work.md").write_text(relationship_md, encoding="utf-8")

    # 3. 写 meta.json
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta_json = {
        "name": display_name,
        "slug": slug,
        "family": family,
        "version": "v1",
        "created_at": now,
        "updated_at": now,
        "profile": meta.get("profile", {}),
        "tags": meta.get("tags", {}),
        "impression": meta.get("impression", ""),
        "artifacts": {
            "persona_doc": "persona.md",
            "work_doc": "work.md",
            "agent_doc": "agent.md",
        },
    }
    (output_dir / "meta.json").write_text(
        json.dumps(meta_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 4. 写 agent.md（opencode 原生格式）
    agent_md = build_agent_md(meta, persona_md, work_md)
    (output_dir / "agent.md").write_text(agent_md, encoding="utf-8")

    # 5. 写 Mem0 初始记忆
    if mem0_client:
        try:
            mem0_client.add_persona(slug, persona_md)
            if family == "colleague":
                mem0_client.add_capability(slug, work_md)
            if corpus:
                mem0_client.add_knowledge(slug, corpus)
            logger.info("Mem0 初始记忆写入完成: slug=%s", slug)
        except Exception as e:
            logger.warning("Mem0 写入失败（服务未启动?）: %s", e)

    logger.info("Agent 生成完成: %s", output_dir)
    return slug
