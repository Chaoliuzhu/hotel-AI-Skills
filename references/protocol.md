# Handover Protocol - 交接协议详细说明

## 协议版本
v1.0 | 2026-05-11

---

## 交接触发条件

满足以下任意条件时，应触发交接：

| 条件 | 阈值 | 优先级 |
|------|------|--------|
| Token 使用率 | ≥ 80% | P0 - 强制交接 |
| 对话轮次 | ≥ 35轮 | P0 - 强制交接 |
| Token 使用率 | ≥ 65% | P1 - 建议监控 |
| 对话轮次 | ≥ 25轮 | P1 - 建议监控 |
| 预估剩余任务量 | > 40分钟 | P1 - 建议交接 |
| 用户明确要求 | - | P0 - 立即执行 |

---

## 交接流程图

```
┌──────────────────────────────────────────────────────────────────┐
│                      Context Manager (主控)                       │
│   监控所有子Agent状态 → 检测到阈值触发 → 决策交接                   │
└────────────────────────────┬─────────────────────────────────────┘
                             │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │  Old Agent      │             │  New Agent      │
    │  (from_agent)   │             │  (to_agent)     │
    └────────┬────────┘             └────────┬────────┘
             │                                  │
             │  ① Compress                       │  ④ Resume
             │  压缩上下文→摘要                   │  读取检查点
             │                                  │
             │  ② Relay                         │  ⑤ Execute
             │  更新Task状态                     │  从检查点继续
             │  发送任务摘要                     │  执行下一步
             │                                  │
             │  ③ Confirm                       │
             │  进入 idle 状态                   │
             │  清空自身上下文                   │
             └──────────────────────────────────┘
```

---

## 3步交接详解

### ① Compress（压缩）

**执行者**：旧Agent（from_agent）

**动作**：
1. 扫描当前上下文，提炼关键信息：
   - 任务目标
   - 已完成步骤（清单）
   - 关键决策点及理由
   - 当前进行中的步骤
   - 下一步指令（清晰描述）
2. 生成摘要（不超过500字符）
3. 调用 `handover_manager.py --action prepare`

**输出**：`/memory/handover/{task_id}.json`

---

### ② Relay（传递）

**执行者**：Context Manager / 主控Agent

**动作**：
1. 更新 Task 状态：
   - `owner` → 新Agent
   - `description` → 追加检查点信息
2. 向新Agent发送 `SendMessage`，内容：
   ```
   接棒任务: {task_id}
   来自: {from_agent}
   摘要: {summary}
   下一步: {checkpoint.next_steps}
   ```

---

### ③ Confirm（确认）

**执行者**：旧Agent（from_agent）

**动作**：
1. 收到主控确认后，调用 `handover_manager.py --action confirm`
2. 进入 `idle` 状态
3. 清空自身对话上下文（释放内存）
4. 变为可用状态，可接受新任务

---

## 新Agent接棒流程

### ④ Resume（恢复）

**执行者**：新Agent（to_agent）

**动作**：
1. 调用 `handover_manager.py --action resume --task_id {task_id} --to_agent {agent_name}`
2. 读取返回的检查点信息
3. 构建新上下文：系统prompt + 任务背景 + 检查点摘要

### ⑤ Execute（执行）

**执行者**：新Agent（to_agent）

**动作**：
1. 从检查点 `checkpoint.in_progress` 继续
2. 按照 `checkpoint.next_steps` 顺序执行
3. 定期自检上下文使用率（建议每5轮一次）

---

## 交接文件格式

```json
{
  "task_id": "string",
  "handover_sequence": "number",
  "from_agent": "string",
  "to_agent": "string",
  "timestamp": "ISO8601",
  "summary": "string (<=500 chars)",
  "checkpoint": {
    "completed": ["string"],
    "in_progress": "string",
    "next_steps": ["string"]
  },
  "context_snapshot": {
    "token_used": "number",
    "round_count": "number"
  },
  "status": "prepared|confirmed|resumed",
  "history": [
    {
      "sequence": "number",
      "from": "string",
      "to": "string",
      "timestamp": "ISO8601",
      "summary": "string"
    }
  ]
}
```

---

## 错误处理规则

| 错误场景 | 处理方式 |
|---------|---------|
| 交接文件不存在 | 新Agent从任务初始状态重启，标注 `resumed_from_handover=false` |
| 新Agent读取失败 | 记录错误到 `handover_error.log`，重试3次后放弃 |
| 旧Agent无法确认空闲 | 标记 `stuck`，启动备用Agent |
| 交接过于频繁（>5次） | 警告可能存在任务设计问题，建议拆分任务 |
| Task ID冲突 | 在ID后追加随机后缀确保唯一 |

---

## Agent状态机

```
           ┌─────────────────────────────────────────┐
           │                                         │
           ▼                                         │
       ┌───────┐    execute    ┌────────┐    timeout  │
       │ idle  │ ───────────► │ active │ ──────────► │
       └───┬───┘              └───┬────┘             │
           ▲                      │                  │
           │        confirm        │ overflow         │
           └──────────────────────┘                  │
                                                    │
                       ┌────────┐                   │
                       │ handing_over │ ◄───────────┘
                       └────────┘    overflow
```

**状态说明**：
- `idle`：空闲待命，可接受新任务
- `active`：执行任务中
- `handing_over`：正在交接中（临时状态）

---

## 最佳实践

1. **交接时机宁早勿晚**：等到强制阈值再交接风险高，建议在警告阈值就开始准备
2. **摘要要精确**：摘要决定下一个Agent能否正确接续，模糊的摘要会导致重复劳动
3. **检查点要具体**：`next_steps` 应该是可直接执行的指令，不是抽象目标
4. **交接后旧Agent立即清空**：防止残留上下文占用资源
5. **监控交接频率**：如果同一任务交接>5次，说明任务设计有问题，应该拆分
