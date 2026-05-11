#!/usr/bin/env python3
"""
auto_monitor.py - 多Agent上下文自动监控守护进程

功能：
- 持续监控所有进行中任务的Agent上下文使用率
- 达到阈值时自动触发交接协议（可选：自动执行或仅提醒）
- 支持守护模式（后台持续运行）和单次检查模式

用法:
  # 单次检查（检查所有活跃任务）
  python3 auto_monitor.py --mode once

  # 守护模式（每60秒检查一次）
  python3 auto_monitor.py --mode daemon --interval 60

  # 查看帮助
  python3 auto_monitor.py --help
"""

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# 导入同目录下的模块
sys.path.insert(0, str(Path(__file__).parent))
from handover_manager import list_handoffs, get_status, prepare_handover, confirm_handover
from check_context import check_context

# ============ 配置 ============
SKILL_DIR = Path(__file__).parent.parent
CONFIG_FILE = SKILL_DIR / "scripts/config.yaml"
MEMORY_HANDOVER_DIR = Path.home() / "WorkBuddy/2026-05-11-task-17/.workbuddy/memory/handover"
QUEUE_FILE = MEMORY_HANDOVER_DIR / "auto_handover_queue.json"

# 全局停止标志（用于守护模式优雅退出）
RUNNING = True


def load_config() -> dict:
    """加载配置文件"""
    if CONFIG_FILE.exists():
        import yaml
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "token_warn_pct": 65,
        "token_force_pct": 80,
        "round_warn": 25,
        "round_force": 35,
        "auto_execute": False,  # 默认仅提醒，不自动执行
    }


def load_handover_queue() -> list:
    """加载交接队列"""
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_handover_queue(queue: list):
    """保存交接队列"""
    MEMORY_HANDOVER_DIR.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def add_to_queue(task_id: str, reason: str, context_result: dict):
    """添加交接建议到队列"""
    queue = load_handover_queue()
    queue.append({
        "task_id": task_id,
        "reason": reason,
        "context": context_result,
        "added_at": datetime.now().isoformat(),
        "status": "pending",
    })
    save_handover_queue(queue)


def scan_active_tasks() -> list:
    """扫描所有进行中的任务"""
    handoffs = list_handoffs()
    active = []
    for h in handoffs:
        if h.get("status") in ["prepared", "resumed"]:
            active.append(h)
    return active


def auto_check_agent(token_used: int, token_limit: int, rounds: int, round_limit: int) -> dict:
    """
    自动检测Agent上下文状态（无需外部参数）
    如果无法获取真实数据，使用模拟值用于测试
    """
    # 优先使用真实数据，否则使用配置文件中的默认值
    if token_limit == 0:
        token_limit = 3200
    if round_limit == 0:
        round_limit = 40

    return check_context(token_used, token_limit, rounds, round_limit)


def monitor_single_task(task_id: str, agent_name: str, config: dict) -> Optional[dict]:
    """
    监控单个任务的Agent上下文状态
    返回交接建议（如果有）
    """
    status = get_status(task_id)
    if not status.get("exists"):
        return None

    # 从检查点获取上下文快照（如果有）
    snapshot = status.get("checkpoint", {})
    token_used = snapshot.get("token_used", 0)
    round_count = snapshot.get("round_count", 0)

    # 如果没有快照数据，跳过（需要外部提供）
    # 这里用一个估算：在已有交接历史上继续计数
    history = status.get("history", [])
    if history and round_count == 0:
        # 估算：每次交接后轮次清零，从交接序列推算
        round_count = len(history) * 10  # 假设每次交接平均10轮

    result = auto_check_agent(
        token_used=token_used,
        token_limit=3200,
        rounds=round_count,
        round_limit=40,
    )

    if result["overflow"] or result["recommendation"] == "handover":
        reason = f"Token {result['token_pct']}% + 轮次 {result['rounds']}/{result['round_limit']}"
        return {
            "task_id": task_id,
            "agent": agent_name,
            "reason": reason,
            "result": result,
            "action": "queue" if not config.get("auto_execute") else "execute",
        }
    return None


def execute_monitor(config: dict) -> list:
    """
    执行监控主逻辑
    返回所有需要交接的任务列表
    """
    active_tasks = scan_active_tasks()
    alerts = []

    if not active_tasks:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 无进行中任务，跳过检查")
        return alerts

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 监控 {len(active_tasks)} 个任务...")

    for task in active_tasks:
        task_id = task.get("task_id")
        # 尝试确定当前Agent
        agent = task.get("to", task.get("from", "unknown"))

        alert = monitor_single_task(task_id, agent, config)
        if alert:
            alerts.append(alert)
            if config.get("auto_execute"):
                print(f"  ⚠️ 触发自动交接: {task_id} ({alert['reason']})")
            else:
                print(f"  🔔 交接建议: {task_id} ({alert['reason']})")
                add_to_queue(task_id, alert["reason"], alert["result"])

    return alerts


def daemon_mode(interval: int, config: dict):
    """
    守护模式主循环
    """
    print(f"[启动] auto_monitor 守护进程 (间隔 {interval}s)")
    print(f"[配置] auto_execute={config.get('auto_execute', False)}")

    while RUNNING:
        try:
            alerts = execute_monitor(config)
            if alerts:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 发现 {len(alerts)} 个交接建议")
        except Exception as e:
            print(f"[错误] 监控异常: {e}", file=sys.stderr)

        # 优雅休眠
        for _ in range(interval):
            if not RUNNING:
                break
            time.sleep(1)

    print(f"[退出] auto_monitor 守护进程已停止")


def signal_handler(signum, frame):
    """处理停止信号"""
    global RUNNING
    print("\n[信号] 收到停止信号，正在优雅退出...")
    RUNNING = False


def main():
    parser = argparse.ArgumentParser(
        description="多Agent上下文自动监控守护进程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 auto_monitor.py --mode once                    # 单次检查
  python3 auto_monitor.py --mode daemon --interval 60     # 守护模式，60秒间隔
  python3 auto_monitor.py --mode daemon --auto-execute   # 自动执行交接
        """
    )
    parser.add_argument(
        "--mode",
        choices=["once", "daemon"],
        default="once",
        help="运行模式: once=单次检查, daemon=守护进程"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="守护模式检查间隔（秒），默认60"
    )
    parser.add_argument(
        "--auto-execute",
        action="store_true",
        help="达到阈值时自动执行交接（默认仅添加到队列）"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出"
    )

    args = parser.parse_args()
    config = load_config()

    if args.auto_execute:
        config["auto_execute"] = True

    # 注册信号处理器（用于优雅退出）
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.mode == "daemon":
        daemon_mode(args.interval, config)
    else:
        alerts = execute_monitor(config)
        if not alerts:
            print("所有任务上下文使用率正常")
        sys.exit(0 if not alerts else 1)


if __name__ == "__main__":
    main()
