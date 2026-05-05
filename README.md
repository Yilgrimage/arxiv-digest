# arxiv-digest

每日 arXiv 论文日报生成器。自动聚合关注领域 + 跨领域热门 + HuggingFace Daily Papers，通过 LLM 智能 rerank 生成结构化中文日报。

## 功能

- **三源并行**：arXiv 关键词搜索 + alphaxiv 跨领域热门 + HuggingFace Daily Papers
- **LLM 逐篇评估**：relevance × 2 + novelty + impact 综合评分，中文摘要 + 点评
- **自动过滤**：综合评分 < 6.0 的论文自动剔除
- **重复高亮**：连续多次被推荐的论文自动标记 🔥🔥
- **外部热度信号**：HackerNews 讨论度（🔥HN pts/cmt）
- **论文上下文对话**：日报后追问某篇论文，自动识别并加载完整上下文
- **增量收集 + 重试**：arXiv API 429 时保存已成功的进度，稍后补全
- **QQBot 定时推送**：每日 04:00（Asia/Shanghai）自动推送

## 快速开始

```bash
cd skills/arxiv-digest

# 第1步：收集原始数据
python3 scripts/generate_digest.py --raw

# 第2步：LLM 逐篇评估（写入 memory/llm_scores.json）
# 在当前 session 中逐篇评估论文

# 第3步：生成最终日报
python3 scripts/generate_digest.py --rerank-json memory/llm_scores.json --output memory/daily_digest.md
```

## 自动化（cron）

已配置每日 **04:00（Asia/Shanghai）** 自动执行完整流程并推送到 QQBot。

如需立即触发测试：
```bash
openclaw cron run arxiv-digest-daily
```

如需手动补发日报：
```bash
bash scripts/resend_daily_digest.sh [YYYY-MM-DD]
```

## 配置

### 关注领域 — `config/topics.json`

```json
{
  "topics": ["LLM post-training", "agentic RL", "LLM agent"],
  "per_topic_count": 5
}
```

### 推荐风格 — `config/preferences.json`

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
    "score_threshold": 7,
    "filter_threshold": 6.0,
    "filter_low_score": true
  }
}
```

## 目录结构

```
skills/arxiv-digest/
├── config/                 # 用户配置
├── scripts/                # 核心脚本
│   ├── generate_digest.py  # 日报生成主脚本
│   ├── heat_signals.py     # 外部热度信号收集
│   ├── search_papers.py    # 论文语义检索
│   └── resend_daily_digest.sh  # 手动补发
├── memory/                 # 运行时数据
│   ├── digests/            # 按日期保存的日报
│   ├── papers/             # 单篇论文档案
│   └── llm_scores.json     # LLM 评估结果
└── docs/                   # 设计文档与审计报告
```

## 数据源与排序依据

| 板块 | 来源 | 排序依据 | 代表什么 |
|------|------|----------|----------|
| 📌 关注领域 | arXiv API 关键词搜索 | `submittedDate` 降序 | 你指定的领域最新论文 |
| 🔥 跨领域热门 | alphaxiv.org 首页抓取 | alphaxiv 内部热度算法 | 全 AI 领域社区讨论度最高的论文 |
| 🤗 HuggingFace Daily | huggingface.co/papers | 社区 curated | HuggingFace 社区每日精选 |

## 扩展方向（TODO）

- [ ] Semantic Scholar 引用增速（需 API key）
- [ ] Reddit / X(Twitter) 讨论度
- [ ] 支持按 arXiv category（cs.AI, cs.CL, cs.LG）订阅
- [ ] 论文 PDF 自动下载 + 关键图表提取
- [ ] 用户反馈收集（QQBot 回复解析、emoji 反馈）
- [ ] 个性化 LLM 评估 prompt（基于反馈调优）

## License

MIT
