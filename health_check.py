#!/usr/bin/env python3
"""
health_check.py - 记忆系统健康检查

校验两套系统的数据一致性，发现问题自动修复。

用法:
    python3 scripts/health_check.py --agent demo-agent
    python3 scripts/health_check.py --agent demo-agent --fix
"""

import argparse
import hashlib
import re
import sqlite3
from pathlib import Path
import sys

from path_utils import resolve_workspace

WORKSPACE = resolve_workspace()
MEMORY_DIR = WORKSPACE / "memory"


def normalize(s: str) -> str:
    s = re.sub(r'^[-\s⭐❌✅❗🔨📌📚💭☐🎯📝\[\]\d:]+', '', s)
    return s.strip()


def content_hash(s: str) -> str:
    return hashlib.md5(normalize(s).encode("utf-8")).hexdigest()


def check(agent_name: str, fix: bool = False):
    db_path = WORKSPACE / "data" / agent_name / "memory" / "memory_stream.db"
    index_db = WORKSPACE / "data" / "index" / "memory_index.db"
    issues = []

    print("=" * 55)
    print("🏥 记忆系统健康检查")
    print("=" * 55)

    # 1. 文件存在性
    print("\n📁 文件检查")
    for name, path in [
        ("MEMORY.md", WORKSPACE / "MEMORY.md"),
        ("知识系统DB", db_path),
        ("搜索索引", index_db),
        ("memory/", MEMORY_DIR),
    ]:
        if path.exists():
            print(f"  ✅ {name}")
        else:
            print(f"  ❌ {name} 不存在")
            issues.append(f"缺失: {name}")

    # 2. SQLite 重复检查
    if db_path.exists():
        print("\n🔍 重复数据检查")
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")

        # 精确重复
        exact_dupes = conn.execute(
            "SELECT content, COUNT(*) c FROM memories GROUP BY content HAVING c > 1"
        ).fetchall()
        if exact_dupes:
            print(f"  ⚠️  发现 {len(exact_dupes)} 组精确重复")
            for content, count in exact_dupes[:5]:
                print(f"     \"{content[:50]}...\" x{count}")
            issues.append(f"精确重复: {len(exact_dupes)} 组")
            if fix:
                conn.execute(
                    "DELETE FROM memories WHERE id NOT IN "
                    "(SELECT MIN(id) FROM memories GROUP BY content)"
                )
                conn.commit()
                print(f"  🔧 已修复：删除重复，保留最早的")
        else:
            print(f"  ✅ 无精确重复")

        # 标准化重复（去 emoji 后相同）
        rows = conn.execute("SELECT id, content FROM memories").fetchall()
        hash_map = {}
        norm_dupes = []
        for mid, content in rows:
            h = content_hash(content)
            if h in hash_map:
                norm_dupes.append((mid, content[:50], hash_map[h]))
            else:
                hash_map[h] = mid

        if norm_dupes:
            print(f"  ⚠️  发现 {len(norm_dupes)} 条标准化重复（emoji 差异）")
            for mid, preview, orig_id in norm_dupes[:5]:
                print(f"     ID {mid}: \"{preview}...\" (重复 ID {orig_id})")
            issues.append(f"标准化重复: {len(norm_dupes)} 条")
            if fix:
                ids = [d[0] for d in norm_dupes]
                ph = ",".join("?" * len(ids))
                conn.execute(f"DELETE FROM memories WHERE id IN ({ph})", ids)
                conn.commit()
                print(f"  🔧 已修复：删除 {len(ids)} 条标准化重复")
        else:
            print(f"  ✅ 无标准化重复")

        conn.close()

    # 3. 索引一致性
    if index_db.exists():
        print("\n🔍 索引一致性")
        conn = sqlite3.connect(str(index_db), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        vec_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        conn.close()

        if vec_count == doc_count:
            print(f"  ✅ 文档数 = 向量数 = {doc_count}")
        elif vec_count == 0:
            print(f"  ⚠️  {doc_count} 文档但 0 向量，需要 --embed")
            issues.append("缺少语义向量")
        else:
            print(f"  ⚠️  文档 {doc_count} ≠ 向量 {vec_count}")
            issues.append(f"索引不一致: {doc_count} docs vs {vec_count} vecs")

    # 4. Markdown 格式检查
    print("\n📄 Markdown 格式")
    for md_file in sorted(MEMORY_DIR.glob("????-??-??.md")):
        content = md_file.read_text(encoding="utf-8")
        first_line = content.split("\n")[0] if content else ""
        date_in_name = re.search(r"(\d{4}-\d{2}-\d{2})", md_file.name)
        if date_in_name and date_in_name.group(1) not in first_line:
            print(f"  ⚠️  {md_file.name}: 文件头日期不匹配 ({first_line[:30]})")
            issues.append(f"日期不匹配: {md_file.name}")
            if fix:
                correct_date = date_in_name.group(1)
                lines = content.split("\n")
                lines[0] = f"# {correct_date} - 会话记录"
                md_file.write_text("\n".join(lines), encoding="utf-8")
                print(f"  🔧 已修复")
        else:
            print(f"  ✅ {md_file.name}")

    # 5. 数量对比
    if db_path.exists():
        print("\n📊 数量对比")
        md_count = 0
        for md_file in MEMORY_DIR.glob("????-??-??.md"):
            md_count += sum(1 for l in md_file.read_text("utf-8").split("\n")
                           if l.strip().startswith("- "))
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        db_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conn.close()
        diff = abs(md_count - db_count)
        ratio = min(md_count, db_count) / max(md_count, db_count) if max(md_count, db_count) > 0 else 1
        print(f"  Markdown: {md_count} 条")
        print(f"  SQLite:   {db_count} 条")
        print(f"  一致率:   {ratio:.0%}")
        if ratio < 0.8:
            issues.append(f"数据差异大: md={md_count} vs db={db_count}")

    # 总结
    print(f"\n{'=' * 55}")
    if issues:
        print(f"⚠️  发现 {len(issues)} 个问题:")
        for i in issues:
            print(f"  - {i}")
        if not fix:
            print(f"\n运行 --fix 自动修复")
    else:
        print("✅ 一切健康！")
    print(f"{'=' * 55}")
    return len(issues)


def main():
    parser = argparse.ArgumentParser(description="记忆系统健康检查")
    parser.add_argument("--agent", default="demo-agent")
    parser.add_argument("--fix", action="store_true", help="自动修复发现的问题")
    args = parser.parse_args()
    check(args.agent, args.fix)


if __name__ == "__main__":
    main()
