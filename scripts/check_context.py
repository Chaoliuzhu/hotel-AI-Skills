#!/usr/bin/env python3
"""
check_context.py - 多Agent上下文检查器
检查当前Agent的上下文使用率，判断是否需要交接

用法:
  python3 check_context.py --token_used 2340 --token_limit 3200 --rounds 18 --round_limit 40

输出:
  JSON格式的状态报告
"""

import argparse
import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config():
    """加载配置文件"""
    if CONFIG_PATH.exists():
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "token_warn_pct": 65,
        "token_force_pct": 80,
        "round_warn": 25,
        "round_force": 35,
    }


def check_context(token_used: int, token_limit: int, rounds: int, round_limit: int) -> dict:
    """
    检查上下文使用率并返回状态报告
    """
    config = load_config()

    token_pct = (token_used / token_limit * 100) if token_limit > 0 else 0
    round_pct = (rounds / round_limit * 100) if round_limit > 0 else 0

    # 计算推荐动作
    if token_pct >= config["token_force_pct"] or rounds >= config["round_force"]:
        recommendation = "handover"
        overflow = True
    elif token_pct >= config["token_warn_pct"] or rounds >= config["round_warn"]:
        recommendation = "monitor"
        overflow = False
    else:
        recommendation = "continue"
        overflow = False

    return {
        "overflow": overflow,
        "token_pct": round(token_pct, 1),
        "round_pct": round(round_pct, 1),
        "token_used": token_used,
        "token_limit": token_limit,
        "rounds": rounds,
        "round_limit": round_limit,
        "recommendation": recommendation,
        "config": config,
    }


def main():
    parser = argparse.ArgumentParser(description="检查上下文使用率")
    parser.add_argument("--token_used", type=int, required=True, help="已使用的token数")
    parser.add_argument("--token_limit", type=int, required=True, help="最大token限制")
    parser.add_argument("--rounds", type=int, required=True, help="当前对话轮次")
    parser.add_argument("--round_limit", type=int, required=True, help="最大对话轮次限制")
    parser.add_argument("--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    result = check_context(
        token_used=args.token_used,
        token_limit=args.token_limit,
        rounds=args.rounds,
        round_limit=args.round_limit,
    )

    if args.verbose:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False))

    # 如果需要交接，输出建议
    if result["recommendation"] == "handover":
        print(
            f"\n⚠️ 建议交接: Token使用率 {result['token_pct']}%, 轮次 {result['rounds']}/{result['round_limit']}",
            file=sys.stderr,
        )
        sys.exit(1)
    elif result["recommendation"] == "monitor":
        print(
            f"\n🔔 建议监控: Token使用率 {result['token_pct']}%, 轮次 {result['rounds']}/{result['round_limit']}",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
