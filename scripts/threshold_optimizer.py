#!/usr/bin/env python3
"""
threshold_optimizer.py - 上下文阈值自学习优化器

功能：
- 读取 handover 目录下的历史交接记录
- 分析交接频率、时机、效果等指标
- 生成动态阈值优化建议
- 支持模拟数据测试（在没有真实数据时）

用法:
  # 分析所有历史交接记录
  python3 threshold_optimizer.py

  # 只看优化建议
  python3 threshold_optimizer.py --suggest

  # 生成详细报告
  python3 threshold_optimizer.py --report

  # 模拟演示（使用示例数据）
  python3 threshold_optimizer.py --simulate
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from check_context import check_context

# ============ 配置 ============
SKILL_DIR = Path(__file__).parent.parent
MEMORY_HANDOVER_DIR = Path.home() / "WorkBuddy/2026-05-11-task-17/.workbuddy/memory/handover"
CONFIG_FILE = SKILL_DIR / "scripts/config.yaml"

# 默认阈值配置
DEFAULT_THRESHOLDS = {
    "token_warn_pct": 65,
    "token_force_pct": 80,
    "round_warn": 25,
    "round_force": 35,
}


def load_config() -> dict:
    """加载当前配置"""
    if CONFIG_FILE.exists():
        import yaml
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return DEFAULT_THRESHOLDS.copy()


def load_handover_records() -> list:
    """加载所有交接记录"""
    if not MEMORY_HANDOVER_DIR.exists():
        return []
    files = list(MEMORY_HANDOVER_DIR.glob("*.json"))
    records = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                data["_file"] = f.name
                records.append(data)
        except Exception:
            pass
    return records


def flatten_records(records: list) -> list:
    """将嵌套的交接记录展开为每次交接的独立记录"""
    flat = []
    for record in records:
        history = record.get("history", [])
        if history:
            for h in history:
                flat.append({
                    "task_id": record.get("task_id"),
                    "file": record.get("_file"),
                    "sequence": h.get("sequence"),
                    "from": h.get("from"),
                    "to": h.get("to"),
                    "timestamp": h.get("timestamp"),
                    "summary": h.get("summary", ""),
                    "context_snapshot": record.get("context_snapshot", {}),
                    "status": record.get("status"),
                })
        else:
            # 单次交接（没有history）
            flat.append({
                "task_id": record.get("task_id"),
                "file": record.get("_file"),
                "sequence": record.get("handover_sequence", 1),
                "from": record.get("from_agent"),
                "to": record.get("to_agent"),
                "timestamp": record.get("timestamp"),
                "summary": record.get("summary", ""),
                "context_snapshot": record.get("context_snapshot", {}),
                "status": record.get("status"),
            })
    return flat


def analyze_frequency(flat_records: list) -> dict:
    """分析交接频率"""
    if not flat_records:
        return {"score": 1.0, "message": "无历史数据", "avg_per_task": 0}

    # 按任务分组
    tasks = {}
    for r in flat_records:
        tid = r["task_id"]
        if tid not in tasks:
            tasks[tid] = []
        tasks[tid].append(r)

    # 计算每任务平均交接次数
    counts = [len(v) for v in tasks.values()]
    avg = sum(counts) / len(counts) if counts else 0

    # 评分
    if avg < 2:
        score = 1.0
        message = f"效率高（平均 {avg:.1f} 次/任务）"
    elif avg <= 5:
        score = 0.7
        message = f"正常范围（平均 {avg:.1f} 次/任务）"
    else:
        score = 0.3
        message = f"过于频繁（平均 {avg:.1f} 次/任务，建议拆分任务）"

    return {
        "score": score,
        "message": message,
        "avg_per_task": round(avg, 2),
        "total_tasks": len(tasks),
        "total_handoffs": len(flat_records),
        "task_details": {tid: len(v) for tid, v in tasks.items()},
    }


def analyze_timing(flat_records: list, current_thresholds: dict) -> dict:
    """分析交接时机是否合适"""
    if not flat_records:
        return {"score": 1.0, "message": "无历史数据"}

    token_pcts = []
    round_counts = []

    for r in flat_records:
        snapshot = r.get("context_snapshot", {})
        token_used = snapshot.get("token_used", 0)
        round_count = snapshot.get("round_count", 0)

        # 如果没有真实数据，用估算
        if token_used == 0:
            # 基于轮次估算token使用率
            estimated_pct = min(95, (round_count / 40) * 100) if round_count else 50
            token_pcts.append(estimated_pct)
        else:
            token_pcts.append(min(95, (token_used / 3200) * 100))

        round_counts.append(round_count)

    avg_token_pct = sum(token_pcts) / len(token_pcts) if token_pcts else 0
    avg_rounds = sum(round_counts) / len(round_counts) if round_counts else 0

    # 评分
    # 最佳窗口: 60-75% token
    if 60 <= avg_token_pct <= 75:
        score = 1.0
        message = f"时机最佳（平均 {avg_token_pct:.0f}% token，{avg_rounds:.0f} 轮）"
    elif 50 <= avg_token_pct < 60:
        score = 0.9
        message = f"偏早（平均 {avg_token_pct:.0f}% token，可能可以再等等）"
    elif 76 <= avg_token_pct <= 85:
        score = 0.7
        message = f"略晚（平均 {avg_token_pct:.0f}% token，建议提前5%）"
    elif avg_token_pct > 85:
        score = 0.3
        message = f"太晚（平均 {avg_token_pct:.0f}% token，风险较高）"
    else:
        score = 0.8
        message = f"平均 {avg_token_pct:.0f}% token"

    return {
        "score": score,
        "message": message,
        "avg_token_pct": round(avg_token_pct, 1),
        "avg_rounds": round(avg_rounds, 1),
        "force_threshold": current_thresholds.get("token_force_pct", 80),
        "optimal_range": "60-75%",
    }


def compute_overall_score(frequency: dict, timing: dict) -> dict:
    """计算综合评分"""
    # 权重: 时机更重要(0.6) vs 频率(0.4)
    overall = 0.4 * frequency["score"] + 0.6 * timing["score"]

    if overall > 0.8:
        verdict = "阈值配置合适，无需调整"
        confidence = "高"
    elif overall >= 0.6:
        verdict = "建议微调（±5%）"
        confidence = "中"
    else:
        verdict = "建议显著调整（±10%）"
        confidence = "中"

    return {
        "overall": round(overall, 2),
        "verdict": verdict,
        "confidence": confidence,
        "weights": {"frequency": 0.4, "timing": 0.6},
    }


def generate_suggestions(
    current: dict,
    frequency: dict,
    timing: dict,
    overall: dict,
) -> dict:
    """生成具体的阈值优化建议"""
    suggestions = {}
    reasons = []

    # Token 强制阈值
    if overall["overall"] < 0.8:
        current_force = current.get("token_force_pct", 80)
        if timing["avg_token_pct"] > 80:
            # 太晚了，降低阈值提前交接
            new_force = max(70, current_force - 5)
            suggestions["token_force_pct"] = new_force
            reasons.append(f"实际交接平均在{timing['avg_token_pct']:.0f}%进行，当前阈值{current_force}%过晚")
        elif timing["avg_token_pct"] < 55:
            # 太早了，可以适当提高
            new_force = min(85, current_force + 5)
            suggestions["token_force_pct"] = new_force
            reasons.append(f"交接过早({timing['avg_token_pct']:.0f}%)，可适当延后")

    # 轮次阈值
    current_round_force = current.get("round_force", 35)
    if timing["avg_rounds"] > 30:
        new_round_force = max(25, current_round_force - 3)
        suggestions["round_force"] = new_round_force
        reasons.append(f"实际平均轮次{timing['avg_rounds']:.0f}，建议调整")

    return {
        "current": current,
        "suggested": suggestions if suggestions else "保持不变",
        "reasons": reasons,
        "note": "仅输出建议，实际修改需手动更新 config.yaml 或确认后自动应用"
    }


def generate_report(
    frequency: dict,
    timing: dict,
    overall: dict,
    suggestions: dict,
) -> str:
    """生成可读的详细报告"""
    lines = [
        "=" * 50,
        "  context-rotation 阈值优化分析报告",
        f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 50,
        "",
        "【频率分析】",
        f"  评分: {frequency['score']:.1f}/1.0",
        f"  {frequency['message']}",
        f"  任务数: {frequency.get('total_tasks', 0)}, 总交接: {frequency.get('total_handoffs', 0)}",
        "",
        "【时机分析】",
        f"  评分: {timing['score']:.1f}/1.0",
        f"  {timing['message']}",
        f"  最佳窗口: {timing['optimal_range']}",
        "",
        "【综合评分】",
        f"  得分: {overall['overall']:.2f}/1.0",
        f"  结论: {overall['verdict']}",
        f"  置信度: {overall['confidence']}",
        "",
        "【优化建议】",
    ]

    if isinstance(suggestions.get("suggested"), dict):
        for k, v in suggestions["suggested"].items():
            lines.append(f"  {k}: {suggestions['current'].get(k)} → {v}")
        for r in suggestions.get("reasons", []):
            lines.append(f"  原因: {r}")
    else:
        lines.append(f"  {suggestions.get('suggested', '保持不变')}")

    lines.extend(["", "=" * 50])
    return "\n".join(lines)


def simulate_data() -> list:
    """
    生成模拟数据用于演示
    （在没有真实交接记录时展示功能）
    """
    return [
        {
            "task_id": "demo-task-1",
            "sequence": 1,
            "from": "agent-1",
            "to": "agent-2",
            "timestamp": "2026-05-10T10:00:00",
            "summary": "完成需求分析",
            "context_snapshot": {"token_used": 2100, "round_count": 22},
        },
        {
            "task_id": "demo-task-1",
            "sequence": 2,
            "from": "agent-2",
            "to": "agent-3",
            "timestamp": "2026-05-10T10:30:00",
            "summary": "完成架构设计",
            "context_snapshot": {"token_used": 2400, "round_count": 25},
        },
        {
            "task_id": "demo-task-2",
            "sequence": 1,
            "from": "agent-1",
            "to": "agent-2",
            "timestamp": "2026-05-11T14:00:00",
            "summary": "完成数据采集",
            "context_snapshot": {"token_used": 2800, "round_count": 32},
        },
        {
            "task_id": "demo-task-3",
            "sequence": 1,
            "from": "agent-1",
            "to": "agent-2",
            "timestamp": "2026-05-11T16:00:00",
            "summary": "完成初步分析",
            "context_snapshot": {"token_used": 2600, "round_count": 28},
        },
    ]


def main():
    parser = argparse.ArgumentParser(description="上下文阈值自学习优化器")
    parser.add_argument("--report", action="store_true", help="生成详细报告")
    parser.add_argument("--suggest", action="store_true", help="只显示优化建议")
    parser.add_argument("--simulate", action="store_true", help="使用模拟数据演示")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")
    args = parser.parse_args()

    # 加载数据
    if args.simulate:
        flat = simulate_data()
        current = DEFAULT_THRESHOLDS.copy()
        print("# [演示模式] 使用模拟数据", file=sys.stderr)
    else:
        records = load_handover_records()
        flat = flatten_records(records)
        current = load_config()
        if not flat:
            print("# [提示] 无历史交接记录，使用 --simulate 查看演示", file=sys.stderr)
            flat = simulate_data()
            current = DEFAULT_THRESHOLDS.copy()

    # 分析
    frequency = analyze_frequency(flat)
    timing = analyze_timing(flat, current)
    overall = compute_overall_score(frequency, timing)
    suggestions = generate_suggestions(current, frequency, timing, overall)

    # 输出
    if args.json:
        result = {
            "frequency": frequency,
            "timing": timing,
            "overall": overall,
            "suggestions": suggestions,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.suggest:
        if isinstance(suggestions.get("suggested"), dict):
            print("优化建议:")
            for k, v in suggestions["suggested"].items():
                print(f"  {k}: {suggestions['current'].get(k)} → {v}")
        else:
            print(suggestions.get("suggested", "保持不变"))
    elif args.report:
        print(generate_report(frequency, timing, overall, suggestions))
    else:
        # 默认输出摘要
        print(f"综合评分: {overall['overall']:.2f}/1.0 | {overall['verdict']}")
        print(f"频率: {frequency['message']}")
        print(f"时机: {timing['message']}")
        if overall['overall'] < 0.8:
            print("\n详细建议: python3 threshold_optimizer.py --suggest")


if __name__ == "__main__":
    main()
