#!/bin/bash
# install.sh - unified-memory-skill 一键安装
# 
# 用法:
#   推荐（国内）：curl -fsSL https://gitee.com/luoboask/unified-memory-skill/raw/master/install.sh | bash -s
#   海外：curl -fsSL https://raw.githubusercontent.com/luoboask/unified-memory-skill/master/install.sh | bash -s

set -e

WORKSPACE_ROOT="${1:-$HOME/.openclaw/skills/unified-memory}"

# 多个下载源（自动选择最快的）
SOURCES=(
  "https://gitee.com/luoboask/unified-memory-skill/raw/master"
  "https://raw.githubusercontent.com/luoboask/unified-memory-skill/master"
)

echo "╔════════════════════════════════════════════════════════╗"
echo "║     unified-memory 安装                                 ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "📦 技能：unified-memory"
echo "📁 位置：$WORKSPACE_ROOT"
echo ""

# 克隆技能（自动选择最快的源）
echo "📥 克隆技能..."
if [ -d "$WORKSPACE_ROOT" ]; then
    echo "⚠️  技能已存在，更新中..."
    cd "$WORKSPACE_ROOT"
    git pull origin master >/dev/null 2>&1 || true
else
    CLONE_SUCCESS=false
    for SOURCE in "${SOURCES[@]}"; do
        if [[ "$SOURCE" == *"gitee.com"* ]]; then
            GIT_URL="https://gitee.com/luoboask/unified-memory-skill.git"
        else
            GIT_URL="https://github.com/luoboask/unified-memory-skill.git"
        fi
        
        echo "   尝试：$GIT_URL"
        if git clone --depth 1 "$GIT_URL" "$WORKSPACE_ROOT" 2>/dev/null; then
            echo "   ✅ 成功：$GIT_URL"
            CLONE_SUCCESS=true
            break
        fi
    done
    
    if [ "$CLONE_SUCCESS" = false ]; then
        echo "❌ 所有源都失败，请检查网络连接"
        exit 1
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
