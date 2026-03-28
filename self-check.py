#!/usr/bin/env python3
"""
self_check.py - Workspace 完整性自检 + 自动修复

检测 workspace 是否存在问题，帮助 Agent 自主发现问题并修复。

用法:
    python3 scripts/core/self_check.py              # 快速检查
    python3 scripts/core/self_check.py --full       # 完整检查
    python3 scripts/core/self_check.py --fix        # 自动修复
    python3 scripts/core/self_check.py --dry-run    # 预览修复（不实际修改）
    python3 scripts/core/self_check.py --report     # 生成报告
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 添加 core 目录到路径
# Skill 仓库脚本在根目录
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR  # 根目录就是 workspace

# 使用上面定义的 WORKSPACE


class Colors:
    """终端颜色"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class CheckResult:
    """检查结果"""
    def __init__(self, name: str, passed: bool, message: str = "", 
                 suggestion: str = "", severity: str = "info"):
        self.name = name
        self.passed = passed
        self.message = message
        self.suggestion = suggestion
        self.severity = severity  # info, warning, error
    
    def __str__(self):
        if self.passed:
            status = f"{Colors.GREEN}✅{Colors.RESET}"
        elif self.severity == "error":
            status = f"{Colors.RED}❌{Colors.RESET}"
        else:
            status = f"{Colors.YELLOW}⚠️{Colors.RESET}"
        
        return f"{status} {self.name}: {self.message}"


