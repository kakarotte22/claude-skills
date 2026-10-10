---
name: get-feature-importance
description: 在给定的表上使用指定标签列对剩余字段计算特征重要性。仅支持用户手动调用（/get-feature-importance），不允许模型自动触发。接收 --input_table_name（输入表名）、--label_col（标签列名）和可选的 --exclude_cols（排除列）参数，按顺序依次创建节点、发布到生产环境、执行节点、获取运行日志并在浏览器打开 logview 链接。
disable-model-invocation: true
---

## 功能

端到端编排特征重要性计算流程，依次调用以下技能：

1. `create-feature-importance-task` — 创建特征重要性计算节点
2. `publish-node` — 将节点发布到生产环境
3. `execute-node` — 触发节点运行
4. `get-instance-log` — 获取实例运行日志
5. 在浏览器中打开 logview 链接

## 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--input_table_name` | ✅ | 输入表名，格式 `project.table`，例如 `du_risk_training.test_table` |
| `--label_col` | ✅ | 标签列名，例如 `is_bad` |
| `--exclude_cols` | ❌ | 排除列，逗号分隔，例如 `uid,req_id`。不传则使用默认值 `request_id,user_id,uid,userid` |

缺少任意必填参数时，提示：
```
❌ 缺少必填参数，用法：
/get-feature-importance --input_table_name <表名> --label_col <标签列名> [--exclude_cols <排除列>]
示例：/get-feature-importance --input_table_name du_risk_training.test_table --label_col is_bad
示例（指定排除列）：/get-feature-importance --input_table_name du_risk_training.test_table --label_col is_bad --exclude_cols uid,req_id
```

---

## 执行流程

### 第零步：解析参数

从用户输入中提取：
- `INPUT_TABLE_NAME`：`--input_table_name` 的值
- `LABEL_COL`：`--label_col` 的值
- `EXCLUDE_COLS`：`--exclude_cols` 的值（可选，未传则为空）

若任意必填参数缺失，输出上方错误提示后**立即停止**，不再执行后续步骤。

---

### 第一步：创建特征重要性节点

调用 `create-feature-importance-task`技能，传入参数：
- 第一个参数：`INPUT_TABLE_NAME`
- 第二个参数：`LABEL_COL`
- 第三个参数：`EXCLUDE_COLS`（若用户传入了 `--exclude_cols`，则追加；否则不传，让下层技能使用默认值）

**向用户展示：**
```
✅ 第一步完成：节点已创建
节点名称：特征重要性_手动_20260401_154605_366
节点 ID：8593609032826935290
请求 ID：4A91805D-7AAE-5BE4-86DC-5EBC7A3A79D7
输入表名： du_risk_training.test_table
标签列名：is_bad
排除列：request_id,user_id,uid,userid（默认）
结果表名：du_risk_training.model_train_skills_feature_importance_20260401_154605_366
```

从返回结果中提取 **节点 ID**（node_id / object_id），用于第二步。

---

### 第二步：发布节点到生产环境

调用 `publish-node`技能，传入参数：
- `--object-ids <node_id>`（第一步获取的节点 ID）

**向用户展示：**
```
✅ 第二步完成：节点已发布到生产环境
节点任务 ID：<node_task_id>
```

从返回结果中提取 **节点任务 ID**（node task id / task_id），用于第三步。

---

### 第三步：执行节点

调用 `execute-node`技能，传入参数：
- `--include-node-ids <node_task_id>`（第二步获取的节点任务 ID）
- `--flow-name get_feature_importance4ai`

**向用户展示：**
```
✅ 第三步完成：节点已触发运行
实例 ID：<instance_id>
```

从返回结果中提取 **实例 ID**（instance_id），用于第四步。

---

### 第四步：获取运行日志

等待 **10 秒**（使用 `sleep 10` 或 Bash 工具执行 `sleep 10`），让节点有时间启动后，再调用日志接口。

调用 `get-instance-log`技能 ，传入参数：
- 第一个参数：`<instance_id>`（第三步获取的实例 ID）

**向用户展示：**
```
✅ 第四步完成：已获取运行日志
Logview：<logview_url>

日志内容：
<log_content>
```

从返回结果中提取 **logview URL**，用于第五步。

---

### 第五步：在浏览器中打开 logview

使用 Bash 工具执行以下命令，在浏览器中打开 logview 链接：

```bash
open "<logview_url>"
```

**向用户展示：**
```
✅ 第五步完成：已在浏览器中打开 logview
链接：<logview_url>
```

---

## 完成摘要

全部步骤执行完毕后，输出汇总：

```
🎉 特征重要性计算任务已全部完成！

📋 执行摘要：
  输入表：<INPUT_TABLE_NAME>
  标签列：<LABEL_COL>
  排除列：<EXCLUDE_COLS 或 "request_id,user_id,uid,userid（默认）">
  节点 ID：<node_id>
  节点任务 ID：<node_task_id>
  实例 ID：<instance_id>
  Logview：<logview_url>
  结果表名：du_risk_training.model_train_skills_feature_importance_<suffix>
```

**注意**：摘要中的"实例 ID"仅指第三步从 `list-manual-dag-instances` 返回的 DataWorks `InstanceId`（数字格式，如 `1700051607916`）。日志中出现的 `ODPS InstanceId`（字母数字混合格式，如 `20260413082228835gjhsoyi16z7`）是底层 MaxCompute 实例标识，**不得**出现在摘要中。

---

## 注意事项

- 每一步必须等待上一步成功返回并提取到所需 ID 后，才能继续执行下一步。
- 若任意步骤失败，立即停止并向用户报告具体错误信息，不再执行后续步骤。
- 第四步的 10 秒等待时间是为了确保节点实例已完成初始化，不可省略。
