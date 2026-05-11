# context-rotation 多Agent上下文轮值控制器

> 让多个子Agent像接力赛一样无缝交接任务，防止上下文溢出导致"卡住"。

[English README](#english) | [中文说明](#中文)

---

## 中文说明

### 是什么

context-rotation 是一个多Agent协作调度工具。当一个复杂任务需要多轮对话才能完成时，它负责：
- **监控**每个Agent的上下文使用率（Token使用量、对话轮次）
- **预警**在达到危险阈值前主动提醒
- **交接**在阈值触发时自动执行3步交接协议，新Agent接棒继续任务
- **自学习**根据历史交接数据动态优化阈值，越用越精准

### 解决的问题

- 长任务执行到一半"卡住"，上下文溢出
- 多Agent协作时不知道何时该换人
- 任务中断后下一个Agent不知道从哪继续

### 核心特性

| 特性 | 说明 |
|------|------|
| 3步交接协议 | 压缩→传递→确认，无缝接续 |
| 自动监控 | 后台守护进程，每30秒自动检查 |
| 双扩展方向 | A:自动化监控 + B:自学习阈值优化 |
| 开源免费 | MIT License，可自由使用和修改 |

### 快速开始

#### 安装

```bash
# 克隆或复制到本地 skills 目录
cp -r context-rotation ~/.workbuddy/skills/
```

#### 基本用法

```bash
# Step 1: 检查上下文使用率
python3 ~/.workbuddy/skills/context-rotation/scripts/check_context.py \
  --token_used 2340 --token_limit 3200 --rounds 18 --round_limit 40

# Step 2: 触发交接
python3 ~/.workbuddy/skills/context-rotation/scripts/handover_manager.py \
  --action prepare --task_id task-123 --from_agent agent-1 --to_agent agent-2 \
  --summary "完成需求分析，继续做架构设计"

# Step 3: 新Agent接棒
python3 ~/.workbuddy/skills/context-rotation/scripts/handover_manager.py \
  --action resume --task_id task-123 --to_agent agent-2
```

#### 启动自动监控（推荐）

```bash
# 后台守护进程模式
python3 ~/.workbuddy/skills/context-rotation/scripts/auto_monitor.py \
  --mode daemon --interval 30

# 或一键配置定时任务
bash ~/.workbuddy/skills/context-rotation/scripts/setup_automation.sh
```

#### 每周阈值复盘

```bash
python3 ~/.workbuddy/skills/context-rotation/scripts/threshold_optimizer.py --report
```

### 文件结构

```
context-rotation/
├── SKILL.md                          # 主技能说明
├── scripts/
│   ├── check_context.py              # 上下文检查器
│   ├── handover_manager.py           # 交接管理器
│   ├── auto_monitor.py              # 自动监控守护进程
│   ├── threshold_optimizer.py        # 阈值自学习分析器
│   ├── setup_automation.sh          # 自动化配置脚本
│   └── config.yaml                   # 阈值配置
└── references/
    ├── protocol.md                   # 交接协议详细文档
    └── learning_logic.md             # 自学习算法说明
```

### 阈值配置

编辑 `scripts/config.yaml`：

```yaml
token_warn_pct: 65    # 警告阈值（%）
token_force_pct: 80   # 强制交接阈值（%）
round_warn: 25        # 警告轮次
round_force: 35       # 强制交接轮次
```

### 适用场景

- 长任务（>20轮对话）的多Agent接续
- 需要多个人Agent并行研发的复杂项目
- 防止上下文溢出导致任务中断
- 需要持续运行的自动化监控管线

### 相关技能

- `context-guardian`：上下文守护（互补，一个管"护"，一个管"换"）
- `hotel-room-quality-inspection`：德胧客房质检系统

---

## English

### What is context-rotation?

context-rotation is a multi-agent context management and handover system. It monitors each sub-agent's context usage and automatically triggers a 3-step handover protocol when thresholds are reached, ensuring seamless task continuation without context overflow.

### Key Features

- **3-Step Handover Protocol**: Compress → Relay → Confirm
- **Auto-Monitor Daemon**: Background process checks every 30 seconds
- **Two Extension Directions**: A) Automated monitoring B) Self-learning threshold optimization
- **MIT Licensed**: Free to use, modify, and share

### Quick Start

```bash
# Check context usage
python3 scripts/check_context.py --token_used 2340 --token_limit 3200 --rounds 18 --round_limit 40

# Start auto-monitor daemon
python3 scripts/auto_monitor.py --mode daemon --interval 30
```

### License

MIT License - Free for commercial and non-commercial use.

---

## 贡献者

- 开发者：Claw (WorkBuddy AI Agent)
- 适用平台：WorkBuddy / CodeBuddy
- 版本：1.0
- 更新日期：2026-05-11
