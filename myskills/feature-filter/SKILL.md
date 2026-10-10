---
name: feature-filter
description: 根据特征重要性表对 MaxCompute 数据集进行特征筛选，生成过滤后的新表。当用户提到"按重要性筛选特征"、"剔除低重要性特征"、"feature filter"、"特征过滤"、"只保留重要特征"、"按 importance 筛选列"时触发。仅支持手动调用（/feature-filter），不允许模型自动触发。
disable-model-invocation: true
---

## 功能

根据特征重要性表（含 `feature_name`、`importance`、`importance_prob` 列）和用户描述的筛选条件，自动推断需要**剔除**哪些特征，然后从原始数据集表的全量列中移除这些列，其余列**全部保留**（包括不在特征重要性表中的列和分区列，这些列不受筛选影响，必须保留）。结果写入新表（表名为原表名加 `_filtered` 后缀）。全程通过 pyodps 执行 SQL，AK 从 `/Users/admin/.aliyun/config.json` 中读取。

> **核心原则**：筛选只剔除"在特征重要性表中、且不满足条件"的特征列；原始表中不在特征重要性表里的列（包括分区列）一律保留，不参与筛选判断。

## 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--importance_table` | ✅ | 特征重要性表名，格式 `project.table`，表内必须含 `feature_name`、`importance`、`importance_prob` 三列 |
| `--input_table` | ✅ | 原始数据集表名，格式 `project.table` |
| `--condition` | ✅ | 自然语言描述的筛选条件，支持复合条件。例如："剔除重要性占比低于 0.01 的特征"、"只保留 importance 大于 0.05 的"、"取重要性最高的前 20 个特征，但保留 spu_90d"、"剔除 importance_prob 低于 0.05 的特征，同时强制剔除 bad_feat1, bad_feat2" |

缺少必填参数时，提示：
```
❌ 缺少必填参数，用法：
/feature-filter --importance_table <特征重要性表名> --input_table <原始数据集表名> --condition "<筛选条件描述>"
示例（按占比）：/feature-filter --importance_table du_risk.feat_imp --input_table du_risk.raw_data --condition "剔除 importance_prob 低于 0.01 的特征"
示例（按绝对值）：/feature-filter --importance_table du_risk.feat_imp --input_table du_risk.raw_data --condition "只保留 importance 大于 0.05 的特征"
示例（TOP-N）：/feature-filter --importance_table du_risk.feat_imp --input_table du_risk.raw_data --condition "保留重要性最高的前 30 个特征"
示例（强制保留）：/feature-filter --importance_table du_risk.feat_imp --input_table du_risk.raw_data --condition "剔除 importance_prob 低于 0.05 的特征，但保留 spu_90d"
示例（强制剔除）：/feature-filter --importance_table du_risk.feat_imp --input_table du_risk.raw_data --condition "剔除 importance_prob 低于 0.05 的特征，同时强制剔除 bad_feat1, bad_feat2"
```

---

## 执行流程

### 前置检查：验证 pyodps 是否已安装

在执行任何步骤前，使用 Bash 工具运行以下命令检测 pyodps：

```bash
python3 -c "import odps; print('pyodps OK:', odps.__version__)"
```

**情况 A：输出 `pyodps OK: x.x.x`** → 环境正常，继续执行。创建本次运行的临时目录：

```bash
SKILL_TMPDIR=$(mktemp -d /tmp/feature-filter-XXXXXX)
echo "临时目录：$SKILL_TMPDIR"
```

后续所有中间文件均存放在 `$SKILL_TMPDIR` 下，运行结束后统一清理。

**情况 B：报 `ModuleNotFoundError`** → 立即停止并提示用户安装：

```
❌ 未检测到 pyodps，该 skill 依赖 pyodps 访问 MaxCompute。

请执行以下命令安装：

    pip install pyodps

安装完成后，重新执行 /feature-filter 即可。
```

---

### 第零步：解析参数与推断筛选条件

从用户输入中提取：
- `IMPORTANCE_TABLE`：`--importance_table` 的值（格式 `project.table`）
- `INPUT_TABLE`：`--input_table` 的值（格式 `project.table`）
- `CONDITION_DESC`：`--condition` 的值（自然语言描述）
- `OUTPUT_TABLE`：project 前缀不变，表名加 `_filtered` 后缀。**若表名已以 `_filtered` 结尾，则追加当天日期**，如 `raw_data_filtered` → `raw_data_filtered_20260413`（实际执行时用 `date +%Y%m%d` 获取，勿硬编码固定日期）。

**字段判断（重要）：**

用户描述中的关键词决定筛选字段，若存在歧义，**必须反问，不得擅自假设**：

