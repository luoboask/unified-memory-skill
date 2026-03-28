#!/usr/bin/env python3
"""
path_utils.py - 统一路径解析工具

优先级：
1. EVO_WORKSPACE 环境变量
2. .install-config 配置文件
3. 从脚本位置推导（回退）

用法:
    from path_utils import resolve_workspace, resolve_agent_memory, resolve_data_dir
    
    WORKSPACE = resolve_workspace()
    MEMORY_DIR = resolve_agent_memory(args.agent)
    DATA_DIR = resolve_data_dir("index")
"""
import os
from pathlib import Path


def resolve_workspace() -> Path:
    """解析 Workspace 路径
    
    对于 unified-memory-skill (skill 仓库):
    - 脚本在根目录，workspace 就是当前目录
    
    对于 evo-agents (workspace 仓库):
    - 脚本在 scripts/core/，workspace 是 scripts/core/..
    
    优先级:
    1. EVO_WORKSPACE 或 WORKSPACE_ROOT 环境变量
    2. .install-config 配置文件
    3. 从脚本位置推导（回退）
    """
    # 1. 环境变量（最高优先级）
    env_path = os.environ.get("EVO_WORKSPACE") or os.environ.get("WORKSPACE_ROOT")
    if env_path:
        return Path(env_path)
    
    # 2. 配置文件
    script_dir = Path(__file__).resolve().parent
    config_file = script_dir / ".install-config"
    if config_file.exists():
        for line in config_file.read_text().splitlines():
            if line.startswith("workspace_path="):
                return Path(line.split("=", 1)[1].strip())
    
    # 3. 推导（回退）
    # 检查是否在 scripts/core/ 目录
    if script_dir.name == "core" and script_dir.parent.name == "scripts":
        return script_dir.parent.parent  # evo-agents
    else:
        return script_dir  # unified-memory-skill (skill 仓库)


def resolve_agent_memory(agent: str = None) -> Path:
    """解析 Agent 记忆目录
    
    Args:
        agent: Agent 名称，None 表示主 Agent
        
    Returns:
        Path: 记忆目录路径
    """
    workspace = resolve_workspace()
    if not agent:
        return workspace / "memory"
    
    # 支持多 Agent 模式：agents/<agent>/memory/
    agent_memory = workspace / "agents" / agent / "memory"
    if agent_memory.exists():
        return agent_memory
    
    # 回退到默认 memory/
    return workspace / "memory"


def resolve_data_dir(subdir: str = None) -> Path:
    """解析数据目录
    
    Args:
        subdir: 子目录名称（如 "index", "locks" 等）
        
    Returns:
        Path: 数据目录路径
    """
    workspace = resolve_workspace()
    data_dir = workspace / "data"
    return data_dir / subdir if subdir else data_dir


def resolve_script_dir(script_name: str = None) -> Path:
    """解析脚本目录
    
    Args:
        script_name: 脚本名称（可选）
        
    Returns:
        Path: 脚本目录或脚本文件路径
    """
    workspace = resolve_workspace()
    scripts_dir = workspace / "scripts"
    return scripts_dir / script_name if script_name else scripts_dir
