#!/usr/bin/env python3
"""
lock_utils.py - 并发锁工具

为所有脚本提供统一的文件锁和 SQLite WAL 模式支持。
"""

import fcntl
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from path_utils import resolve_workspace

WORKSPACE = resolve_workspace()
LOCK_DIR = WORKSPACE / "data" / ".locks"


@contextmanager
def file_lock(name: str):
    """命名文件锁，防止多个脚本同时运行冲突操作

    用法:
        with file_lock("bridge_sync"):
            # 同步操作
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lockfile = LOCK_DIR / f"{name}.lock"

    with open(lockfile, "w") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # 已有其他进程持锁，等待
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextmanager
def md_file_lock(filepath: Path):
    """锁住单个 markdown 文件

    用法:
        with md_file_lock(Path("memory/2026-03-25.md")) as f:
            content = f.read()
            f.seek(0); f.truncate()
            f.write(new_content)
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    if not filepath.exists():
        filepath.touch()

    f = open(filepath, "r+", encoding="utf-8")
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    try:
        yield f
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def open_db(db_path: Path, wal: bool = True) -> sqlite3.Connection:
    """打开 SQLite 数据库，默认启用 WAL 模式

    WAL 模式允许一个写入者和多个读取者并发，
    避免 'database is locked' 错误。
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)

    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")  # 10s 等待

    return conn
