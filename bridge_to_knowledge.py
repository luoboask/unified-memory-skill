#!/usr/bin/env python3
"""
bridge_to_knowledge.py - Markdown → 知识系统桥

从 OpenClaw 的 markdown 记忆文件中提取内容，写入 SQLite 知识系统。
让知识系统的搜索、反思、进化能覆盖到对话产生的记忆。

数据流：
    memory/YYYY-MM-DD.md → 解析 → SQLite (memory_stream.db)

用法:
    python3 scripts/bridge/bridge_to_knowledge.py                    # 同步今天+昨天
    python3 scripts/bridge/bridge_to_knowledge.py --since 2026-03-24
    python3 scripts/bridge/bridge_to_knowledge.py --agent demo-agent
"""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple

from path_utils import resolve_workspace

WORKSPACE = resolve_workspace().parent
MEMORY_DIR = WORKSPACE / "memory"

# 加载锁工具
sys.path.insert(0, str(WORKSPACE / "scripts"))
from lock_utils import file_lock, open_db

# Markdown section → 知识系统类型映射
SECTION_TYPE_MAP = {
    "事件": "observation",
    "观察": "observation",
    "决定": "knowledge",
    "学习": "knowledge",
    "知识": "knowledge",
    "反思": "reflection",
    "目标": "goal",
    "待办": "goal",
}

# 重要性关键词权重
IMPORTANCE_KEYWORDS = {
    # 高重要性 (8-10)
    "决定": 2.0, "选择": 1.5, "采用": 1.5, "确定": 1.5, "方案": 1.5,
    "引入": 1.5, "切换": 1.5, "替代": 1.5, "放弃": 1.5, "废弃": 1.5,
    "架构": 2.0, "重构": 1.5, "迁移": 1.5, "部署": 1.0, "上线": 1.0,
    "⭐": 3.0, "❗": 2.0, "重要": 2.0, "关键": 2.0, "核心": 1.5,
    "教训": 2.0, "错误": 1.5, "bug": 1.5, "修复": 1.0, "回滚": 1.5,
    "安全": 1.5, "权限": 1.0, "泄漏": 1.5, "漏洞": 2.0,
    # 中等重要性 (6-7)
    "完成": 1.0, "实现": 1.0, "优化": 1.0, "改进": 1.0,
    "发现": 1.0, "学到": 1.0, "原来": 0.5,
    "❌": 1.5, "失败": 1.5,
    "✅": 0.5,
    # 降低重要性
    "测试": -0.5, "调试": -0.5, "临时": -1.0, "暂时": -0.5,
}


def estimate_importance(content: str, memory_type: str) -> float:
    """基于关键词和类型估算重要性 (1-10)"""
    base = {
        "knowledge": 6.0,   # 决定/学习天然更重要
        "reflection": 6.0,  # 反思有价值
        "goal": 5.5,        # 待办一般
        "observation": 5.0, # 事件默认最低
    }.get(memory_type, 5.0)

    bonus = 0.0
    for keyword, weight in IMPORTANCE_KEYWORDS.items():
        if keyword in content:
            bonus += weight

    # 内容长度加分（详细的更重要）
    if len(content) > 100:
        bonus += 0.5
    if len(content) > 200:
        bonus += 0.5

    score = base + bonus
    return max(1.0, min(10.0, round(score, 1)))


def get_db_path(agent_name: str) -> Path:
    return WORKSPACE / "data" / agent_name / "memory" / "memory_stream.db"


