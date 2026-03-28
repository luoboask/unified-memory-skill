#!/bin/bash
# install.sh - unified-memory-skill 一键安装
# 
# 用法:
#   推荐（国内）：curl -fsSL https://gitee.com/luoboask/unified-memory-skill/raw/master/install.sh | bash -s
#   海外：curl -fsSL https://raw.githubusercontent.com/luoboask/unified-memory-skill/master/install.sh | bash -s

set -e

WORKSPACE_ROOT="${1:-$HOME/.openclaw/skills/unified-memory}"

# 检测脚本来源，自动选择对应 Git 源
if [[ "${BASH_SOURCE[0]}" == *"gitee.com"* ]] || [[ "$0" == *"gitee.com"* ]]; then
    # 从 Gitee 下载，使用 Gitee Git 源
    GIT_URL="https://gitee.com/luoboask/unified-memory-skill.git"
    SOURCE_NAME="Gitee"
else
    # 从 GitHub 下载，优先尝试 Gitee（国内更快）
    GIT_URL="https://gitee.com/luoboask/unified-memory-skill.git"
    SOURCE_NAME="Gitee (优先)"
fi

echo "╔════════════════════════════════════════════════════════╗"
echo "║     unified-memory 安装                                 ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "📦 技能：unified-memory"
echo "📁 位置：$WORKSPACE_ROOT"
echo ""

# 克隆技能
echo "📥 克隆技能..."
if [ -d "$WORKSPACE_ROOT" ]; then
    echo "⚠️  技能已存在，更新中..."
    cd "$WORKSPACE_ROOT"
    git pull origin master >/dev/null 2>&1 || true
else
    echo "   源：$SOURCE_NAME ($GIT_URL)"
    
    if ! git clone --depth 1 "$GIT_URL" "$WORKSPACE_ROOT" 2>/dev/null; then
        # Gitee 失败时尝试 GitHub
        if [[ "$GIT_URL" == *"gitee.com"* ]]; then
            echo "   ⚠️  Gitee 失败，尝试 GitHub..."
            GIT_URL="https://github.com/luoboask/unified-memory-skill.git"
            if ! git clone --depth 1 "$GIT_URL" "$WORKSPACE_ROOT" 2>/dev/null; then
                echo "❌ 所有源都失败，请检查网络连接"
                exit 1
            fi
        else
            echo "❌ 克隆失败，请检查网络连接"
            exit 1
        fi
    fi
    
    cd "$WORKSPACE_ROOT"
fi

# 清理不必要的文件
echo "🧹 清理文件..."
rm -f LICENSE CLAWHUB_UPLOAD.md publish-to-clawhub.sh 2>/dev/null || true
echo "   ✅ 完成"

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║  ✅ 安装完成！                                          ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "📚 位置：$WORKSPACE_ROOT"
echo "📖 文档：README.md, SKILL.md"
echo ""
