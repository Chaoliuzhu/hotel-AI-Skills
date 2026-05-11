---
name: context-rotation
description: |
  多Agent上下文轮值交接控制器。当用户提到"轮值"、"上下文交接"、"多Agent协作"、"避免上下文溢出"、
  "子Agent轮换"、"任务接续"、"Context Manager"、"自动轮值"、"自动化监控"、"后台守护"、"自学习阈值"、
  "动态阈值"、"交接优化"时触发。此Skill管理多个子Agent的上下文使用率监控、阈值触发交接协议、
  Agent池的空闲/活跃状态切换、自动化后台监控、以及阈值自学习优化。
  agent_created: true
---

# Context Rotation Skill

多Agent上下文轮值交接控制器——让多个子Agent像接力赛一样无缝交接任务，防止上下文溢出导致"卡住"。

## 核心概念

- **Context Manager**：主控Agent，负责监控所有子Agent的上下文使用率，在阈值触发时决策交接
- **Agent Pool**：子Agent池，每个Agent有 `idle` / `active` / `handing_over` 三种状态
- **Handover Protocol**：交接协议，3步完成无缝接续
- **Checkpoint**：检查点，包含任务状态、已完成步骤、下一步指令

## 使用场景

1. 长任务（>20轮对话）需要多个子Agent接续完成
2. 单一子Agent上下文即将达到限制（建议阈值：token>70% 或 rounds>30）
3. 用户要求"多Agent并行"或"接力完成"复杂任务
4. 发现上下文可能溢出，主动预防而非事后补救

## 快速开始

### Step 1：创建 Agent Pool

启动多个子Agent，明确各自职责和接续规则：

```
使用 Agent tool 启动 N 个子Agent（建议3个）：
- name="agent-1", prompt 说明你是"第一棒，执行任务前期工作"
- name="agent-2", prompt 说明你是"第二棒，接替 agent-1 继续"
- name="agent-3", prompt 说明你是"第三棒，接替 agent-2 收尾"

所有子Agent共享同一个 Task List（用于传递检查点）
```

### Step 2：监控上下文状态

每个子Agent在执行过程中，定期调用 `scripts/check_context.py` 检查自身使用率：

```bash
python3 ~/.workbuddy/skills/context-rotation/scripts/check_context.py \
  --token_used 2340 \
  --token_limit 3200 \
  --rounds 18 \
  --round_limit 40
```

返回 JSON：`{"overflow": false, "token_pct": 73.1, "round_pct": 45.0, "recommendation": "monitor"}`

### Step 3：触发交接（当 overflow=true 或 recommendation="handover"）

执行交接协议：

```bash
python3 ~/.workbuddy/skills/context-rotation/scripts/handover_manager.py \
  --action prepare \
  --task_id <任务ID> \
  --from_agent agent-1 \
  --task_history "<压缩后的上下文摘要>"
```

### Step 4：新Agent接棒

下一个Agent启动时读取检查点：

```bash
python3 ~/.workbuddy/skills/context-rotation/scripts/handover_manager.py \
  --action resume \
  --task_id <任务ID> \
  --to_agent agent-2
```

### Step 5：更新Task状态

使用 `TaskUpdate` 标记任务分配给新Agent，并更新描述包含最新检查点信息。

## 交接协议详解（Handover Protocol）

### 3步交接流程

**① 压缩（Compress）**
- 将当前上下文压缩为摘要（保留：任务目标、已完成步骤、关键决策、下一步指令）
- 写入 `/Users/ccc/WorkBuddy/2026-05-11-task-17/.workbuddy/memory/handover/{task_id}.json`

**② 传递（Relay）**
- 更新 Task 状态：`owner` 改为新Agent，`description` 追加检查点
- 向新Agent发送 `SendMessage`，内容包含任务摘要和下一步指令

**③ 交接（Confirm）**
- 旧Agent收到确认后进入 `idle` 状态，清空自身上下文
- 新Agent读取检查点，开始执行

### 检查点文件格式

```json
{
  "task_id": "task-123",
  "handover_sequence": 1,
  "from_agent": "agent-1",
  "to_agent": "agent-2",
  "timestamp": "2026-05-11T17:45:00+08:00",
  "summary": "完成了需求分析和技术选型，确定使用YOLOv06进行客房质检...",
  "checkpoint": {
    "completed": ["需求调研", "竞品分析", "技术选型"],
    "in_progress": "架构设计",
    "next_steps": ["画系统架构图", "编写核心模块代码", "集成测试"]
  },
  "context_snapshot": {
    "token_used": 2850,
    "round_count": 28
  }
}
```

