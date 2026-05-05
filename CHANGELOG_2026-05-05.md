# ArXiv Digest 修改总结 — 2026-05-05

---

## 已修复问题

### P0-1 ✅ 统一 arXiv API 调用间隔

**新增 `_arxiv_call_delay()` 全局函数**：
- 追踪上一次 arXiv 调用的时间戳
- 确保任何两个 arXiv API 调用之间至少间隔 3 秒
- 自动 sleep 补足不足的部分

**调用序列现在变为**：
```
topic:LLM post-training → arXiv API
  ↓ _arxiv_call_delay()  (至少3s)
topic:agentic RL → arXiv API
  ↓ _arxiv_call_delay()  (至少3s)
topic:LLM agent → arXiv API
  ↓ _arxiv_call_delay()  (至少3s)  ← 新增！
alphaxiv_ids → alphaxiv.org (非 arXiv)
  ↓ _arxiv_call_delay()  (至少3s)  ← 新增！
alphaxiv_papers → fetch_by_ids → arXiv API
  ↓ _arxiv_call_delay()  (至少3s)  ← 新增！
huggingface_ids → huggingface.co (非 arXiv)
  ↓ _arxiv_call_delay()  (至少3s)  ← 新增！
huggingface_papers → fetch_by_ids → arXiv API
```

**fetch_by_ids 内部 batch 之间也保留 `sleep(3)`**。

---

### P0-2 ✅ `fetch_by_ids` 纳入进度跟踪

**数据源拆分**：

| 原阶段 | 新阶段 | 说明 |
|-------|-------|------|
| `alphaxiv_ids` | `alphaxiv_ids` + `alphaxiv_papers` | IDs 从 alphaxiv.org 抓，论文详情从 arXiv API 查，分别跟踪 |
| `huggingface` | `huggingface_ids` + `huggingface_papers` | IDs 从 huggingface.co 抓，论文详情从 arXiv API 查，分别跟踪 |
| `topic:xxx` | 不变 | 本身就只调一次 arXiv API |

**效果**：
- 如果 `alphaxiv_ids` 成功但 `alphaxiv_papers` 失败（429），进度文件会正确记录：
  - `alphaxiv_ids: ok`（IDs 已拿到）
  - `alphaxiv_papers: failed`（需要重试）
- 下次重试时，跳过 `alphaxiv_ids`，只重试 `alphaxiv_papers`
- **不再浪费已成功的进度**

---

### P1-3 ✅ 精细化状态判断

`fetch_source_with_progress` 现在支持三种状态：

| 状态 | 含义 | 重试时行为 |
|------|------|-----------|
| `ok` | 有数据，成功 | **跳过**（已有缓存） |
| `empty` | 正常返回但 0 条（如 HF 今天没新论文） | **可重试**（可能之后有） |
| `failed` | 网络/API 错误（如 429、连接超时） | **必须重试** |

**判断逻辑**：
- arXiv 相关源（topic、*_papers）：空结果 = `failed`（arXiv 不应该完全空）
- 非 arXiv 源（alphaxiv_ids、huggingface_ids）：空结果 = `empty`（可能确实没数据）

---

### P1-4 ✅ 增加 cron timeout

- **900s → 1800s**（15 分钟 → 30 分钟）
- 支持 exit code 2 时等待 10 分钟重试 `--raw`

---

### P2-5 ✅ 更 robust 的 429 检测

`fetch_url` 改用 curl `-w "\n___CURL_HTTP_CODE:%{http_code}\n"`：
- 从 stdout 尾部解析真实 HTTP 状态码
- 不再猜 body 内容（不再依赖 "Rate exceeded." 的字面匹配）
- 支持 `429` 和任意错误响应体的检测

---

## 修改的文件

1. `scripts/generate_digest.py` — 脚本核心逻辑
2. `cron job` — 更新 payload 和 timeout

---

## 遗留事项

- **export.arxiv.org 目前仍间歇性 429**（IP/代理层面的问题，非脚本问题）
- 新设计允许脚本在 429 时保存部分数据，等待重试补全
- 下次 cron 运行（5 月 6 日 04:00）将验证完整流程
