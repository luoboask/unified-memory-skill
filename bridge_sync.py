#!/usr/bin/env python3
"""
bridge_sync.py - 双向同步入口

一键执行双向同步：
1. SQLite → Markdown（知识系统的洞察 → OpenClaw 可读）
2. Markdown → SQLite（对话记录 → 知识系统可检索）

用法:
    python3 scripts/bridge/bridge_sync.py                     # 双向同步
    python3 scripts/bridge/bridge_sync.py --direction to-md   # 只同步到 markdown
    python3 scripts/bridge/bridge_sync.py --direction to-kb   # 只同步到知识系统
    python3 scripts/bridge/bridge_sync.py --agent demo-agent --days 7
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加当前目录到路径
BRIDGE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BRIDGE_DIR))

from bridge_to_markdown import sync_to_markdown
from bridge_to_knowledge import sync_to_knowledge


def main():
    parser = argparse.ArgumentParser(description="双向同步 - OpenClaw ↔ 知识系统")
    parser.add_argument("--agent", default="demo-agent", help="Agent 名称")
    parser.add_argument("--since", default=None, help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=2, help="同步最近几天（默认 2）")
    parser.add_argument("--direction", choices=["both", "to-md", "to-kb"],
                        default="both", help="同步方向")
    args = parser.parse_args()

    if args.since:
        since = args.since
    else:
        since = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print("=" * 55)
    print("🔄 双向记忆同步")
    print("=" * 55)
    print(f"  Agent: {args.agent}")
    print(f"  起始: {since}")
    print(f"  方向: {args.direction}")
    print()

    total_new = 0
    total_skip = 0

    if args.direction in ("both", "to-md"):
        print("━" * 55)
        print("📤 Phase 1: 知识系统 → Markdown")
        print("━" * 55)
        r1 = sync_to_markdown(args.agent, since)
        total_new += r1["new"]
        total_skip += r1["skipped"]
        print(f"  结果: {r1['new']} 新增, {r1['skipped']} 跳过\n")

    if args.direction in ("both", "to-kb"):
        print("━" * 55)
        print("📥 Phase 2: Markdown → 知识系统")
        print("━" * 55)
        r2 = sync_to_knowledge(args.agent, since)
        total_new += r2["new"]
        total_skip += r2["skipped"]
        print(f"  结果: {r2['new']} 新增, {r2['skipped']} 跳过\n")

    print("=" * 55)
    print(f"📊 总计: {total_new} 新增, {total_skip} 跳过")
    print("=" * 55)


if __name__ == "__main__":
    main()