class WorkspaceChecker:
    """Workspace 完整性检查器"""
    
    def __init__(self, workspace: Path, verbose: bool = False, 
                 fix: bool = False, dry_run: bool = False):
        self.workspace = workspace
        self.verbose = verbose
        self.fix = fix
        self.dry_run = dry_run
        self.results: List[CheckResult] = []
        self.fixed_count = 0
        self.failed_fix_count = 0
    
    def check(self) -> List[CheckResult]:
        """执行所有检查"""
        print(f"{Colors.BOLD}🔍 Workspace 完整性检查{Colors.RESET}")
        print(f"📁 {self.workspace}\n")
        
        # 1. 目录结构检查
        self._check_directory_structure()
        
        # 2. 关键文件检查
        self._check_critical_files()
        
        # 3. 运行时数据检查（不应该存在的目录）
        self._check_runtime_data()
        
        # 4. Git 配置检查
        self._check_git_config()
        
        # 5. OpenClaw 注册检查
        self._check_openclaw_registration()
        
        # 6. 路径系统检查
        self._check_path_system()
        
        # 7. 技能完整性检查 - Skill 仓库跳过
        # self._check_skills()
        
        # 8. 数据库健康检查
        self._check_databases()
        
        # 如果需要修复
        if self.fix:
            self._fix_issues()
        
        # 打印摘要
        self._print_summary()
        
        return self.results
    
    def _check_directory_structure(self):
        """检查目录结构"""
        required_dirs = [
            # Skill 仓库不需要这些目录
            # ("scripts/core", "核心脚本目录"),
            # ("scripts/user", "用户脚本目录"),
            # ("skills", "技能目录"),
            ("docs", "文档目录"),
            ("memory", "记忆目录"),
            ("data", "数据目录"),
            ("config", "配置目录"),
            ("public", "知识库目录"),
        ]
        
        for dir_path, description in required_dirs:
            full_path = self.workspace / dir_path
            if full_path.exists():
                self.results.append(CheckResult(
                    f"目录：{dir_path}",
                    True,
                    f"{description} 存在"
                ))
            else:
                self.results.append(CheckResult(
                    f"目录：{dir_path}",
                    False,
                    f"{description} 不存在",
                    f"创建目录：mkdir -p {dir_path}",
                    "error"
                ))
    
    def _check_critical_files(self):
        """检查关键文件"""
        required_files = [
            ("README.md", "主文档"),
            ("SKILL.md", "技能说明"),
            ("path_utils.py", "路径工具"),
        ]
        
        for file_path, description in required_files:
            full_path = self.workspace / file_path
            if full_path.exists():
                self.results.append(CheckResult(
                    f"文件：{file_path}",
                    True,
                    f"{description} 存在"
                ))
            else:
                self.results.append(CheckResult(
                    f"文件：{file_path}",
                    False,
                    f"{description} 不存在",
                    "从 GitHub 重新克隆或恢复文件",
                    "error"
                ))
        
        # 检查 .install-config（可选）
        config_file = self.workspace / ".install-config"
        if config_file.exists():
            self.results.append(CheckResult(
                "文件：.install-config",
                True,
                "安装配置存在"
            ))
        else:
            self.results.append(CheckResult(
                "文件：.install-config",
                True,
                "未找到（首次安装后会自动创建）",
                severity="info"
            ))
    
    def _check_runtime_data(self):
        """检查运行时数据（不应该存在的目录）"""
        forbidden_dirs = [
            ("scripts/data", "脚本运行时数据目录"),
            ("scripts/memory", "脚本临时记忆目录"),
        ]
        
        for dir_path, description in forbidden_dirs:
            full_path = self.workspace / dir_path
            if full_path.exists():
                self.results.append(CheckResult(
                    f"异常目录：{dir_path}",
                    False,
                    f"{description} 不应该存在",
                    f"删除目录：rm -rf {dir_path}",
                    "warning"
                ))
            else:
                self.results.append(CheckResult(
                    f"异常目录：{dir_path}",
                    True,
                    f"{description} 不存在（正确）"
                ))
        
        # 检查 data/ 目录是否为空（应该只有 .gitkeep）
        data_dir = self.workspace / "data"
        if data_dir.exists():
            files = list(data_dir.iterdir())
            if len(files) > 1 or (len(files) == 1 and files[0].name != ".gitkeep"):
                self.results.append(CheckResult(
                    "目录：data/",
                    False,
                    f"data/ 目录包含运行时数据：{[f.name for f in files]}",
                    "这些文件不应该提交到 Git",
                    "warning"
                ))
            else:
                self.results.append(CheckResult(
                    "目录：data/",
                    True,
                    "data/ 目录干净"
                ))
    
    def _check_git_config(self):
        """检查 Git 配置"""
        git_dir = self.workspace / ".git"
        if git_dir.exists():
            self.results.append(CheckResult(
                "Git: .git 目录",
                True,
                "Git 仓库存在"
            ))
            
            # 检查 .gitignore
            gitignore = self.workspace / ".gitignore"
            if gitignore.exists():
                content = gitignore.read_text()
                if "scripts/data" in content or "scripts/memory" in content:
                    self.results.append(CheckResult(
                        "Git: .gitignore",
                        False,
                        ".gitignore 包含过时的排除规则",
                        "更新 .gitignore，移除 scripts/data 和 scripts/memory",
                        "warning"
                    ))
                else:
                    self.results.append(CheckResult(
                        "Git: .gitignore",
                        True,
                        ".gitignore 配置正确"
                    ))
            else:
                self.results.append(CheckResult(
                    "Git: .gitignore",
                    False,
                    ".gitignore 不存在",
                    "从 GitHub 恢复 .gitignore",
                    "error"
                ))
        else:
            self.results.append(CheckResult(
                "Git: .git 目录",
                False,
                "不是 Git 仓库",
                "使用 git init 初始化或重新克隆",
                "warning"
            ))
    
    def _check_openclaw_registration(self):
        """检查 OpenClaw 注册状态"""
        # 读取 .install-config 获取 agent 名称
        config_file = self.workspace / ".install-config"
        if not config_file.exists():
            self.results.append(CheckResult(
                "OpenClaw: 注册状态",
                True,
                "未检测到 .install-config（可能未安装）",
                severity="info"
            ))
            return
        
        config = {}
        for line in config_file.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()
        
        agent_name = config.get("agent_name", "unknown")
        
        # 检查 OpenClaw 配置
        openclaw_config = Path.home() / ".openclaw" / "openclaw.json"
        if openclaw_config.exists():
            try:
                data = json.loads(openclaw_config.read_text())
                agents = data.get("agents", {})
                if agent_name in agents:
                    self.results.append(CheckResult(
                        f"OpenClaw: {agent_name}",
                        True,
                        "已注册到 OpenClaw"
                    ))
                else:
                    self.results.append(CheckResult(
                        f"OpenClaw: {agent_name}",
                        False,
                        "未在 OpenClaw 中注册",
                        "运行 install.sh 重新注册",
                        "warning"
                    ))
            except Exception as e:
                self.results.append(CheckResult(
                    "OpenClaw: 配置",
                    False,
                    f"读取 openclaw.json 失败：{e}",
                    severity="warning"
                ))
        else:
            self.results.append(CheckResult(
                "OpenClaw: 配置",
                False,
                "openclaw.json 不存在",
                "安装 OpenClaw",
                "warning"
            ))
    
    def _check_path_system(self):
        """检查路径系统"""
        # 测试 path_utils 是否能正常工作
        try:
            from path_utils import resolve_workspace, resolve_agent_memory, resolve_data_dir
            
            ws = resolve_workspace()
            memory = resolve_agent_memory(None)
            data = resolve_data_dir()
            
            self.results.append(CheckResult(
                "路径系统：path_utils",
                True,
                f"路径解析正常 (workspace={ws.name})"
            ))
        except Exception as e:
            self.results.append(CheckResult(
                "路径系统：path_utils",
                False,
                f"路径解析失败：{e}",
                "检查 scripts/core/path_utils.py 是否存在",
                "error"
            ))
    
    def _check_skills(self):
        """检查技能完整性"""
        required_skills = [
            "memory-search",
            "rag",
            "self-evolution",
            "web-knowledge",
        ]
        
        for skill in required_skills:
            skill_dir = self.workspace / "skills" / skill
            if skill_dir.exists():
                # 检查关键文件
                skill_json = skill_dir / "skill.json"
                if skill_json.exists():
                    self.results.append(CheckResult(
                        f"技能：{skill}",
                        True,
                        "技能完整"
                    ))
                else:
                    self.results.append(CheckResult(
                        f"技能：{skill}",
                        False,
                        "缺少 skill.json",
                        "从 GitHub 恢复技能文件",
                        "warning"
                    ))
            else:
                self.results.append(CheckResult(
                    f"技能：{skill}",
                    False,
                    "技能目录不存在",
                    "从 GitHub 恢复技能",
                    "error"
                ))
    
    def _check_databases(self):
        """检查数据库健康"""
        # 检查索引数据库
        index_db = self.workspace / "data" / "index" / "memory_index.db"
        if index_db.exists():
            try:
                conn = sqlite3.connect(str(index_db))
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM documents")
                count = cursor.fetchone()[0]
                conn.close()
                
                self.results.append(CheckResult(
                    "数据库：memory_index.db",
                    True,
                    f"索引数据库正常 ({count} 文档)"
                ))
            except Exception as e:
                self.results.append(CheckResult(
                    "数据库：memory_index.db",
                    False,
                    f"数据库损坏：{e}",
                    "运行 memory_indexer.py --full 重建索引",
                    "warning"
                ))
        else:
            self.results.append(CheckResult(
                "数据库：memory_index.db",
                True,
                "索引数据库不存在（首次使用会创建）",
                severity="info"
            ))
    
    # =========================================================================
    # 自动修复功能
    # =========================================================================
    
    def _fix_issues(self):
        """自动修复可修复的问题"""
        print(f"\n{Colors.BOLD}🔧 开始自动修复...{Colors.RESET}\n")
        
        fixable = [r for r in self.results if not r.passed]
        
        if not fixable:
            print(f"{Colors.GREEN}✅ 没有需要修复的问题{Colors.RESET}\n")
            return
        
        for result in fixable:
            fixed = self._try_fix(result)
            if fixed:
                self.fixed_count += 1
                result.passed = True
                result.message = f"已修复：{result.message}"
            else:
                self.failed_fix_count += 1
    
    def _try_fix(self, result: CheckResult) -> bool:
        """尝试修复单个问题"""
        name = result.name.lower()
        
        # 1. 创建缺失的目录
        if name.startswith("目录："):
            dir_path = name.replace("目录：", "").strip()
            return self._fix_create_directory(dir_path)
        
        # 2. 删除不应该存在的目录
        if name.startswith("异常目录："):
            dir_path = name.replace("异常目录：", "").strip()
            return self._fix_delete_directory(dir_path)
        
        # 3. 创建缺失的 .gitkeep 文件
        if "data/" in name and "包含运行时数据" in result.message:
            return self._fix_clean_data_directory()
        
        # 4. 重建索引数据库
        if "数据库损坏" in result.message or "memory_indexer" in result.suggestion:
            return self._fix_rebuild_index()
        
        # 其他问题无法自动修复
        print(f"  ⚠️  无法自动修复：{result.name}")
        print(f"     建议：{result.suggestion}\n")
        return False
    
    def _fix_create_directory(self, dir_path: str) -> bool:
        """创建缺失的目录"""
        full_path = self.workspace / dir_path
        
        if self.dry_run:
            print(f"  📝 [预览] 创建目录：{dir_path}")
            return True
        
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            # 如果是空目录，创建 .gitkeep
            gitkeep = full_path / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.touch()
            
            print(f"  {Colors.GREEN}✅ 已创建目录：{dir_path}{Colors.RESET}")
            return True
        except Exception as e:
            print(f"  {Colors.RED}❌ 创建目录失败：{e}{Colors.RESET}")
            return False
    
    def _fix_delete_directory(self, dir_path: str) -> bool:
        """删除不应该存在的目录"""
        full_path = self.workspace / dir_path
        
        if not full_path.exists():
            return True
        
        if self.dry_run:
            print(f"  📝 [预览] 删除目录：{dir_path}")
            return True
        
        try:
            shutil.rmtree(full_path)
            print(f"  {Colors.GREEN}✅ 已删除目录：{dir_path}{Colors.RESET}")
            return True
        except Exception as e:
            print(f"  {Colors.RED}❌ 删除目录失败：{e}{Colors.RESET}")
            return False
    
    def _fix_clean_data_directory(self) -> bool:
        """清理 data/ 目录，只保留 .gitkeep"""
        data_dir = self.workspace / "data"
        
        if self.dry_run:
            print(f"  📝 [预览] 清理 data/ 目录")
            return True
        
        try:
            for item in data_dir.iterdir():
                if item.name != ".gitkeep" and item.name != "README.md":
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            
            print(f"  {Colors.GREEN}✅ 已清理 data/ 目录{Colors.RESET}")
            return True
        except Exception as e:
            print(f"  {Colors.RED}❌ 清理 data/ 失败：{e}{Colors.RESET}")
            return False
    
    def _fix_rebuild_index(self) -> bool:
        """重建索引数据库"""
        indexer_script = self.workspace / "scripts" / "core" / "memory_indexer.py"
        
        if not indexer_script.exists():
            print(f"  {Colors.RED}❌ memory_indexer.py 不存在{Colors.RESET}")
            return False
        
        if self.dry_run:
            print(f"  📝 [预览] 重建索引数据库")
            return True
        
        try:
            print(f"  🔄 运行 memory_indexer.py --full...")
            result = subprocess.run(
                [sys.executable, str(indexer_script), "--full"],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print(f"  {Colors.GREEN}✅ 索引重建成功{Colors.RESET}")
                return True
            else:
                print(f"  {Colors.RED}❌ 索引重建失败：{result.stderr}{Colors.RESET}")
                return False
        except subprocess.TimeoutExpired:
            print(f"  {Colors.RED}❌ 索引重建超时{Colors.RESET}")
            return False
        except Exception as e:
            print(f"  {Colors.RED}❌ 索引重建失败：{e}{Colors.RESET}")
            return False
    
    def _print_summary(self):
        """打印摘要"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}📊 检查摘要{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        errors = sum(1 for r in self.results if not r.passed and r.severity == "error")
        warnings = sum(1 for r in self.results if not r.passed and r.severity == "warning")
        
        print(f"总检查项：{total}")
        print(f"{Colors.GREEN}✅ 通过：{passed}{Colors.RESET}")
        print(f"{Colors.RED}❌ 失败：{failed}{Colors.RESET}")
        print(f"  - 错误：{errors}")
        print(f"  - 警告：{warnings}")
        
        # 显示修复结果
        if self.fix:
            print(f"\n{Colors.BOLD}🔧 修复结果:{Colors.RESET}")
            if self.fixed_count > 0:
                print(f"{Colors.GREEN}✅ 已修复：{self.fixed_count} 个问题{Colors.RESET}")
            if self.failed_fix_count > 0:
                print(f"{Colors.YELLOW}⚠️  无法修复：{self.failed_fix_count} 个问题（需要手动处理）{Colors.RESET}")
        
        if errors > 0 and not self.fix:
            print(f"\n{Colors.RED}⚠️  发现严重问题，需要立即修复！{Colors.RESET}")
            print(f"{Colors.BLUE}💡 提示：运行 --fix 自动修复可修复的问题{Colors.RESET}")
        elif warnings > 0 and not self.fix:
            print(f"\n{Colors.YELLOW}⚠️  发现警告，建议修复{Colors.RESET}")
            print(f"{Colors.BLUE}💡 提示：运行 --fix 自动修复可修复的问题{Colors.RESET}")
        elif self.fix:
            if self.failed_fix_count == 0:
                print(f"\n{Colors.GREEN}✅ 所有问题已修复！{Colors.RESET}")
            else:
                print(f"\n{Colors.YELLOW}⚠️  还有问题需要手动处理{Colors.RESET}")
        else:
            print(f"\n{Colors.GREEN}✅ Workspace 状态良好！{Colors.RESET}")
        
        # 显示失败项
        failed_results = [r for r in self.results if not r.passed]
        if failed_results:
            print(f"\n{Colors.BOLD}📋 问题列表:{Colors.RESET}")
            for result in failed_results:
                print(f"\n{result}")
                if result.suggestion:
                    print(f"   💡 建议：{result.suggestion}")
    
    def generate_report(self) -> str:
        """生成 JSON 报告"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "workspace": str(self.workspace),
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "errors": sum(1 for r in self.results if not r.passed and r.severity == "error"),
            "warnings": sum(1 for r in self.results if not r.passed and r.severity == "warning"),
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "suggestion": r.suggestion,
                    "severity": r.severity
                }
                for r in self.results
            ]
        }
        return json.dumps(report, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Workspace 完整性自检")
    parser.add_argument("--full", action="store_true", help="完整检查（包括所有可选检查）")
    parser.add_argument("--fix", action="store_true", help="自动修复可修复的问题")
    parser.add_argument("--dry-run", action="store_true", help="预览修复（不实际修改）")
    parser.add_argument("--report", action="store_true", help="生成 JSON 报告")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    args = parser.parse_args()
    
    checker = WorkspaceChecker(
        WORKSPACE, 
        verbose=args.verbose,
        fix=args.fix,
        dry_run=args.dry_run
    )
    results = checker.check()
    
    if args.report:
        print(f"\n{Colors.BOLD}📄 JSON 报告:{Colors.RESET}")
        print(checker.generate_report())
    
    # 返回错误码
    errors = sum(1 for r in results if not r.passed and r.severity == "error")
    sys.exit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()
