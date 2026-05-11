#!/usr/bin/env python3
"""
handover_manager.py - 多Agent交接管理器
执行Handover Protocol的3步流程：压缩 → 传递 → 交接

用法:
  # 准备交接（旧Agent执行）
  python3 handover_manager.py --action prepare --task_id task-123 \
    --from_agent agent-1 --to_agent agent-2 \
    --summary "完成了需求分析和技术选型"

  # 恢复接棒（新Agent执行）
  python3 handover_manager.py --action resume --task_id task-123 --to_agent agent-2

  # 查询交接状态
  python3 handover_manager.py --action status --task_id task-123
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Handover文件存储目录
HANDOVER_DIR = Path.home() / "WorkBuddy/2026-05-11-task-17/.workbuddy/memory/handover"


def ensure_handover_dir():
    """确保交接目录存在"""
    HANDOVER_DIR.mkdir(parents=True, exist_ok=True)


def get_handover_file(task_id: str) -> Path:
    """获取指定任务的交接文件路径"""
    return HANDOVER_DIR / f"{task_id}.json"


def prepare_handover(
    task_id: str,
    from_agent: str,
    to_agent: str,
    summary: str,
    checkpoint: dict = None,
) -> dict:
    """
    步骤1：压缩上下文并写入交接文件
    """
    ensure_handover_dir()

    handover_file = get_handover_file(task_id)

    # 读取已有交接记录（如果存在）
    existing = {}
    if handover_file.exists():
        with open(handover_file, "r", encoding="utf-8") as f:
            existing = json.load(f)

    # 构建新的交接记录
    sequence = existing.get("handover_sequence", 0) + 1

    handover_data = {
        "task_id": task_id,
        "handover_sequence": sequence,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "checkpoint": checkpoint or {
            "completed": [],
            "in_progress": "",
            "next_steps": [],
        },
        "context_snapshot": {
            "token_used": 0,  # 由调用方填充
            "round_count": 0,  # 由调用方填充
        },
        "status": "prepared",
        "history": existing.get("history", []),
    }

    # 追加到历史
    handover_data["history"].append({
        "sequence": sequence,
        "from": from_agent,
        "to": to_agent,
        "timestamp": handover_data["timestamp"],
        "summary": summary,
    })

    with open(handover_file, "w", encoding="utf-8") as f:
        json.dump(handover_data, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "handover_file": str(handover_file),
        "sequence": sequence,
        "message": f"交接准备完成: {from_agent} → {to_agent}",
    }


def confirm_handover(task_id: str, from_agent: str) -> dict:
    """
    步骤3：旧Agent确认交接完成，进入空闲状态
    """
    handover_file = get_handover_file(task_id)

    if not handover_file.exists():
        return {
            "success": False,
            "error": f"未找到任务 {task_id} 的交接文件",
        }

    with open(handover_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("from_agent") != from_agent:
        return {
            "success": False,
            "error": f"交接确认失败: 当前Agent是 {from_agent}，但交接记录显示来自 {data.get('from_agent')}",
        }

    data["status"] = "confirmed"
    data["confirmed_at"] = datetime.now().isoformat()

    with open(handover_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "message": f"交接已确认，Agent {from_agent} 现已空闲",
        "handover_data": data,
    }


def resume_handover(task_id: str, to_agent: str) -> dict:
    """
    步骤2+4：新Agent读取检查点，恢复执行
    """
    handover_file = get_handover_file(task_id)

    if not handover_file.exists():
        return {
            "success": False,
            "error": f"未找到任务 {task_id} 的交接文件",
            "action": "restart",
            "message": f"任务 {task_id} 无交接记录，建议从头开始",
        }

    with open(handover_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 验证目标Agent是否匹配
    if data.get("to_agent") != to_agent:
        # 允许任意Agent接棒（灵活性）
        pass

    # 更新状态为"已接棒"
    data["status"] = "resumed"
    data["resumed_at"] = datetime.now().isoformat()
    data["resumed_by"] = to_agent

    with open(handover_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "message": f"Agent {to_agent} 成功接棒任务 {task_id}",
        "task_id": task_id,
        "summary": data.get("summary", ""),
        "checkpoint": data.get("checkpoint", {}),
        "handover_sequence": data.get("handover_sequence", 0),
        "history": data.get("history", []),
    }


def get_status(task_id: str) -> dict:
    """查询交接状态"""
    handover_file = get_handover_file(task_id)

    if not handover_file.exists():
        return {
            "exists": False,
            "task_id": task_id,
            "message": f"任务 {task_id} 无交接记录",
        }

    with open(handover_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "exists": True,
        "task_id": task_id,
        "status": data.get("status", "unknown"),
        "from_agent": data.get("from_agent", ""),
        "to_agent": data.get("to_agent", ""),
        "handover_sequence": data.get("handover_sequence", 0),
        "last_timestamp": data.get("timestamp", ""),
        "summary": data.get("summary", ""),
        "checkpoint": data.get("checkpoint", {}),
    }


def list_handoffs() -> list:
    """列出所有交接记录"""
    ensure_handover_dir()
    files = list(HANDOVER_DIR.glob("*.json"))
    result = []
    for f in files:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            result.append({
                "task_id": data.get("task_id", f.stem),
                "status": data.get("status", ""),
                "from": data.get("from_agent", ""),
                "to": data.get("to_agent", ""),
                "sequence": data.get("handover_sequence", 0),
                "timestamp": data.get("timestamp", ""),
            })
    return sorted(result, key=lambda x: x["timestamp"], reverse=True)


def main():
    parser = argparse.ArgumentParser(description="多Agent交接管理器")
    parser.add_argument("--action", choices=["prepare", "resume", "confirm", "status", "list"], required=True)
    parser.add_argument("--task_id", type=str, help="任务ID")
    parser.add_argument("--from_agent", type=str, help="交出任务的Agent")
    parser.add_argument("--to_agent", type=str, help="接收任务的Agent")
    parser.add_argument("--summary", type=str, default="", help="任务摘要")
    parser.add_argument("--checkpoint_json", type=str, help="检查点JSON字符串")
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    result = None

    if args.action == "prepare":
        checkpoint = None
        if args.checkpoint_json:
            checkpoint = json.loads(args.checkpoint_json)
        result = prepare_handover(
            task_id=args.task_id,
            from_agent=args.from_agent,
            to_agent=args.to_agent,
            summary=args.summary,
            checkpoint=checkpoint,
        )

    elif args.action == "resume":
        result = resume_handover(
            task_id=args.task_id,
            to_agent=args.to_agent,
        )

    elif args.action == "confirm":
        result = confirm_handover(
            task_id=args.task_id,
            from_agent=args.from_agent,
        )

    elif args.action == "status":
        result = get_status(args.task_id)

    elif args.action == "list":
        result = {"handoffs": list_handoffs()}

    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"success": False, "error": "未知操作"}, ensure_ascii=False))
        sys.exit(1)

    if not result.get("success", True) and args.action in ["prepare", "resume"]:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