| 用户描述关键词 | 推断使用字段 | 备注 |
|--------------|------------|------|
| 占比、prob、proportion、比例、百分比、`importance_prob` | `importance_prob` | 明确指向占比字段 |
| `importance`（不含 prob）、绝对值、重要性值、score | `importance` | 明确指向绝对值字段 |
| 仅"重要性"（无其他限定词） | ⚠️ 歧义，必须反问 | 不得擅自假设 |
| 前 N、TOP N、最高的 N 个、排名前 N | `importance` | 按绝对值排序 |
| 后 N、最低的 N 个、倒数 N | `importance` | 按绝对值排序 |

**根据 `CONDITION_DESC` 推断完整的剔除查询 SQL：**

> ⚠️ EXCLUDE SQL 必须是**完整的可执行 SELECT 语句**（含 FROM 子句），不能只写 WHERE 子句片段，否则脚本会报语法错误。

| 筛选类型 | 完整 EXCLUDE SQL 模板 |
|---------|---------------------|
| 阈值过滤（剔除低于，严格小于） | `SELECT feature_name FROM {IMPORTANCE_TABLE} WHERE {field} < {threshold}` |
| 阈值过滤（剔除不超过，含边界） | `SELECT feature_name FROM {IMPORTANCE_TABLE} WHERE {field} <= {threshold}` |
| 阈值过滤（剔除高于，严格大于） | `SELECT feature_name FROM {IMPORTANCE_TABLE} WHERE {field} > {threshold}` |
| 阈值过滤（剔除不低于，含边界） | `SELECT feature_name FROM {IMPORTANCE_TABLE} WHERE {field} >= {threshold}` |
| TOP-N（保留前 N，剔除其余） | `SELECT feature_name FROM {IMPORTANCE_TABLE} WHERE feature_name NOT IN (SELECT feature_name FROM {IMPORTANCE_TABLE} ORDER BY importance DESC NULLS LAST LIMIT {N})` |
| 后 N（直接剔除倒数 N） | `SELECT feature_name FROM {IMPORTANCE_TABLE} ORDER BY importance ASC NULLS LAST LIMIT {N}` |

**推断运算符（剔除方向）：**
- "低于 / 小于 / <" → 剔除 `< 阈值` 的（严格小于）
- "不超过 / 至多 / ≤ / 不大于" → 剔除 `<= 阈值` 的（含边界）
- "高于 / 大于 / >" → 剔除 `> 阈值` 的（严格大于）
- "不低于 / 至少 / ≥ / 不小于"（保留语义）→ 剔除 `< 阈值` 的
- "保留…高于 / 只要…大于" → 剔除 `< 阈值` 的

**复合条件解析（可与主筛选条件叠加）：**

在主筛选条件基础上，用户还可以额外指定**强制保留**或**强制剔除**特定特征名，两者可同时出现：

| 描述关键词 | 含义 | 操作 |
|---|---|---|
| 「但保留 X」/「且名称不为 X」/「除了 X 之外都剔除」/「X 不管重要性必须保留」 | **强制保留**：即使 X 的重要性不达标，也不将其剔除 | 在 EXCLUDE SQL 的 WHERE 子句末尾追加 `AND feature_name NOT IN ('X')` |
| 「但保留 X, Y, Z」/「且名称不为 X, Y, Z」 | **强制保留多个**特征 | 追加 `AND feature_name NOT IN ('X', 'Y', 'Z')` |
| 「同时强制剔除 X, Y」/「另外排除/删除 X, Y」/「无论重要性如何都删除 X」 | **强制剔除**：即使 X 的重要性高，也将其加入排除列表 | 提取为 `FORCE_EXCLUDE_FEATURES`，通过 `--extra_exclude` 参数传给脚本 |

**复合条件示例推断：**
- `"剔除 importance_prob 低于 0.05 的特征，但保留 spu_90d"`
  → EXCLUDE SQL: `SELECT feature_name FROM {IMPORTANCE_TABLE} WHERE importance_prob < 0.05 AND feature_name NOT IN ('spu_90d')`
  → FORCE_EXCLUDE_FEATURES: 无
- `"剔除 importance_prob 低于 0.05 的特征，同时强制剔除 bad_feat1, bad_feat2"`
  → EXCLUDE SQL: `SELECT feature_name FROM {IMPORTANCE_TABLE} WHERE importance_prob < 0.05`
  → FORCE_EXCLUDE_FEATURES: `bad_feat1,bad_feat2`
- `"保留重要性最高的前 20 个特征，但保留 spu_90d，同时强制剔除 leak_feat"`
  → EXCLUDE SQL: `SELECT feature_name FROM {IMPORTANCE_TABLE} WHERE feature_name NOT IN (SELECT feature_name FROM {IMPORTANCE_TABLE} ORDER BY importance DESC NULLS LAST LIMIT 20) AND feature_name NOT IN ('spu_90d')`
  → FORCE_EXCLUDE_FEATURES: `leak_feat`

