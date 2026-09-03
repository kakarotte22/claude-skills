---
name: wikiskill
description: 从智能体的执行经验(成功/失败轨迹、历史对话、工具调用记录、复盘笔记)自动提取并沉淀为持久化知识库：把散落的经验编译成结构化的 wiki patterns，再据此归纳为可复用的技能。纯经验提取，不涉及模型训练、验证集评分或门控回滚。当用户提供一批执行记录/成功失败案例/复盘内容、希望自动总结出规律和可操作经验、或想把零散经验整理成团队可复用的技能文档时使用。触发词：经验提取、经验沉淀、经验总结、wiki 编译、复盘提炼、案例沉淀、技能归纳、经验库、知识沉淀。
---

# WikiSkill：把执行经验自动编译成持久知识（无训练版）

灵感源自论文《WikiSkill: Compiling Agent Experience into Persistent Knowledge for Skill Evolution》
(Google Research, arXiv:2608.27454) 的三层知识架构。本 skill **只保留"经验编译"能力**，
移除了模型训练、验证集评分、门控回滚等强化学习式机制，专注一件事：

> 把散落的执行经验 → 结构化 wiki patterns → 可复用技能。

## 核心思想

经验只有在被**结构化沉淀**后才能跨任务复用，否则每次都在原地重新踩坑。
本 skill 把"经验"分成三层，逐层提炼：

- 原始记录（raw）→ 提炼成**模式**（patterns）→ 归纳成**技能**（skills）

## Workspace 固定路径与初始化

所有经验统一沉淀到固定路径，确保知识跨会话累积、不分散：

```
~/.claude/wikiskill-workspace/
```

**每次执行沉淀前，先完成初始化（建目录）**：若目录不存在则创建，命令如下：

```bash
mkdir -p ~/.claude/wikiskill-workspace/raw \
         ~/.claude/wikiskill-workspace/wiki/patterns \
         ~/.claude/wikiskill-workspace/skills
```

并确保以下基础文件存在（不存在则用空模板创建）：
- `~/.claude/wikiskill-workspace/wiki/index.md`（空索引）
- `~/.claude/wikiskill-workspace/wiki/logs.md`（空日志）
- `~/.claude/wikiskill-workspace/wiki/skill-impact.md`（空归纳记录）

所有 raw / wiki / skills 内容一律写入此路径，不要临时新建别处。

## 三层知识架构

```
~/.claude/wikiskill-workspace/
├── raw/        # 原始经验：完整执行轨迹、对话记录、复盘原文，只追加不改
├── wiki/       # 沉淀后的知识：结构化、累积、只增不减
│   ├── index.md            # 目录索引，列出所有 pattern 及一句话摘要
│   ├── patterns/           # 模式页：每页记录一类失败模式或成功策略
│   ├── logs.md             # 沉淀日志：何时从哪些素材提炼了什么
│   └── skill-impact.md     # 归纳记录：每个技能由哪些 pattern 启发而来
└── skills/     # 可复用技能：从 patterns 归纳出的、可直接执行的技能文档
    └── <skill-name>/
        ├── SKILL.md        # 技能完整内容（后续执行时全文引用）
        └── PURPOSE.md      # 该技能解决什么问题、由哪些 pattern 归纳而来
```

## 核心原则：workspace 是全量汇总，分流只是同步副本

**`~/.claude/wikiskill-workspace/` 是唯一、永久的经验总库。任何经验都永久保留一份在这里，供人员随时查阅。**

- 分层判定与"分流到别处"（写 CLAUDE.md / 归到 skill 的 references / 发布技能）**只是为了让经验在后续场景被有效复用所做的复制同步，绝不从 workspace 移除或覆盖**。
- 每份经验在 workspace 里始终有本体；外面的副本（CLAUDE.md、references、独立 skill）是"投递到使用现场"的同步件。
- 顺序永远是：**先落到 workspace（留档）→ 再分流同步（复用）**。

## 经验分层判定（先留档，再决定如何分流复用）

收到经验时，**先写入 workspace 留档**，再按下面三类判定"如何把副本同步到别处以复用"。一条经验只有一个留档本体，但可以有多种复用分流：

| 类型 | 特征 | 判据 | 复用分流去处 |
|------|------|------|------|
| **常驻型硬约束** | 跨项目、高频、每次必须生效的一条规则/约定 | "下次需要'永远记得这条规则'" | 同步写入**全局 CLAUDE.md**（`~/.claude/CLAUDE.md`） |
| **按需型经验/技巧** | 低频、特定场景、按需检索 | "下次遇到 X 时，需要'查到这条坑'" | 复制到**对应 skill 的 `references/`** 并加引用（见下） |
| **可复用技能** | 一组可执行的多步流程/SOP | "下次遇到，需要'照这套步骤做一遍'" | 归纳为 **skill** 并发布到 `~/.claude/skills/` |

判据一句话：需要"永远记得"→CLAUDE.md；需要"查到这条坑"→references；需要"照着步骤做"→独立 skill。无论去哪个去处，workspace 里的留档本体都保留。

