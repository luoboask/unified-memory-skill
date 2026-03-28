---
name: unified-memory
description: 统一记忆系统 - Markdown + SQLite 双向同步，支持中文搜索
version: 1.0.0
tags: memory, search, sqlite
---

# Unified Memory Skill

为 OpenClaw Agent 提供记忆能力。

## 功能

- 对话自动记录
- Markdown ↔ SQLite 双向同步
- FTS5 中文全文搜索
- 语义搜索（需要 Ollama）

## 文件

- `session_recorder.py` - 记录对话
- `memory_indexer.py` - 创建索引
- `unified_search.py` - 搜索记忆
- `bridge_sync.py` - 双向同步
- `path_utils.py` - 路径工具

## 依赖

- Python 3.10+
- jieba (可选，中文分词)
- Ollama + bge-m3 (可选，语义搜索)
