---

name: arxiv-digest
description: 每日arXiv论文简报生成器。支持自定义关键词查询、alphaxiv跨领域热门抓取、HuggingFace Daily Papers、推荐历史追踪、LLM智能rerank、重复推荐高亮。
---

# ArXiv Digest

通用、可定制的arXiv论文监控skill。自动聚合你关注的领域 + 全AI领域热门论文 + HuggingFace社区精选，通过LLM智能rerank生成结构化日报。

## 配置

### 1. 关注领域 — `config/topics.json`

```json
{
  "topics": ["LLM post-training", "agentic RL", "LLM agent"],
  "per_topic_count": 5
}
```

### 2. 推荐风格 — `config/preferences.json`

```json
{
  "summary": {
    "max_length": 800,
    "include_full_abstract": true,
    "include_author_list": true,
    "highlight_repeated": true,
    "repeated_threshold": 2
  },
  "cross_domain": {
    "enabled": true,
    "max_papers": 5,
    "source": "alphaxiv-trending",
    "label": "🔥 跨领域热门"
  },
  "huggingface": {
    "enabled": true,
    "max_papers": 5,
    "label": "🤗 HuggingFace Daily"
  },
  "llm_rerank": {
    "enabled": true,
    "top_k": 10,
    "score_threshold": 7
  },
  "cron": {
    "enabled": true,
    "schedule": "0 9 * * *",
    "timezone": "Asia/Shanghai"
  }
}
```

## 使用

```bash
# 第1步：收集原始数据
python3 scripts/generate_digest.py --raw

# 第2步：LLM 逐篇评估论文，写入 memory/llm_scores.json

# 第3步：生成最终日报
python3 scripts/generate_digest.py --rerank-json memory/llm_scores.json --output memory/daily_digest.md

# 或一键运行（需手动完成第2步评估）
bash scripts/deliver_digest.sh

# 查询单个主题
bash scripts/query_arxiv.sh "your topic" 5
```

## 自动化（cron）

已配置每日 **04:00（Asia/Shanghai）** 自动推送到 `qqbot` 频道。agent 会自动执行：
1. 抓取 arXiv topics + alphaxiv trending + HuggingFace Daily Papers
2. **LLM 逐篇评估**：对每篇论文评估 relevance、novelty、impact，生成详细中文摘要（2-3 句，涵盖方法+发现+意义）
3. **自动过滤低相关论文**：综合评分 < 6.0 分的论文不进入日报
4. **只推送最终报告**：生成精简日报后 **一次性推送到指定频道**

**为什么逐篇评估？**
- 模型注意力有限，多篇塞一起会导致每篇分析深度下降
- 并行子 agent 写文件不可靠，容易丢失评分结果
- 逐篇评估确保质量，中文摘要更详细准确

**论文上下文对话**：
收到日报后，你回复任何包含论文标题、arXiv ID 或核心关键词的消息，agent 会自动：
1. 识别你指的是哪篇论文（从最近7天的日报中匹配）
2. 加载该论文的完整摘要和元信息
3. 基于论文内容回答你的具体问题
4. 如果论文不在最近日报中，自动去 arXiv 获取信息

**推送目标配置**：修改 `delivery.channel` 可切换目标频道：
- `qqbot` → QQ 频道
- `webchat` → 网页控制台
- 其他已配置的频道名称

如需立即触发测试：`openclaw cron run arxiv-digest-daily`

## 输出特性

- **关注领域** + **跨领域热门** + **🤗 HuggingFace Daily** 三板块
- 长摘要（默认800字符）、作者列表、arXiv分类、论文备注
- 🔥 alphaxiv trending 标记热门来源
- 🤗 HuggingFace Daily Papers 标记社区精选
- 🔥🔥 自动高亮连续多次被推荐的论文（配置阈值）
- 🎯 **LLM 智能 rerank**：综合相关性、新颖性、影响力评分，生成 Top Picks
- 📅 **按日期分文件保存**：`memory/digests/YYYY-MM-DD.md`，不再全部追加到一个文件
- 🗣️ **论文上下文对话**：你在日报后追问某篇论文，我会自动识别论文 ID 并加载上下文
- 📊 **周期性提炼**：自动生成周总结 `memory/weekly/YYYY-WXX.md` 和月总结 `memory/monthly/YYYY-MM.md`
- 自动记录推荐历史到 `memory/recommended_history.json`
- `memory/RESEARCH_LOG.md` 保留索引引用，指向每日完整报告

## 数据源与热度/相关性架构

当前 skill 采用 **三源并行 + LLM rerank 融合** 架构：

| 板块 | 来源 | 排序依据 | 代表什么 |
|------|------|----------|----------|
| 📌 关注领域 | arXiv API 关键词搜索 | `submittedDate` 降序 | **相关性** — 你指定的领域最新论文 |
| 🔥 跨领域热门 | alphaxiv.org 首页抓取 | alphaxiv 内部热度算法 | **热度** — 全 AI 领域社区讨论度最高的论文 |
| 🤗 HuggingFace Daily | huggingface.co/papers 页面抓取 | 社区 curated | **精选** — HuggingFace 社区每日精选论文 |

**LLM Rerank 流程**：
1. 三源数据去重合并，预排序（基于主题匹配度 + 推荐历史 + 元信息）
2. LLM 对每篇论文评估：relevance（主题相关度×2）、novelty（新颖性）、impact（影响力）
3. 综合 score = (relevance×2 + novelty + impact) / 4，生成 Top Picks（≥7分）
4. 最终报告按板块 + LLM 评分双维度呈现

## 扩展方向（TODO）

- [x] 接入 alphaxiv 热度源，补充跨领域高影响力论文
- [x] 推荐历史追踪 + 重复推荐高亮
- [x] 接入 cron，定时推送日报（每日 04:00 到 qqbot）
- [x] 基于 LLM 对摘要进行再总结和重要性评分（rerank）
- [x] 接入 HuggingFace Daily Papers
- [x] 中文摘要 + 英文原文双语言输出
- [x] LLM 自动过滤低相关论文（<6.0分剔除）
- [x] 按日期分文件保存日报（digests/YYYY-MM-DD.md）
- [x] 周期性提炼：周总结 + 月总结
- [x] 论文上下文对话机制（日报后追问自动识别论文）
- [ ] 支持按 arXiv category（cs.AI, cs.CL, cs.LG）订阅
- [ ] 接入 Semantic Scholar 引用增速信号
- [ ] 支持论文 PDF 自动下载 + 关键图表提取
