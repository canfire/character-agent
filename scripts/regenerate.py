"""重新生成 opencode agent.md 文件.

从已编辑的 persona.md + work.md + meta.json 重新融合生成 agent.md.
编辑蒸馏产物后不需要重新蒸馏，直接运行此脚本刷新 agent.md.

Usage:
    python scripts/regenerate.py --slug zhang-san --family colleague
    python scripts/regenerate.py --slug zhang-san --family colleague --output-dir /custom/path
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from distillation.generator import regenerate_agent_md


def main():
    parser = argparse.ArgumentParser(description="从已编辑素材重新生成 opencode agent.md")
    parser.add_argument("--slug", required=True, help="角色标识 (如 zhang-san)")
    parser.add_argument("--family", default="colleague", choices=["colleague", "relationship"], help="角色族")
    parser.add_argument("--output-dir", help="产物目录 (默认 outputs/agents/{family}/{slug}/)")
    args = parser.parse_args()

    path = regenerate_agent_md(args.family, args.slug, args.output_dir)
    print(f"Agent.md 已重新生成: {path}")


if __name__ == "__main__":
    main()
