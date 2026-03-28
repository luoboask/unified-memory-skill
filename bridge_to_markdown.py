#!/usr/bin/env python3
"""
bridge_to_markdown.py - 知识系统 → Markdown 桥

从 SQLite 知识记忆系统中提取新内容，写入 OpenClaw 可读的 markdown 文件。
让 OpenClaw agent 在启动时能"看到"知识系统产生的洞察。

数据流：
    SQLite (memory_stream.db) → 提取新记忆 → 写入 memory/YYYY-MM-DD.md

用法:
    python3 scripts/bridge/bridge_to_markdown.py                    # 同步今天的
    python3 scripts/bridge/bridge_to_markdown.py --since 2026-03-24 # 指定日期起
    python3 scripts/bridge/bridge_to_markdown.py --agent demo-agent # 指定 agent
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

from path_utils import resolve_workspace

WORKSPACE = resolve_workspace().parent
MEMORY_DIR = WORKSPACE / "memory"

sys.path.insert(0, str(WORKSPACE / "scripts"))
from lock_utils import file_lock, md_file_lock, open_db

# 记忆类型映射
TYPE_MAP = {
    "observation": ("📌 观察", "event"),
    "reflection":  ("💭 反思", "reflection"),
    "knowledge":   ("📚 知识", "learning"),
    "goal":        ("🎯 目标", "todo"),
}


def get_db_path(agent_name: str) -> Path:
    return WORKSPACE / "data" / agent_name / "memory" / "memory_stream.db"


def fetch_new_memories(db_path: Path, since: str) -> List[Dict]:
    """从 SQLite 中获取指定日期之后的记忆"""
    if not db_path.exists():
        print(f"  ⚠️  数据库不存在: {db_path}")
        return []

    conn = open_db(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT id, content, memory_type, importance, tags, created_at
            FROM memories
            WHERE created_at >= ?
            ORDER BY created_at ASC
        """, (since,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")
        return []
    finally:
        conn.close()


def get_synced_ids(sync_file: Path) -> set:
    """获取已同步的记忆 ID"""
    if not sync_file.exists():
        return set()
    try:
        data = json.loads(sync_file.read_text(encoding="utf-8"))
        return set(data.get("synced_ids", []))
    except Exception:
        return set()


def save_synced_ids(sync_file: Path, ids: set):
    """保存已同步的记忆 ID"""
    sync_file.parent.mkdir(parents=True, exist_ok=True)
    data = {"synced_ids": sorted(ids), "last_sync": datetime.now().isoformat()}
    sync_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ensure_daily_file(date_str: str) -> Path:
    """确保每日 markdown 文件存在"""
    filepath = MEMORY_DIR / f"{date_str}.md"
    if not filepath.exists():
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(f"# {date_str} - 会话记录\n\n", encoding="utf-8")
    return filepath


def append_to_daily(date_str: str, section: str, entries: List[str]):
    """追加内容到 daily markdown 文件的指定 section"""
    filepath = ensure_daily_file(date_str)
    content = filepath.read_text(encoding="utf-8")

    # 查找 section
    section_header = f"## {section}"
    if section_header in content:
        # 在 section 末尾追加（下一个 ## 之前）
        lines = content.split("\n")
        insert_idx = None
        in_section = False
        for i, line in enumerate(lines):
            if line.strip() == section_header:
                in_section = True
                continue
            if in_section and line.startswith("## "):
                insert_idx = i
                break
        if insert_idx is None:
            insert_idx = len(lines)
        # 去掉尾部空行
        while insert_idx > 0 and not lines[insert_idx - 1].strip():
            insert_idx -= 1
        for entry in entries:
            lines.insert(insert_idx, entry)
            insert_idx += 1
        lines.insert(insert_idx, "")
        content = "\n".join(lines)
    else:
        # 创建新 section
        if content and not content.endswith("\n\n"):
            content = content.rstrip("\n") + "\n\n"
        content += f"{section_header}\n\n"
        for entry in entries:
            content += f"{entry}\n"
        content += "\n"

    filepath.write_text(content, encoding="utf-8")


def sync_to_markdown(agent_name: str, since: str) -> dict:
    """执行同步：SQLite → Markdown（带全局锁）"""
    with file_lock("bridge_to_markdown"):
        return _sync_to_markdown_inner(agent_name, since)


def _sync_to_markdown_inner(agent_name: str, since: str) -> dict:
    db_path = get_db_path(agent_name)
    sync_file = WORKSPACE / "data" / agent_name / ".bridge_sync.json"

    memories = fetch_new_memories(db_path, since)
    if not memories:
        return {"new": 0, "skipped": 0}

    synced_ids = get_synced_ids(sync_file)
    new_count = 0
    skip_count = 0

    # 预加载所有 daily md 文件内容用于验证
    md_cache = {}

    # 按日期分组
    by_date = {}
    for mem in memories:
        mem_id = mem["id"]

        # 提取日期
        created = mem["created_at"]
        if "T" in str(created):
            date_str = str(created).split("T")[0]
        else:
            date_str = str(created).split(" ")[0]

        # 即使 ID 已标记为同步，也要验证文件中是否真的存在内容
        # 防止文件被清空后数据无法恢复
        if mem_id in synced_ids:
            if date_str not in md_cache:
                md_file = MEMORY_DIR / f"{date_str}.md"
                md_cache[date_str] = md_file.read_text("utf-8") if md_file.exists() else ""
            content_clean = re.sub(r'^[-\s⭐❌✅❗🔨📌📚💭☐🎯📝]+', '', mem["content"].strip()).strip()
            if content_clean in md_cache[date_str]:
                skip_count += 1
                continue
            # 文件中不存在 → 需要重新写入
            synced_ids.discard(mem_id)

        if date_str not in by_date:
            by_date[date_str] = {}

        mem_type = mem.get("memory_type", "observation")
        section_name = TYPE_MAP.get(mem_type, ("📝 其他", "other"))[0]

        if section_name not in by_date[date_str]:
            by_date[date_str][section_name] = []

        importance = mem.get("importance", 5.0)
        content = mem["content"].strip()

        # 格式化条目
        marker = "⭐ " if importance >= 8 else ""
        entry = f"- {marker}{content}"
        by_date[date_str][section_name].append(entry)
        synced_ids.add(mem_id)
        new_count += 1

    # 写入 markdown
    for date_str, sections in sorted(by_date.items()):
        for section_name, entries in sections.items():
            # 去重：检查文件中是否已有相同内容
            filepath = MEMORY_DIR / f"{date_str}.md"
            existing = filepath.read_text(encoding="utf-8") if filepath.exists() else ""
            # 标准化去重：去掉 emoji 装饰后比较核心内容
            def normalize(s):
                s = re.sub(r'^[-\s⭐❌✅❗🔨📌📚💭☐🎯📝]+', '', s)
                return s.strip()
            existing_normalized = normalize(existing)
            new_entries = [e for e in entries if normalize(e) not in existing_normalized]
            if new_entries:
                append_to_daily(date_str, section_name, new_entries)
                print(f"  📝 {date_str} [{section_name}]: +{len(new_entries)} 条")

    save_synced_ids(sync_file, synced_ids)
    return {"new": new_count, "skipped": skip_count}


def main():
    parser = argparse.ArgumentParser(description="知识系统 → Markdown 桥")
    parser.add_argument("--agent", default="demo-agent", help="Agent 名称")
    parser.add_argument("--since", default=None, help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=2, help="同步最近几天（默认 2）")
    args = parser.parse_args()

    if args.since:
        since = args.since
    else:
        since = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"🔄 知识系统 → Markdown")
    print(f"   Agent: {args.agent}")
    print(f"   起始: {since}\n")

    result = sync_to_markdown(args.agent, since)

    print(f"\n✅ 同步完成: {result['new']} 新增, {result['skipped']} 跳过")


if __name__ == "__main__":
    main()