若自然语言语义模糊无法唯一确定条件，**向用户反问并立即停止**：
```
❓ 无法明确推断筛选条件，请补充说明：
- 您希望按"importance_prob（重要性占比）"还是"importance（重要性绝对值）"筛选？
- 筛选方向是"保留高于阈值"还是"剔除低于阈值"？
- 具体阈值或数量是多少？
```

推断成功后向用户展示，**展示完立即开始执行**（不等待回复，如发现理解有误请尽快告知以中止）：
```
🔍 已推断筛选条件（正在执行，如有误请立即告知）：
  使用字段：importance_prob / importance
  剔除逻辑：WHERE importance_prob < 0.01（示例）
  强制保留：spu_90d（若有）
  强制剔除：bad_feat1, bad_feat2（若有）
  含义：将特征重要性表中满足剔除条件的特征从原始表中删去；强制保留的特征不受阈值影响；强制剔除的特征无论重要性高低均被删去；其余列（含分区列）全部保留
```

若任意必填参数缺失，输出错误提示后**立即停止**。

---

### 第一步：查询特征重要性表，确定需要剔除的特征列表

调用 `scripts/run_filter_query.py`，传入第零步推断出的**完整 EXCLUDE SQL**（所有 `${...}` 变量替换为实际值后再执行）。若存在强制剔除特征，同时传入 `--extra_exclude`。AK 由脚本自动从 `~/.aliyun/config.json` 读取，无需手动传入。

**执行命令（在 `/Users/admin/.claude/skills/feature-filter` 目录下，用实际值替换尖括号内容）：**

```bash
# 无强制剔除特征时：
python scripts/run_filter_query.py \
  --importance_table "<实际的 IMPORTANCE_TABLE，如 du_risk.feat_imp>" \
  --filter_sql "<实际的 EXCLUDE SQL，如 SELECT feature_name FROM du_risk.feat_imp WHERE importance_prob < 0.01>" \
  > "$SKILL_TMPDIR/excluded_features.txt"

# 有强制剔除特征时（追加 --extra_exclude）：
python scripts/run_filter_query.py \
  --importance_table "<实际的 IMPORTANCE_TABLE>" \
  --filter_sql "<实际的 EXCLUDE SQL>" \
  --extra_exclude "<逗号分隔的强制剔除特征名，如 bad_feat1,bad_feat2>" \
  > "$SKILL_TMPDIR/excluded_features.txt"
```

脚本输出格式（每行一个需剔除的特征名，已自动去重）：
```
FEATURE:feat_a
FEATURE:feat_b
...
```

从 `$SKILL_TMPDIR/excluded_features.txt` 中提取所有 `FEATURE:` 开头的行，得到**需剔除特征列表** `EXCLUDED_FEATURES`。

**脚本执行失败处理**：若脚本退出码非零，读取 stderr 输出，**先执行 `rm -rf "$SKILL_TMPDIR"` 清理临时目录**，再向用户报告具体错误后立即停止，不继续执行后续步骤。常见原因：AK 配置缺失或失效、网络不通、SQL 语法错误、MaxCompute 权限不足。

**向用户展示：**
```
✅ 第一步完成：已确定需剔除的特征
剔除条件：${推断出的条件描述}
强制保留：${FORCE_KEEP_FEATURES 或 "无"}
强制剔除（额外）：${FORCE_EXCLUDE_FEATURES 或 "无"}
特征重要性表：${IMPORTANCE_TABLE}
需剔除特征数：N 个
需剔除特征列表（前 10 个）：
  feat_a  importance_prob=0.005
  feat_b  importance_prob=0.003
  ...
```

若 `EXCLUDED_FEATURES` 为空（所有特征均满足条件，无需剔除），提示后**继续执行**：
```
ℹ️  特征重要性表中所有特征均满足条件，无特征被剔除，新表将与原表列完全一致。
```

---

### 第二步：获取原始数据集表的全部列名（含分区列）

调用脚本获取 `INPUT_TABLE` 的所有列名和分区列名（用实际表名替换尖括号内容）：

```bash
python scripts/run_filter_query.py \
  --get_columns "<实际的 INPUT_TABLE，如 du_risk.raw_data>" \
  > "$SKILL_TMPDIR/columns.txt"
```

脚本输出格式：
```
COLUMN:col1
COLUMN:col2
...
PARTITION:ds
PARTITION:region
```

从 `$SKILL_TMPDIR/columns.txt` 中：
- 提取所有 `COLUMN:` 开头的行得到 `ALL_COLUMNS` 列表（普通列）
- 提取所有 `PARTITION:` 开头的行得到 `PARTITION_COLUMNS` 列表（分区列）

