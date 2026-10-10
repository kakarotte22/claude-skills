---
name: logview-stdout
description: 从 MaxCompute Spark 任务的 LogView 中自动提取 Driver StdOut 日志。当用户说"从 logview 提取 stdout"、"查看 spark 任务日志"、"获取 logview stdout"、"提取任务输出"、"看一下任务的输出"，或提供了 MaxCompute job-insights URL 并想查看日志内容时，主动使用此技能。即使用户只说"看看日志"或"任务输出是什么"，只要上下文涉及 MaxCompute/Spark 任务，也应触发此技能。
---

## 概述

通过 Chrome CDP（Chrome DevTools Protocol）自动化操作浏览器，从 MaxCompute LogView 页面提取 Spark Driver 的完整 StdOut 输出。

**前置要求**：用户需提供 LogView URL，支持两种格式：
```
# 新版 job-insights 格式
https://maxcompute.console.aliyun.com/cn-hangzhou/job-insights?h=...&p=<项目名>&i=<任务ID>

# 旧版 logview 格式（同样支持）
http://logview.odps.aliyun.com/logview/?h=...&p=<项目名>&i=<任务ID>&token=<token>
```
样例1：
```
https://maxcompute.console.aliyun.com/cn-hangzhou/job-insights?h=https://service.cn-hangzhou.maxcompute.aliyun-inc.com/api&p=du_risk_training&i=20260520030118792gdrog944o1a
```
样例2：
```
http://logview.odps.aliyun.com/logview/?h=http://service.cn-hangzhou.maxcompute.aliyun-inc.com/api&p=du_risk_training&i=20260520030118792gdrog944o1a&token=ZG9kTU5sNHZjV0VnL0tWUUl0YklubHo4ZmhBPSxPRFBTX09CTzoxODE2NTYzNTQxODk5NzAwLDE3Nzk4NTA4NzgseyJTdGF0ZW1lbnQiOlt7IkFjdGlvbiI6WyJvZHBzOlJlYWQiXSwiRWZmZWN0IjoiQWxsb3ciLCJSZXNvdXJjZSI6WyJhY3M6b2RwczoqOnByb2plY3RzL2R1X3Jpc2tfdHJhaW5pbmcvaW5zdGFuY2VzLzIwMjYwNTIwMDMwMTE4NzkyZ2Ryb2c5NDRvMWEiXX1dLCJWZXJzaW9uIjoiMSJ9
```

---

## 执行流程
第一步：检查用户提供的 `logview url` 是否为支持的格式，如果不是则提示用户输入正确的格式，待用户输入正确格式后继续执行。

第二步：阅读 [claude-code-logview-stdout-guide.md](目录为：references/claude-code-logview-stdout-guide.md) 文档，按照文档中记录的方法，从 `logview url` 中提取 StdOut 信息。
## 输出格式

成功时展示：

```
✅ StdOut 日志提取成功
任务 ID：<任务ID>
─────────────────────────────
<完整 StdOut 内容>
─────────────────────────────
```
样例：
```
pt: 20260415
入模特征数量: 84
开始保存打分结果...
打分完成，结果已写入分区: pt=20260415
INFO:py4j.clientserver:Closing down clientserver connection
```