## 复用分流：把副本同步到对应 skill 的 references 目录

按需型经验在 workspace 留档后，**另外复制一份**到对应 skill 下，让它在正确场景被自动带入。**目标目录是已安装的 skill 位置**：

```
~/.claude/skills/<对应skill>/references/
```

### 分流步骤

1. **定位对应 skill**：根据经验主题，判断它属于哪个已有 skill（如 `dataworks-pyspark`、`dataworks-upload`、`model-train`、`model-deploy`、`logview-stdout` 等）。先 `ls ~/.claude/skills/` 查看已有 skill，优先归入最相关的一个。
2. **复制 reference**：在该 skill 下建 `references/` 目录（不存在则建），把经验写成 markdown 放入，命名 `references/<主题>.md`。内容含：触发场景、现象、根因、可操作对策，并在文末标注"留档本体见 `~/.claude/wikiskill-workspace/...`"。
3. **加引用语句**：在该 skill 的 `SKILL.md` 里补一句"遇到 X 场景时，先阅读 [<主题>.md](目录为：references/<主题>.md)"，让触发该 skill 时能自动读到这份经验。
4. 若该经验 **没有对应 skill 可归**（独立成一类且够常用），则按下方"归纳技能"流程给它新建一个带触发词的 skill（同样先在 workspace 留档）。

## 提取流程（纯经验，无训练）

每次收到一批新经验时，遵循**先留档、后分流**的顺序：

### 1. 归置原始经验 → `raw/`（留档本体）
- 原始经验先原样写入 `~/.claude/wikiskill-workspace/raw/`（只追加、不改写），保留时间戳与来源，作为永久证据链与查阅依据。

### 2. 提炼模式 → `wiki/patterns/`（留档本体）
对每条原始经验做根因分析，抽象出**可复用规律**，写成 markdown pattern 页。每个 pattern 页至少包含：

- **触发条件**：什么场景/信号下会出现这个问题（或该策略适用）。
- **现象**：成功/失败的具体表现。
- **根因**：为什么会这样（失败模式尤其要挖根因）。
- **可操作对策**：下次遇到该怎么做/怎么避免（必须可执行，拒绝空话）。
- **来源**：指向 `raw/` 中对应的原始记录。

写入规则：
- 优先**增量更新**已有 pattern（同类经验合并），确有新规律才新建页面。
- 提炼完更新 `index.md`，追加 `logs.md`。

### 3. 分流复用（从留档本体复制副本到使用现场）
每个 pattern 在 workspace 留档后，按分层判定把**副本**同步到复用现场（绝不移除 workspace 本体）：

- **常驻型硬约束** → 同步写入全局 CLAUDE.md，确保每会话生效。**写入前必须先向用户确认**：先说明「发现一条可常驻的硬约束，是否写入全局 CLAUDE.md？」，得到用户同意后才编辑 `~/.claude/CLAUDE.md`；若用户拒绝，则只保留 workspace 留档，不动 CLAUDE.md。写入前先检查 CLAUDE.md 是否已有同义规则，已有则不重复写、仅报告「已存在，无需重复」。
- **按需型经验** → 复制到对应 skill 的 `references/`，并加引用语句（见上节）。
- **可复用技能** → 归纳为独立 skill（见下节）。

### 4. 归纳技能（仅当确为多步流程时才做）
- 当若干 patterns 指向同一类"可照做的流程"时，归纳为一个技能目录（先在 workspace 的 `skills/` 留档）。
- `SKILL.md` 写技能完整执行方法（把 patterns 的对策串成可照做的流程），并在 frontmatter 的 `description` 里写清**触发词**。
- `PURPOSE.md` 写清该技能解决什么问题、归纳自哪些 pattern。
- 归纳出的新 skill 要**复制到 `~/.claude/skills/<name>/`**，才能被任意会话 `/` 触发。
- 同步更新 `skill-impact.md`，记录归纳来源。

## 提炼时遵循的原则

1. **先留档、后分流**：每份经验先落 workspace 汇总库，再复制副本到复用现场；workspace 本体永不删除。
2. **去重合并**：新经验先对照已有 pattern/已有 skill 的 reference，同类就补充，不新开文件，避免膨胀。
3. **对策可执行**：每条经验必须落到"下次具体怎么做"，禁止只描述现象不给出路。
4. **只增不减**：workspace 内容累积，不删除、不回滚（错了就在原处标注修正并写进 logs）。
5. **单点提炼**：一次聚焦一类问题，把它说透，不贪多求全。
6. **可追溯**：每个 pattern/skill 都要能指回 `raw/` 里的原始经验，保留证据链。

## 使用方式

- 直接把一批执行记录、成功失败案例、或复盘文字交给本 skill，即可自动完成分层、提炼与归档。
- 沉淀完成后会告诉你：分了哪些层、新建/更新了哪些 pattern、归档到哪个 skill 的 reference、归纳出哪些技能、各自对应哪些原始素材。
- 后续新经验持续追加即可，知识库会不断累积，无需训练任何模型。