分区列**始终保留**，不参与特征重要性筛选。

**脚本执行失败处理**：同第一步，遇到非零退出码**先 `rm -rf "$SKILL_TMPDIR"` 清理**，再立即停止并报告具体错误。

**向用户展示：**
```
✅ 第二步完成：已获取原始数据集表结构
原始表：${INPUT_TABLE}
普通列数：M 列
分区列：${PARTITION_COLUMNS 列表，或 "无（非分区表）"}
```

---

### 第三步：计算最终保留列，构造并执行建表 SQL

**保留规则（核心）**：
- `FINAL_COLUMNS` = `ALL_COLUMNS` 中**不在** `EXCLUDED_FEATURES` 里的所有列，再加上 `PARTITION_COLUMNS`（分区列无条件追加到 SELECT 末尾）
- 原始表中不在特征重要性表中的列：**无条件保留**，不受筛选影响
- 只有"在特征重要性表中 AND 不满足筛选条件"的列才被剔除

**额外检查：**

1. 对 `EXCLUDED_FEATURES` 中的所有特征（包括 `extra_exclude` 强制剔除项），检查是否存在于 `ALL_COLUMNS`。若有不存在的，记录提示（不阻断流程）：
```
ℹ️  以下特征在原始表中不存在（可能已被预处理移除或名称有误），跳过：feat_x, feat_y
```

2. 若 `FINAL_COLUMNS` 为空，立即停止：
```
❌ 筛选后无任何列剩余，无法创建新表。请检查筛选条件是否过于严格后重试。
```

构造建表 SQL 并向用户展示预览：
```
✅ 第三步：即将执行建表 SQL
原始列数：M 列（普通列）+ P 列（分区列）
剔除列数：N 列（仅剔除在特征重要性表中且不满足条件的列）
保留列数：M-N+P 列
输出表名：${OUTPUT_TABLE}

SQL：
------
DROP TABLE IF EXISTS ${OUTPUT_TABLE};
CREATE TABLE ${OUTPUT_TABLE} AS
SELECT
    col1,
    col2,
    ...（普通保留列）
    ds,
    region
    ...（分区列，始终保留）
FROM ${INPUT_TABLE};
------
```

> ⚠️ 注意：输出表为**非分区表**（数据完整保留，但不继承原表分区结构）。如需输出分区表，请告知以便手动处理。

先执行删除旧表（若存在），再执行建表（用实际值替换尖括号内容）：

```bash
# 第一步：删除旧表
python scripts/run_filter_query.py \
  --create_table_project "<实际的 OUTPUT_PROJECT，如 du_risk>" \
  --create_table_sql "DROP TABLE IF EXISTS <实际的 OUTPUT_TABLE，如 du_risk.raw_data_filtered>"

# 第二步：建表
python scripts/run_filter_query.py \
  --create_table_project "<实际的 OUTPUT_PROJECT>" \
  --create_table_sql "<实际的 CREATE TABLE AS SELECT 语句>"
```

**脚本执行失败处理**：遇到非零退出码**先 `rm -rf "$SKILL_TMPDIR"` 清理临时目录**，再立即停止并报告具体错误，不继续执行。

等待执行成功后展示：
```
✅ 第三步完成：筛选后的新表已成功创建
输出表名：${OUTPUT_TABLE}
保留列数：M-N+P 列
```

---

## 完成摘要

```
🎉 特征筛选完成！

📋 执行摘要：
  特征重要性表：${IMPORTANCE_TABLE}
  原始数据集表：${INPUT_TABLE}
  筛选条件：${推断出的条件描述}
  原始列数：M 列（含 P 个分区列）
  剔除列数：N 列（特征重要性表中不满足条件的特征）
  保留列数：M-N+P 列
  输出表名：${OUTPUT_TABLE}
```

### 清理临时文件

建表成功后，删除本次运行的临时目录：

```bash
rm -rf "$SKILL_TMPDIR"
echo "🧹 临时文件已清理：$SKILL_TMPDIR"
```

---

## 注意事项

- 每一步必须等待上一步成功返回后才能继续；任意步骤失败立即停止并报告具体错误。
- 特征名匹配采用**精确匹配**（区分大小写）。
- 推断筛选条件时，若语义有歧义（尤其"重要性"一词不含明确字段限定词），**必须反问用户，不得擅自假设**。
- AK 由脚本内部自动从 `~/.aliyun/config.json` 读取，不通过命令行参数传入。
- **EXCLUDE SQL 必须是完整的 SELECT 语句（含 FROM 子句），不能只传 WHERE 子句片段。**
- `OUTPUT_TABLE` 命名规则：若已以 `_filtered` 结尾，追加当天日期（执行时用 `date +%Y%m%d` 获取，不要硬编码）。