def ensure_db(db_path: Path):
    """确保数据库和表存在"""
    conn = open_db(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            memory_type TEXT DEFAULT 'observation',
            importance REAL DEFAULT 5.0,
            tags TEXT DEFAULT '[]',
            embedding TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute('CREATE INDEX IF NOT EXISTS idx_type ON memories(memory_type)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_created ON memories(created_at)')
    conn.commit()
    conn.close()


def normalize_content(content: str) -> str:
    """标准化内容，去掉装饰性前缀，用于去重比较"""
    s = content.strip()
    # 去掉 ⭐ ❌ ✅ 等 emoji 前缀
    s = re.sub(r'^[⭐❌✅❗🔨📌📚💭☐🎯📝\s]+', '', s)
    return s.strip()


def content_hash(content: str) -> str:
    """生成内容哈希，用于去重（标准化后再 hash）"""
    return hashlib.md5(normalize_content(content).encode("utf-8")).hexdigest()


def get_existing_hashes(db_path: Path) -> set:
    """获取已存在的内容哈希"""
    if not db_path.exists():
        return set()
    conn = open_db(db_path)
    try:
        rows = conn.execute("SELECT content FROM memories").fetchall()
        return {content_hash(r[0]) for r in rows}
    finally:
        conn.close()


def parse_daily_file(filepath: Path) -> List[Dict]:
    """解析 daily markdown 文件，提取条目"""
    content = filepath.read_text(encoding="utf-8")
    entries = []
    current_type = "observation"
    date_str = re.search(r"(\d{4}-\d{2}-\d{2})", filepath.name)
    file_date = date_str.group(1) if date_str else datetime.now().strftime("%Y-%m-%d")

    for line in content.split("\n"):
        stripped = line.strip()

        # 检测 section 类型
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            # 去掉 emoji
            heading_clean = re.sub(r'[^\w\s]', '', heading).strip()
            for keyword, mem_type in SECTION_TYPE_MAP.items():
                if keyword in heading_clean:
                    current_type = mem_type
                    break

        # 提取列表项
        elif stripped.startswith("- "):
            item = stripped[2:].strip()
            # 去掉时间前缀 [HH:MM]
            item = re.sub(r'^\[\d{2}:\d{2}\]\s*', '', item)
            # 去掉 checkbox
            item = re.sub(r'^\[[ x]\]\s*', '', item)

            if len(item) < 3:
                continue

            # 智能重要性评分
            importance = estimate_importance(item, current_type)

            entries.append({
                "content": item,
                "memory_type": current_type,
                "importance": importance,
                "date": file_date,
                "metadata": json.dumps({"source": f"markdown:{filepath.name}"}),
            })

    return entries


def sync_to_knowledge(agent_name: str, since: str) -> dict:
    """执行同步：Markdown → SQLite（带全局锁）"""
    with file_lock("bridge_to_knowledge"):
        return _sync_to_knowledge_inner(agent_name, since)


def _sync_to_knowledge_inner(agent_name: str, since: str) -> dict:
    db_path = get_db_path(agent_name)
    ensure_db(db_path)

    existing_hashes = get_existing_hashes(db_path)

    # 收集要同步的文件
    files = []
    since_date = datetime.strptime(since, "%Y-%m-%d")
    for md_file in sorted(MEMORY_DIR.glob("????-??-??.md")):
        match = re.match(r"(\d{4}-\d{2}-\d{2})", md_file.name)
        if match:
            file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
            if file_date >= since_date:
                files.append(md_file)

    new_count = 0
    skip_count = 0

    conn = open_db(db_path)
    try:
        for filepath in files:
            entries = parse_daily_file(filepath)
            file_new = 0
            file_skip = 0

            for entry in entries:
                h = content_hash(entry["content"])
                if h in existing_hashes:
                    file_skip += 1
                    continue

                conn.execute("""
                    INSERT INTO memories (content, memory_type, importance, tags, metadata, created_at)
                    VALUES (?, ?, ?, '[]', ?, ?)
                """, (
                    entry["content"],
                    entry["memory_type"],
                    entry["importance"],
                    entry["metadata"],
                    entry["date"] + "T12:00:00",
                ))
                existing_hashes.add(h)
                file_new += 1

            if file_new > 0:
                print(f"  📄 {filepath.name}: +{file_new} 新增, {file_skip} 跳过")
            elif file_skip > 0:
                print(f"  ⏭️  {filepath.name}: 全部已存在 ({file_skip})")

            new_count += file_new
            skip_count += file_skip

        conn.commit()
    finally:
        conn.close()

    return {"new": new_count, "skipped": skip_count}


def main():
    parser = argparse.ArgumentParser(description="Markdown → 知识系统桥")
    parser.add_argument("--agent", default="demo-agent", help="Agent 名称")
    parser.add_argument("--since", default=None, help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=2, help="同步最近几天（默认 2）")
    args = parser.parse_args()

    if args.since:
        since = args.since
    else:
        since = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"🔄 Markdown → 知识系统")
    print(f"   Agent: {args.agent}")
    print(f"   起始: {since}\n")

    result = sync_to_knowledge(args.agent, since)

    print(f"\n✅ 同步完成: {result['new']} 新增, {result['skipped']} 跳过")


if __name__ == "__main__":
    main()
