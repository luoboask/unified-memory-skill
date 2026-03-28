#!/usr/bin/env python3
"""
session_recorder.py - 会话记录器

将对话事件写入 memory/YYYY-MM-DD.md，按类型分组。
支持文件锁防并发写入冲突。

用法:
    python3 scripts/session_recorder.py -t event -c '记忆系统改造完成'
    python3 scripts/session_recorder.py -t decision -c '采用统一架构' --sync
    python3 scripts/session_recorder.py -b '[{"type":"event","content":"A"},{"type":"learning","content":"B"}]' --sync
"""

import argparse
import fcntl
import json
import re
from datetime import datetime
from pathlib import Path

from path_utils import resolve_workspace

WORKSPACE = resolve_workspace()
MEMORY_DIR = WORKSPACE / "memory"

TYPE_MAP = {
    "event":      ("📌 事件",),
    "decision":   ("🔨 决定",),
    "learning":   ("📚 学习",),
    "reflection": ("💭 反思",),
    "todo":       ("☐ 待办",),
}

VALID_TYPES = list(TYPE_MAP.keys())


def get_today_file() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return MEMORY_DIR / f"{today}.md"


def ensure_daily_file(filepath: Path) -> str:
    """确保文件存在且有正确的标题头"""
    # 从文件名提取日期
    match = re.search(r"(\d{4}-\d{2}-\d{2})", filepath.name)
    date_str = match.group(1) if match else datetime.now().strftime("%Y-%m-%d")
    expected_header = f"# {date_str} - 会话记录"

    filepath.parent.mkdir(parents=True, exist_ok=True)

    if filepath.exists():
        content = filepath.read_text(encoding="utf-8")
        # 检查标题是否完整
        if content.strip() and content.strip().startswith("#"):
            return content
        # 文件存在但标题损坏/缺失 → 修复标题
        if content.strip():
            # 有内容但没标题，加上标题
            return f"{expected_header}\n\n{content.lstrip()}"
        # 文件为空或只有空白
        pass

    # 创建新文件
    header = f"{expected_header}\n\n"
    filepath.write_text(header, encoding="utf-8")
    return header


def append_to_section(content: str, section_title: str, entry: str) -> str:
    lines = content.split("\n")
    pattern = rf"^## {re.escape(section_title)}"

    section_start = -1
    for i, line in enumerate(lines):
        if re.match(pattern, line):
            section_start = i
            break

    timestamp = datetime.now().strftime("%H:%M")
    new_line = f"- [{timestamp}] {entry}"

    if section_start == -1:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"## {section_title}")
        lines.append("")
        lines.append(new_line)
        lines.append("")
    else:
        insert_pos = len(lines)
        for i in range(section_start + 1, len(lines)):
            if lines[i].startswith("## "):
                insert_pos = i
                break
        while insert_pos > 0 and not lines[insert_pos - 1].strip():
            insert_pos -= 1
        lines.insert(insert_pos, new_line)

    return "\n".join(lines)


def record(entry_type: str, content: str, date: str = None, sync: bool = False) -> str:
    if entry_type not in VALID_TYPES:
        raise ValueError(f"无效类型: {entry_type}，可选: {VALID_TYPES}")

    filepath = MEMORY_DIR / f"{date}.md" if date else get_today_file()
    section_title = TYPE_MAP[entry_type][0]

    # 用文件锁防止并发写入冲突
    # 锁住 md 文件本身，确保 read-modify-write 原子性
    filepath.parent.mkdir(parents=True, exist_ok=True)
    # 确保文件存在
    if not filepath.exists():
        # 先创建空文件
        match = re.search(r"(\d{4}-\d{2}-\d{2})", filepath.name)
        date_str = match.group(1) if match else datetime.now().strftime("%Y-%m-%d")
        filepath.write_text(f"# {date_str} - 会话记录\n\n", encoding="utf-8")

    with open(filepath, "r+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            file_content = f.read()
            # 检查标题完整性
            if not file_content.strip() or not file_content.strip().startswith("#"):
                match = re.search(r"(\d{4}-\d{2}-\d{2})", filepath.name)
                date_str = match.group(1) if match else datetime.now().strftime("%Y-%m-%d")
                if file_content.strip():
                    file_content = f"# {date_str} - 会话记录\n\n{file_content.lstrip()}"
                else:
                    file_content = f"# {date_str} - 会话记录\n\n"

            if content in file_content:
                return f"⏭️  跳过（已存在）: {content[:50]}..."

            updated = append_to_section(file_content, section_title, content)
            f.seek(0)
            f.truncate()
            f.write(updated)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    result = f"✅ 已记录 [{entry_type}]: {content[:80]}"

    if sync:
        result = _do_sync(result)

    return result


def _do_sync(result: str) -> str:
    """后台异步执行同步 + 索引更新，不阻塞主流程"""
    import subprocess
    import os

    bridge = WORKSPACE / "scripts" / "bridge" / "bridge_sync.py"
    indexer = WORKSPACE / "scripts" / "memory_indexer.py"

    # fork 子进程在后台执行，主进程立即返回
    pid = os.fork()
    if pid == 0:
        # 子进程：静默执行同步和索引
        try:
            os.setsid()  # 脱离终端
            if bridge.exists():
                subprocess.run(
                    ["python3", str(bridge), "--agent", "demo-agent", "--days", "1"],
                    capture_output=True, timeout=30, cwd=str(WORKSPACE)
                )
            if indexer.exists():
                subprocess.run(
                    ["python3", str(indexer), "--incremental", "--embed"],
                    capture_output=True, timeout=60, cwd=str(WORKSPACE)
                )
        except Exception:
            pass
        finally:
            os._exit(0)
    else:
        # 父进程：立即返回
        result += " (+ 后台同步中)"

    return result


def batch_record(entries: list, sync: bool = False) -> str:
    """批量记录"""
    results = []
    for entry in entries:
        r = record(entry["type"], entry["content"], entry.get("date"), sync=False)
        results.append(r)

    if sync:
        results.append(_do_sync("🔄"))

    return "\n".join(results)


def main():
    parser = argparse.ArgumentParser(description="会话记录器")
    parser.add_argument("--type", "-t", choices=VALID_TYPES)
    parser.add_argument("--content", "-c")
    parser.add_argument("--batch", "-b",
                        help='批量 JSON: \'[{"type":"event","content":"xxx"}]\'')
    parser.add_argument("--date", "-d", default=None)
    parser.add_argument("--sync", "-s", action="store_true")
    args = parser.parse_args()

    if args.batch:
        entries = json.loads(args.batch)
        print(batch_record(entries, args.sync))
    elif args.type and args.content:
        print(record(args.type, args.content, args.date, args.sync))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
