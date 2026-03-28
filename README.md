# Unified Memory Skill

统一记忆技能 - 为 OpenClaw 提供记忆存储和搜索能力

## 功能

- 对话自动记录
- Markdown ↔ SQLite 双向同步
- FTS5 中文全文搜索
- 语义搜索（需要 Ollama）

## 安装

### 国内用户（推荐，快 50 倍）

```bash
git clone https://gitee.com/luoboask/unified-memory-skill.git
cd unified-memory-skill
```

### 海外用户

```bash
git clone https://github.com/luoboask/unified-memory-skill.git
cd unified-memory-skill
```

**💡 访问速度：**
- 🇨🇳 国内用户：使用 Gitee 源，速度快 50 倍
- 🌏 海外用户：使用 GitHub 源

## 使用

OpenClaw 会自动使用此技能。

## 依赖

- Python 3.10+
- jieba (可选)
- Ollama + bge-m3 (可选)