## 阈值配置建议

| 指标 | 警告阈值 | 强制交接阈值 |
|------|---------|------------|
| Token 使用率 | 65% | 80% |
| 对话轮次 | 25轮 | 35轮 |
| 预估剩余任务量 | >20分钟 | >40分钟 |

**配置位置**：`scripts/config.yaml`

## 错误处理

- **新Agent无法读取检查点**：回退到从任务初始状态重新开始，并记录错误到 `handover_error.log`
- **旧Agent无法进入空闲**：标记 `agent-1` 状态为 `stuck`，启动 `agent-3` 作为备用
- **Task ID 不存在**：创建新的 Task 并标注 `resumed_from_handover=true`

## 扩展方向A：自动化监控（auto_monitor.py）

触发词：自动轮值、自动化监控、后台守护、定时检查

### 什么是 auto_monitor.py

将手动检查升级为**后台守护进程**，自动监控所有进行中任务的上下文使用率，无需人工干预。

### 两种运行模式

**模式1：单次检查（适合定时任务）**
```bash
python3 ~/.workbuddy/skills/context-rotation/scripts/auto_monitor.py --mode once
```
输出：检查所有活跃任务的上下文，返回交接建议列表

**模式2：守护进程（适合后台持续监控）**
```bash
python3 ~/.workbuddy/skills/context-rotation/scripts/auto_monitor.py \
  --mode daemon \
  --interval 60 \
  --auto-execute
```
- `--interval 60`：每60秒检查一次
- `--auto-execute`：达到阈值时自动执行交接（默认仅添加到队列）

### 交接队列

auto_monitor 不直接执行交接，而是将建议写入队列文件：

```
~/.workbuddy/memory/handover/auto_handover_queue.json
```

队列格式：
```json
[{
  "task_id": "task-123",
  "reason": "Token 87.5% + 轮次 32/40",
  "added_at": "2026-05-11T17:45:00",
  "status": "pending"
}]
```

主控Agent定期读取队列，确认后执行交接。

### 一键配置自动化

```bash
bash ~/.workbuddy/skills/context-rotation/scripts/setup_automation.sh
```

菜单选项：
1. 守护进程模式（macOS launchd / Linux systemd）
2. cron 定时任务模式（每天固定时间）
3. 查看当前配置
4. 卸载自动化

---

## 扩展方向B：自学习优化（threshold_optimizer.py）

触发词：自学习阈值、动态阈值、交接优化、阈值分析

### 什么是 threshold_optimizer.py

根据历史交接数据，**自动分析阈值效果并生成优化建议**，让系统越用越精准。

### 核心评估维度

| 维度 | 权重 | 最佳标准 |
|------|------|---------|
| 交接频率 | 40% | 平均 < 2次/任务 |
| 交接时机 | 60% | Token 使用率 60-75% |

### 使用方式

**查看优化建议（推荐每周一次）**
```bash
python3 ~/.workbuddy/skills/context-rotation/scripts/threshold_optimizer.py --suggest
```

**生成详细报告**
```bash
python3 ~/.workbuddy/skills/context-rotation/scripts/threshold_optimizer.py --report
```

**使用模拟数据演示**（无历史数据时）
```bash
python3 ~/.workbuddy/skills/context-rotation/scripts/threshold_optimizer.py --simulate --report
```

### 输出示例

```
【时机分析】
  评分: 0.70/1.0
  略晚（平均 77% token，建议提前5%）
  最佳窗口: 60-75%

【优化建议】
  token_force_pct: 80 → 75
  原因: 实际交接平均在77%进行，建议降低阈值提前交接
```

### 建议应用时机

- **每周复盘**：配合 22:00 自动化复盘运行
- **任务完成后**：分析本次任务的交接效率
- **阈值调整后**：至少收集1周数据再复盘

---

## 关联Skill

- `context-guardian`：上下文守护，与本Skill互补（一个管"护"，一个管"换"）
- `self-improving`：基于本Skill的交接日志，自动分析频繁交接的原因并优化阈值
