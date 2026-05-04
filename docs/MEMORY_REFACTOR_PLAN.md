# ArXiv Digest — Memory 重构计划 v1.0

## 一、当前问题诊断

| 问题 | 当前状态 | 影响 |
|------|---------|------|
| 历史记录太浅 | `recommended_history.json` 只记 `times_recommended` + `last_recommended` | 无法追溯某篇论文的评分变化、热度趋势 |
| 日报文件不可检索 | `digests/YYYY-MM-DD.md` 是纯 markdown，无结构化索引 | 用户问"DPO 相关的"时，只能逐文件 grep，慢且不精准 |
| 无语义关联 | 论文之间没有主题/概念关联 | 无法做"这篇和之前某篇很像"的 callback |
| 无用户反馈 | 用户在 qqbot 的回复（"这篇不错"/"没用"）没有记录 | 推荐无法个性化调优 |
| callback 缺失 | 论文 B 之前被过滤（score 5.0），但 3 天后 HN 爆火 +50 points | 系统不会重新推荐 |

## 二、目标架构：Paper Archive + Semantic Retrieval + Callback

### 2.1 单论文档案（Paper Archive）

每篇论文一个 JSON 文件：`memory/papers/{arxiv_id}.json`

```json
{
  "arxiv_id": "2605.00155",
  "title": "Wasserstein Distributionally Robust Regret Optimization for RLHF",
  "authors": ["Yikai Wang", "Shang Liu", "Jose Blanchet"],
  "categories": ["cs.LG", "cs.CL", "math.OC"],
  "first_seen": "2026-05-04",
  "last_seen": "2026-05-04",

  "llm_evaluations": [
    {
      "date": "2026-05-04",
      "score": 9.0,
      "relevance": 9,
      "novelty": 9,
      "impact": 9,
      "zh_summary": "从运筹学视角...",
      "reason": "直击RLHF的Goodhart定律..."
    }
  ],

  "heat_timeline": [
    {"date": "2026-05-04", "source": "hn", "points": 0, "comments": 0},
    {"date": "2026-05-04", "source": "citations", "count": 0, "influential": 0}
  ],

  "tags": ["RLHF", "分布鲁棒优化", "Wasserstein距离", "奖励过优化", "Goodhart定律", "后训练对齐"],

  "user_interactions": [
    {"date": "2026-05-04", "type": "discussed", "channel": "qqbot", "note": "用户追问奖励过优化的细节"}
  ],

  "status": "active",
  "status_history": [
    {"date": "2026-05-04", "status": "active", "reason": "score 9.0, 入选日报"}
  ]
}
```

**关键字段说明**：
- `llm_evaluations` — 每次评估的完整记录（支持追溯评分变化）
- `heat_timeline` — 热度时间线（检测热度飙升）
- `tags` — LLM 生成的主题标签（语义检索的核心）
- `user_interactions` — 用户反馈和讨论记录
- `status` — `active` | `filtered` | `callback`，配合 `status_history` 追踪状态变迁

### 2.2 文件结构重构

```
memory/
├── papers/                    # 单论文档案（核心）
│   ├── 2605.00155.json
│   ├── 2604.27733.json
│   └── ...
├── digests/                   # 日报（保留，供人阅读）
│   ├── 2026-05-04.md
│   └── ...
├── weekly/                    # 周总结
├── monthly/                   # 月总结
├── heat_cache.json            # 热度信号缓存
├── paper_index.json           # 快速索引（所有论文的 tags + status）
└── RESEARCH_LOG.md            # 人工可读索引
```

`paper_index.json` 结构（轻量，快速加载）：
```json
{
  "2605.00155": {
    "title": "Wasserstein DRO for RLHF",
    "tags": ["RLHF", "分布鲁棒优化", ...],
    "status": "active",
    "last_score": 9.0,
    "last_seen": "2026-05-04"
  }
}
```

### 2.3 语义检索机制

**不使用外部 embedding 模型**（避免依赖），而是利用 LLM 生成的 `tags` + 标题/摘要模糊匹配。

**检索流程**：
1. 用户问："最近有没有 DPO 相关的？"
2. 加载 `paper_index.json`（轻量，所有论文的标签索引）
3. 检索策略：
   - **精确匹配**：tags 中包含 "DPO" 的论文
   - **模糊匹配**：标题/摘要中包含 "preference optimization"、"direct preference" 等变体
   - **时间衰减**：按 `last_seen` 排序，越新的越靠前
   - **评分加权**：`last_score` 高的优先
4. 返回 Top 5-10 篇，附带推荐理由：
   > "你 5 月 4 日的日报中有 3 篇 DPO 相关：
   > ① TUR-DPO (9.0分) — 拓扑感知 DPO 变体
   > ② Mind the Gap (9.0分) — 证明 DPO 理论不一致性
   > 另外历史上还有 2 篇 filtered 但主题相关的：..."

