"""蒸馏 CLI 入口.

纯命令行参数式蒸馏，不交互。

Usage:
    python -m distillation.intake --family colleague --slug zhang-san --corpus-file chat.txt
    python -m distillation.intake --family colleague --slug zhang-san --corpus-file chat.txt --name 张三
    cat chat.txt | python -m distillation.intake --family colleague --slug zhang-san --stdin
"""

import argparse
import json
import sys
from pathlib import Path

from .llm_utils import call_llm_json
from .persona_analyzer import analyze_persona
from .work_analyzer import analyze_work
from .relationship_analyzer import analyze_relationship
from .generator import generate_agent, OUTPUTS_ROOT
from memory.mem0_client import Mem0Client

AUTO_PROFILE_PATH = Path(__file__).parent.parent.parent / "config" / "prompts" / "auto_profile.md"


def _load_corpus(args: argparse.Namespace) -> str:
    """加载语料：file > stdin."""
    if args.corpus_file:
        path = Path(args.corpus_file)
        if not path.exists():
            raise FileNotFoundError(f"语料文件不存在: {args.corpus_file}")
        return path.read_text(encoding="utf-8")
    if args.stdin:
        return sys.stdin.read()
    raise ValueError("请提供 --corpus-file <文件路径> 或 --stdin 从标准输入读取语料")


def _auto_profile(corpus: str) -> dict:
    """从语料中自动推断角色基本信息."""
    prompt = AUTO_PROFILE_PATH.read_text(encoding="utf-8")
    user_prompt = prompt.replace("{docs}", corpus)
    return call_llm_json(
        system_prompt="你是一个人物画像分析专家，从语料中提取角色基本信息。严格按 JSON 格式输出。",
        user_prompt=user_prompt,
        max_tokens=1024,
    )


def _build_profile(
    args: argparse.Namespace, auto_profile: dict, corpus: str, family: str
) -> tuple[dict, list[str], str]:
    """构建角色 profile，优先使用用户提供的值，否则用自动推断结果."""
    name = args.name or auto_profile.get("name") or args.slug
    company = args.company or auto_profile.get("company", "")
    level = args.level or auto_profile.get("level", "")
    role = args.role or auto_profile.get("role", "")
    mbti = args.mbti or auto_profile.get("mbti", "")
    gender = args.gender or auto_profile.get("gender", "")

    basic_info = {
        "name": name, "company": company, "level": level,
        "role": role, "mbti": mbti, "gender": gender,
    }
    if family == "relationship":
        basic_info["relationship_type"] = args.relationship_type or "朋友"

    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    else:
        tags = auto_profile.get("tags", [])

    impression = args.impression or auto_profile.get("impression", "")

    return basic_info, tags, impression


def _intake_colleague_cli(args: argparse.Namespace) -> None:
    """同事族蒸馏 (CLI 模式)."""
    print(f"=== 蒸馏角色: {args.slug} (colleague) ===\n")

    # 1. 加载语料
    corpus = _load_corpus(args)
    print(f"语料: {len(corpus)} 字符")

    # 2. 自动推断（如果需要）
    auto = {}
    need_auto = not (args.name and args.tags and args.impression)
    if need_auto:
        print("自动推断角色信息...")
        auto = _auto_profile(corpus)
        print(f"  姓名: {auto.get('name') or '未推断出'}")
        print(f"  职位: {auto.get('role') or '未推断出'}")
        tags_display = ", ".join(auto.get("tags", [])) or "无"
        print(f"  标签: {tags_display}")
        print(f"  印象: {auto.get('impression') or '未推断出'}")

    # 3. 构建 profile
    basic_info, tags, impression = _build_profile(args, auto, corpus, "colleague")
    print()

    # 4. LLM 分析
    print("分析人格...")
    persona = analyze_persona(basic_info, tags, corpus)
    l0_count = len(persona.get("layer_0", []))
    print(f"  Layer 0 规则: {l0_count} 条")

    print("分析工作能力...")
    work = analyze_work(basic_info, corpus)
    stack = work.get("tech_spec", {}).get("stack", [])
    knowledge = work.get("knowledge", [])
    print(f"  技术栈: {', '.join(stack) if stack else '未识别'}")
    print(f"  经验知识: {len(knowledge)} 条")

    # 5. 生成产物
    print("生成产物 + Mem0 写入...")
    meta = {
        "name": basic_info["name"],
        "slug": args.slug,
        "family": "colleague",
        "profile": basic_info,
        "tags": {"personality": tags},
        "impression": impression,
    }

    try:
        mem0 = Mem0Client.from_yaml()
    except Exception as e:
        print(f"  Mem0 未连接 ({e})，仅生成本地文件")
        mem0 = None

    generate_agent(meta, persona, work, corpus=corpus, mem0_client=mem0)

    # 6. 打印产出
    out_dir = OUTPUTS_ROOT / "colleague" / args.slug
    print(f"\n=== 完成 ===")
    print(f"输出: {out_dir}/")
    for f in sorted(out_dir.iterdir()):
        if f.is_file():
            print(f"  {f.name:20s} {f.stat().st_size:>6d} bytes")

    if mem0:
        c = Mem0Client.from_yaml()
        total = 0
        for layer, aid in [
            ("persona", f"{args.slug}-persona"),
            ("capability", f"{args.slug}-capability"),
            ("knowledge", f"{args.slug}-knowledge"),
        ]:
            result = c.get_all(agent_id=aid)
            count = len(result.get("results", []))
            total += count
            print(f"  Qdrant {layer}: {count} 条")
        print(f"  Qdrant 总计: {total} 条记忆")


