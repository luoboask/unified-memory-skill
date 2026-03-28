#!/usr/bin/env python3
"""
memory_stats.py - 记忆系统全面统计

用法:
    python3 scripts/memory_stats.py
    python3 scripts/memory_stats.py --agent demo-agent
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

from path_utils import resolve_workspace

WORKSPACE = resolve_workspace()
MEMORY_DIR = WORKSPACE / "memory"
WEEKLY_DIR = MEMORY_DIR / "weekly"
MONTHLY_DIR = MEMORY_DIR / "monthly"
ARCHIVE_DIR = MEMORY_DIR / "archive"
INDEX_DB = WORKSPACE / "data" / "index" / "memory_index.db"
MEMORY_MD = WORKSPACE / "MEMORY.md"


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def count_md_entries(filepath: Path) -> int:
    if not filepath.exists():
        return 0
    return sum(1 for line in filepath.read_text("utf-8").split("\n")
               if line.strip().startswith("- "))


def main():
    parser = argparse.ArgumentParser(description="记忆系统统计")
    parser.add_argument("--agent", default="demo-agent")
    args = parser.parse_args()

    print("=" * 55)
    print("📊 记忆系统统计")
    print("=" * 55)

    # MEMORY.md
    if MEMORY_MD.exists():
        lines = len(MEMORY_MD.read_text("utf-8").split("\n"))
        print(f"\n📝 MEMORY.md: {fmt_size(MEMORY_MD.stat().st_size)}, {lines} 行")
    else:
        print(f"\n📝 MEMORY.md: 不存在")

    # Daily
    dailies = sorted(MEMORY_DIR.glob("????-??-??.md"))
    total_entries = sum(count_md_entries(f) for f in dailies)
    print(f"\n📅 每日记录: {len(dailies)} 天, {total_entries} 条")
    if dailies:
        print(f"   范围: {dailies[0].stem} ~ {dailies[-1].stem}")

    # Weekly / Monthly / Archive
    weeklies = list(WEEKLY_DIR.glob("*.md")) if WEEKLY_DIR.exists() else []
    monthlies = list(MONTHLY_DIR.glob("*.md")) if MONTHLY_DIR.exists() else []
    archives = list(ARCHIVE_DIR.glob("*.md")) if ARCHIVE_DIR.exists() else []
    print(f"📅 周摘要: {len(weeklies)} 份")
    print(f"📅 月摘要: {len(monthlies)} 份")
    print(f"📦 归档: {len(archives)} 份")

    # SQLite 知识系统
    db_path = WORKSPACE / "data" / args.agent / "memory" / "memory_stream.db"
    if db_path.exists():
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        types = conn.execute(
            "SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type"
        ).fetchall()
        dupes = conn.execute(
            "SELECT COUNT(*) FROM (SELECT content, COUNT(*) c FROM memories GROUP BY content HAVING c > 1)"
        ).fetchone()[0]
        conn.close()
        print(f"\n🧠 知识系统 ({args.agent})")
        print(f"   总记忆: {total} 条")
        for t, c in types:
            print(f"   {t}: {c}")
        if dupes:
            print(f"   ⚠️  重复: {dupes} 组")
        else:
            print(f"   ✅ 无重复")
        print(f"   数据库: {fmt_size(db_path.stat().st_size)}")
    else:
        print(f"\n🧠 知识系统: 无数据库")

    # 搜索索引
    if INDEX_DB.exists():
        conn = sqlite3.connect(str(INDEX_DB), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        vecs = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        last = conn.execute("SELECT MAX(indexed_at) FROM file_state").fetchone()
        conn.close()
        print(f"\n🔍 搜索索引")
        print(f"   文档块: {docs}")
        print(f"   向量数: {vecs} {'✅' if vecs > 0 else '❌ 运行 memory_indexer.py --embed'}")
        print(f"   大小: {fmt_size(INDEX_DB.stat().st_size)}")
        if last and last[0]:
            print(f"   最后索引: {last[0]}")
    else:
        print(f"\n🔍 搜索索引: 未建立")

    # Ollama 状态
    import subprocess
    try:
        r = subprocess.run(["curl", "-s", "http://localhost:11434/api/tags"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            import json
            models = [m["name"] for m in json.loads(r.stdout).get("models", [])]
            has_embed = any("nomic" in m or "embed" in m for m in models)
            print(f"\n🦙 Ollama: ✅ 运行中 ({len(models)} 模型)")
            print(f"   嵌入模型: {'✅ ' + next((m for m in models if 'nomic' in m or 'embed' in m), '') if has_embed else '❌ 缺少'}")
        else:
            print(f"\n🦙 Ollama: ❌ 不可用")
    except Exception:
        print(f"\n🦙 Ollama: ❌ 不可用")

    print(f"\n{'=' * 55}")


if __name__ == "__main__":
    main()