### 2.4 Callback 机制

**场景 1：热度飙升 Callback**
```
论文 B 状态：filtered（2026-05-01, score 4.5）

3 天后（2026-05-04）：
- HN points 从 0 → 45
- citations 从 0 → 3
→ heat_score 从 0 → 6.0

触发 callback：
- 重新 LLM 评估（可能 score 提升到 7.0+）
- 如果新 score ≥ 6.0，status → callback，加入日报并标注"🔥 热度飙升"
```

**场景 2：主题查询 Callback**
```
用户问："test-time compute 有什么进展？"

检索历史论文 tags → 找到 "test-time compute" 相关论文：
- 论文 X：active，score 8.0，上次推荐 2026-04-20
- 论文 Y：filtered，score 5.5，但 tags 包含 "test-time compute"

返回策略：
- 论文 X 正常推荐（active）
- 论文 Y 作为"历史参考"推荐（标注：之前 filtered，但主题相关）
```

**场景 3：重复推荐策略优化**
```
当前逻辑：times_recommended ≥ 2 → 标 🔥🔥

优化后：
- times_recommended ≥ 2 + heat_score 上升 → 🔥🔥 持续热门
- times_recommended ≥ 2 + heat_score 下降 → 过滤（标注"已冷却"）
- times_recommended ≥ 2 + 用户未互动 → 降低权重
```

### 2.5 用户反馈闭环

**隐式反馈**（自动记录）：
| 用户行为 | 记录为 | 影响 |
|---------|--------|------|
| 追问某篇论文 | `type: "discussed"` | 该论文/主题权重 + |
| 追问后表示"不错" | `type: "positive"` | 该论文/主题权重 ++ |
| 追问后表示"没用" | `type: "negative"` | 该论文/主题权重 -- |
| 对日报无回复 | `type: "ignored"` | 无影响（默认） |

**显式反馈**（用户主动回复 emoji）：
- 👍 → `type: "liked"`
- 👎 → `type: "disliked"`
- 📌 → `type: "pinned"`（重点标记，未来优先 callback）

**反馈如何影响推荐**：
- 用户经常讨论 "RLHF" → 未来 RLHF 相关论文的 relevance 权重上调
- 用户标记 "DPO" 为没用 → 未来 DPO 论文的 relevance 权重下调
- 用户 pinned 某篇论文 → 该论文在月度总结中优先展示

## 三、实现步骤

| 阶段 | 任务 | 优先级 | 预估工作量 |
|------|------|--------|-----------|
| **Phase 1** | 升级 `update_history()` → 生成单论文档案 JSON | 🔴 高 | 1-2h |
| **Phase 2** | LLM 评估时生成 `tags`（5-10 个关键词） | 🔴 高 | 1h |
| **Phase 3** | 构建 `paper_index.json` 轻量索引 | 🟡 中 | 1h |
| **Phase 4** | 实现语义检索接口 `search_papers(query)` | 🟡 中 | 2-3h |
| **Phase 5** | 实现 callback 逻辑（热度检测 + 状态变迁） | 🟡 中 | 2-3h |
| **Phase 6** | 用户反馈收集（qqbot 回复解析） | 🟢 低 | 2-3h |
| **Phase 7** | 反馈权重调优（A/B 风格实验） | 🟢 低 | 持续迭代 |

## 四、与现有代码的兼容

- `recommended_history.json` 保留，作为向后兼容的轻量索引
- `digests/YYYY-MM-DD.md` 保留，供人阅读
- 新增 `papers/` 目录，不破坏现有流程
- `generate_digest.py` 中 `update_history()` 升级，同时写 `recommended_history.json` + `papers/{id}.json`

## 五、关键设计决策

**Q: 为什么不直接用向量数据库（如 Chroma/FAISS）？**
A: 避免引入外部依赖。用 LLM 生成的 `tags` + 标题/摘要模糊匹配，在论文量 < 1000 时足够高效，且无需安装额外包。

**Q: tags 如何生成？**
A: LLM 评估时同时输出 tags。Prompt 增加："Tags: 列出 5-10 个该论文的核心关键词/概念，用逗号分隔" → 存入 `llm_evaluations[].tags`。

**Q: 用户反馈如何影响 LLM 评估标准？**
A: 不是直接改分数，而是改 **prompt 中的权重说明**。例如：
- 用户经常讨论 RLHF → prompt 中 "RLHF 相关论文的 relevance 权重自动上调 0.5"
- 用户标记 DPO 为没用 → prompt 中 "DPO 相关论文的 relevance 权重自动下调 0.5"
- 这是一个轻量的个性化机制，不需要重新训练模型。
