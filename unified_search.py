#!/usr/bin/env python3
"""
unified_search.py - 统一搜索

同时搜索 markdown 文件、SQLite 知识系统和语义向量索引。

用法:
    python3 scripts/unified_search.py '关键词'
    python3 scripts/unified_search.py '如何改进记忆系统' --semantic
    python3 scripts/unified_search.py '记忆系统' --limit 5
    python3 scripts/unified_search.py '知识' --source knowledge --agent demo-agent
    python3 scripts/unified_search.py '知识' --source markdown
"""

import argparse
import json
import math
import sqlite3
import struct
import subprocess
from pathlib import Path
import sys
from typing import List, Dict, Optional

try:
    import jieba
    jieba.setLogLevel(20)
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False

from path_utils import resolve_workspace

WORKSPACE = resolve_workspace()
MEMORY_DIR = WORKSPACE / "memory"
INDEX_DB = WORKSPACE / "data" / "index" / "memory_index.db"
OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "bge-m3"


def search_markdown(query: str, limit: int = 10) -> List[Dict]:
    """搜索 markdown：先用 FTS5（jieba 分词），无结果退回 grep"""
    # 尝试 FTS5
    fts_results = search_fts(query, limit)
    if fts_results:
        return fts_results
    # Fallback: grep
    return search_grep(query, limit)


