# Context Rotation 自学习逻辑

> 本文档说明 threshold_optimizer.py 的自学习算法设计

## 核心思想

阈值不应一成不变。随着任务类型、团队协作模式的变化，最优交接时机也会改变。自学习的目标是：**让系统根据历史数据自动找到最适合当前工作模式的阈值**。

## 评估维度

### 1. 交接频率评分（权重 40%）

衡量标准：每个任务平均需要多少次交接。

| 平均次数 | 评分 | 说明 |
|---------|------|------|
| < 2次 | 1.0 | 效率极高，单任务内上下文利用充分 |
| 2-5次 | 0.7 | 正常范围，任务较复杂但可接受 |
| > 5次 | 0.3 | 过于频繁，提示任务可能需要拆分 |

**数据来源**：统计每个 `task_id` 下的 `history` 数组长度。

---

### 2. 交接时机评分（权重 60%）

衡量标准：交接时 Token 使用率是否在"最佳窗口"内。

**最佳窗口定义**：60% - 75% Token 使用率

| 实际平均 Token% | 评分 | 说明 |
|----------------|------|------|
| 60-75% | 1.0 | 最佳时机，上下文利用充分且留有安全余量 |
| 50-60% 或 76-85% | 0.7 | 略偏早/略偏晚，可优化 |
| > 85% | 0.3 | 太晚，风险高，可能被迫在强制阈值交接 |

**数据来源**：`context_snapshot.token_used / 3200`（或 `round_count / 40` 估算）

---

### 3. 综合评分公式

```
overall_score = 0.4 × frequency_score + 0.6 × timing_score
```

---

## 阈值调整规则

### 何时调整

| 综合评分 | 动作 |
|---------|------|
| > 0.8 | 阈值合适，无需调整 |
| 0.6 - 0.8 | 微调（±5%） |
| < 0.6 | 显著调整（±10%） |

### 调整方向

**Token 强制阈值（`token_force_pct`）**：

- 如果 `avg_token_pct > 80%`（太晚）→ 降低阈值，提前交接
  ```
  new_force = max(70, current_force - 5)
  ```
- 如果 `avg_token_pct < 55%`（太早）→ 提高阈值，延迟交接
  ```
  new_force = min(85, current_force + 5)
  ```

**轮次阈值（`round_force`）**：

- 如果 `avg_rounds > 30` → 降低轮次上限
  ```
  new_round_force = max(25, current_force - 3)
  ```

---

## 数据收集机制

### 自动收集

每次交接时，`handover_manager.py` 的 `prepare_handover()` 会自动写入：

```json
{
  "task_id": "...",
  "context_snapshot": {
    "token_used": 2340,
    "round_count": 18
  }
}
```

### 手动补充

如果某些交接没有快照数据，`threshold_optimizer.py` 会：
1. 尝试从 `history` 数组推断（每次交接约 10 轮）
2. 使用模拟估算值，并标注 `"estimated": true`

---

## 输出解读

运行 `threshold_optimizer.py --report` 输出示例：

```
==================================================
  context-rotation 阈值优化分析报告
  生成时间: 2026-05-11 18:00
==================================================

【频率分析】
  评分: 0.70/1.0
  正常范围（平均 3.2 次/任务）
  任务数: 5, 总交接: 16

【时机分析】
  评分: 0.30/1.0
  太晚（平均 87% token，风险较高）
  最佳窗口: 60-75%

【综合评分】
  得分: 0.46/1.0
  结论: 建议显著调整（±10%）
  置信度: 中

【优化建议】
  token_force_pct: 80 → 75
  原因: 实际交接平均在87%进行，当前阈值80%过晚
==================================================
```

---

## 与 context-rotation 主 Skill 的集成

### 集成点 1：周期性复盘

建议配合 WorkBuddy 自动化，每周末运行一次：

```bash
# 每周日 22:00 运行阈值分析
python3 ~/.workbuddy/skills/context-rotation/scripts/threshold_optimizer.py --report >> \
  ~/.workbuddy/logs/threshold_weekly.log
```

### 集成点 2：交接时自动记录

`handover_manager.py` 已内置 `context_snapshot` 收集，无需额外配置。

### 集成点 3：自动应用（可选）

如果确认建议有效，可追加 `--apply` 参数自动更新 `config.yaml`：

```python
# 在 threshold_optimizer.py 中新增
def apply_suggestions(suggestions: dict):
    """将优化建议写入 config.yaml"""
    config = load_config()
    config.update(suggestions["suggested"])
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)
```

---

## 限制与注意事项

1. **冷启动问题**：初期数据不足时（<3次交接），评分置信度低，优先参考时机评分
2. **任务差异**：不同类型任务的最佳阈值可能差异大，混合分析会稀释信号
3. **数据质量**：依赖交接时正确记录 `context_snapshot`，建议在 `check_context.py` 中自动补充
4. **不宜频繁调整**：阈值调整后，建议至少收集 1 周数据再复盘，避免震荡