def _intake_relationship_cli(args: argparse.Namespace) -> None:
    """关系族蒸馏 (CLI 模式)."""
    print(f"=== 蒸馏角色: {args.slug} (relationship) ===\n")

    corpus = _load_corpus(args)
    print(f"语料: {len(corpus)} 字符")

    auto = {}
    need_auto = not (args.name and args.tags and args.impression)
    if need_auto:
        print("自动推断角色信息...")
        auto = _auto_profile(corpus)
        print(f"  姓名: {auto.get('name') or '未推断出'}")
        print(f"  标签: {', '.join(auto.get('tags', [])) or '无'}")

    basic_info, tags, impression = _build_profile(args, auto, corpus, "relationship")
    print()

    print("分析人格...")
    persona = analyze_persona(basic_info, tags, corpus)
    print(f"  Layer 0 规则: {len(persona.get('layer_0', []))} 条")

    print("分析关系模式...")
    rel = analyze_relationship(basic_info, corpus)
    catchphrases = rel.get("expression_dna", {}).get("catchphrases", [])
    print(f"  口头禅: {', '.join(catchphrases) if catchphrases else '未识别'}")

    print("生成产物 + Mem0 写入...")
    meta = {
        "name": basic_info["name"],
        "slug": args.slug,
        "family": "relationship",
        "profile": basic_info,
        "tags": {"personality": tags},
        "impression": impression,
    }

    try:
        mem0 = Mem0Client.from_yaml()
    except Exception as e:
        print(f"  Mem0 未连接 ({e})，仅生成本地文件")
        mem0 = None

    generate_agent(meta, persona, rel, corpus=corpus, mem0_client=mem0)

    out_dir = OUTPUTS_ROOT / "relationship" / args.slug
    print(f"\n=== 完成 ===")
    print(f"输出: {out_dir}/")
    for f in sorted(out_dir.iterdir()):
        if f.is_file():
            print(f"  {f.name:20s} {f.stat().st_size:>6d} bytes")


def _check_slug_conflict(slug: str, family: str) -> None:
    """检查 slug 是否已存在（create 模式不允许重复）."""
    out_dir = OUTPUTS_ROOT / family / slug
    if out_dir.exists():
        print(f"错误: 角色 '{slug}' 已存在于 {out_dir}/")
        print("如果是语料追加，请使用 --mode append（暂未实现）")
        print("或者删除已有产物后重新创建")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Character-Agent 蒸馏工具 (CLI 模式)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m distillation.intake --family colleague --slug zhang-san --corpus-file chat.txt
  python -m distillation.intake --family colleague --slug zhang-san --corpus-file chat.txt --name 张三 --tags "数据驱动,黑咖啡"
  cat chat.txt | python -m distillation.intake --family colleague --slug zhang-san --stdin
        """,
    )
    parser.add_argument("--family", required=True, choices=["colleague", "relationship"], help="角色族")
    parser.add_argument("--slug", required=True, help="角色标识（如 zhang-san）")
    parser.add_argument("--corpus-file", help="语料文件路径")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取语料")
    parser.add_argument("--name", help="角色名称，不填由 LLM 从语料推断")
    parser.add_argument("--company", help="公司名称")
    parser.add_argument("--level", help="职级")
    parser.add_argument("--role", help="职位/角色")
    parser.add_argument("--mbti", help="MBTI 类型")
    parser.add_argument("--gender", help="性别")
    parser.add_argument("--tags", help="个性标签，逗号分隔")
    parser.add_argument("--impression", help="主观印象/一句话描述")
    parser.add_argument("--relationship-type", default="朋友", help="关系类型（仅 relationship 族）")

    args = parser.parse_args()

    if not args.corpus_file and not args.stdin:
        parser.error("请提供 --corpus-file <路径> 或 --stdin")

    _check_slug_conflict(args.slug, args.family)

    try:
        if args.family == "colleague":
            _intake_colleague_cli(args)
        else:
            _intake_relationship_cli(args)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