def search_fts(query: str, limit: int = 10) -> List[Dict]:
    """FTS5 全文搜索（需要索引 + jieba 分词）"""
    if not INDEX_DB.exists():
        return []
    # 分词
    if HAS_JIEBA:
        tokens = " ".join(jieba.cut_for_search(query))
    else:
        tokens = query

    conn = sqlite3.connect(str(INDEX_DB), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT d.path, d.line_start, d.content, d.type, d.date, rank
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (tokens, limit)).fetchall()
        return [{
            "source": "fts5",
            "path": r["path"],
            "line": r["line_start"],
            "content": r["content"][:300],
            "type": r["type"],
            "date": r["date"],
            "score": round(abs(r["rank"]), 4),
        } for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def search_grep(query: str, limit: int = 10) -> List[Dict]:
    """Grep 文件搜索（fallback）"""
    results = []
    search_paths = []

    memory_md = WORKSPACE / "MEMORY.md"
    if memory_md.exists():
        search_paths.append(memory_md)
    if MEMORY_DIR.exists():
        search_paths.extend(sorted(MEMORY_DIR.rglob("*.md")))

    for filepath in search_paths:
        if not filepath.exists():
            continue
        try:
            lines = filepath.read_text(encoding="utf-8").split("\n")
            rel_path = str(filepath.relative_to(WORKSPACE))
            covered_until = 0  # 去重：跳过已覆盖的行范围
            for i, line in enumerate(lines, 1):
                if i <= covered_until:
                    continue
                if query.lower() in line.lower():
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    context = "\n".join(lines[start:end]).strip()
                    covered_until = end  # 标记这段已覆盖
                    results.append({
                        "source": "markdown",
                        "path": rel_path,
                        "line": i,
                        "content": context[:300],
                        "score": 1.0,
                    })
                    if len(results) >= limit:
                        return results
        except Exception:
            continue
    return results


def search_knowledge(query: str, agent_name: str = "demo-agent",
                     limit: int = 10) -> List[Dict]:
    """搜索 SQLite 知识系统"""
    db_path = WORKSPACE / "data" / agent_name / "memory" / "memory_stream.db"
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT id, content, memory_type, importance, created_at
            FROM memories
            WHERE content LIKE ?
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
        """, (f"%{query}%", limit)).fetchall()

        return [{
            "source": "knowledge",
            "id": row["id"],
            "content": row["content"][:200],
            "type": row["memory_type"],
            "importance": row["importance"],
            "date": str(row["created_at"])[:10],
            "score": row["importance"] / 10.0,
        } for row in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_embedding(text: str, prefix: str = "search_query: ") -> Optional[List[float]]:
    """使用 Ollama 生成嵌入向量，查询用 search_query: 前缀"""
    try:
        result = subprocess.run(
            ["curl", "-s", OLLAMA_URL,
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"model": EMBED_MODEL, "prompt": prefix + text[:500]})],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if "embedding" in data:
                return data["embedding"]
    except Exception:
        pass
    return None


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_semantic(query: str, limit: int = 10) -> List[Dict]:
    """语义搜索（需要 Ollama + 已建索引的向量）"""
    if not INDEX_DB.exists():
        print("  ⚠️  索引不存在，请先运行: python3 scripts/memory_indexer.py --full --embed")
        return []

    query_vec = get_embedding(query)
    if not query_vec:
        print("  ⚠️  Ollama 不可用，退回关键词搜索")
        return search_markdown(query, limit)

    conn = sqlite3.connect(str(INDEX_DB), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT d.id, d.path, d.line_start, d.line_end, d.content, d.type, d.date,
                   e.vector
            FROM embeddings e
            JOIN documents d ON d.id = e.doc_id
        """).fetchall()

        if not rows:
            print("  ⚠️  没有语义向量，请运行: python3 scripts/memory_indexer.py --full --embed")
            return search_markdown(query, limit)

        scored = []
        for row in rows:
            vec_bytes = row["vector"]
            dim = len(vec_bytes) // 4
            doc_vec = list(struct.unpack(f"{dim}f", vec_bytes))
            sim = cosine_similarity(query_vec, doc_vec)
            scored.append((sim, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for sim, row in scored[:limit]:
            results.append({
                "source": "semantic",
                "path": row["path"],
                "line": row["line_start"],
                "content": row["content"][:200],
                "type": row["type"],
                "date": row["date"],
                "score": round(sim, 4),
            })
        return results
    finally:
        conn.close()


def format_results(results: List[Dict]) -> str:
    if not results:
        return "没有找到匹配结果。"

    lines = []
    # 按 source 分组
    by_source = {}
    for r in results:
        src = r["source"]
        if src not in by_source:
            by_source[src] = []
        by_source[src].append(r)

    source_labels = {
        "markdown": "📂 Markdown (grep)",
        "fts5": "📂 Markdown (FTS5)",
        "knowledge": "🧠 知识系统",
        "semantic": "🔮 语义搜索",
    }

    for src, items in by_source.items():
        label = source_labels.get(src, src)
        lines.append(f"{label} ({len(items)} 条)")
        lines.append("-" * 40)
        for i, r in enumerate(items, 1):
            header = f"  [{i}]"
            if r.get("path"):
                header += f" {r['path']}:{r.get('line', '?')}"
            if r.get("type") and r["type"] != "unknown":
                header += f" [{r['type']}]"
            if r.get("importance"):
                header += f" ★{r['importance']}"
            if r.get("date"):
                header += f" ({r['date']})"
            header += f"  score={r.get('score', '-')}"

            content = r["content"].replace("\n", "\n      ")
            lines.append(header)
            lines.append(f"      {content}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="统一记忆搜索")
    parser.add_argument("query", help="搜索关键词或自然语言查询")
    parser.add_argument("--semantic", action="store_true",
                        help="使用语义搜索（需要 Ollama + 向量索引）")
    parser.add_argument("--limit", "-n", type=int, default=10)
    parser.add_argument("--source", choices=["all", "markdown", "knowledge", "semantic"],
                        default="all", help="搜索范围")
    parser.add_argument("--agent", default="demo-agent")
    args = parser.parse_args()

    mode = "语义" if (args.semantic or args.source == "semantic") else "关键词"
    print(f"🔍 搜索: \"{args.query}\" (模式: {mode}, 范围: {args.source})\n")

    all_results = []

    if args.semantic or args.source == "semantic":
        print("🔮 语义搜索中...")
        all_results.extend(search_semantic(args.query, args.limit))
    else:
        if args.source in ("all", "markdown"):
            all_results.extend(search_markdown(args.query, args.limit))
        if args.source in ("all", "knowledge"):
            all_results.extend(search_knowledge(args.query, args.agent, args.limit))

    # 综合排序：按 score 降序，去除内容重复
    seen_content = set()
    deduped = []
    for r in sorted(all_results, key=lambda x: x.get("score", 0), reverse=True):
        # 取前 60 字符做去重 key
        key = r["content"][:60].strip()
        if key not in seen_content:
            seen_content.add(key)
            deduped.append(r)
    all_results = deduped[:args.limit]

    print(f"找到 {len(all_results)} 条结果:\n")
    print(format_results(all_results))


if __name__ == "__main__":
    main()
