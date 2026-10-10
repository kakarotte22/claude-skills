---
name: model-train
description: 端到端编排模型训练流程，依次创建训练任务节点、发布到生产环境、执行节点、获取运行日志并在浏览器打开 logview 链接。仅支持用户手动调用（/model-train），不允许模型自动触发。接收 --train_table_name（训练表名）、--val_table_name（验证表名）、--label_col（标签列名）三个必填参数，以及可选的 --keep_cols（保留列）。
disable-model-invocation: true
---

## 功能

端到端编排模型训练流程，依次调用以下技能：

1. `create-train-task` — 创建模型训练计算节点
2. `publish-node` — 将节点发布到生产环境
3. `execute-node` — 触发节点运行
4. `get-instance-log` — 获取实例运行日志
5. 在浏览器中打开 logview 链接

## 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--train_table_name` | ✅ | 训练表名，格式 `project.table`，例如 `du_risk_training.train_table` |
| `--val_table_name` | ✅ | 验证表名，格式 `project.table`，例如 `du_risk_training.val_table` |
| `--label_col` | ✅ | 标签列名，例如 `is_bad` |
| `--keep_cols` | ❌ | 保留列，逗号分隔，例如 `uid,req_id`。不传则使用默认值 `request_id,user_id,uid,userid` |

缺少任意必填参数时，提示：
```
❌ 缺少必填参数，用法：
/model-train --train_table_name <训练表名> --val_table_name <验证表名> --label_col <标签列名> [--keep_cols <保留列>]
示例：/model-train --train_table_name du_risk_training.train_table --val_table_name du_risk_training.val_table --label_col is_bad
```

---

## 执行流程

### 第零步：解析参数

从用户输入中提取：
- `TRAIN_TABLE_NAME`：`--train_table_name` 的值
- `VAL_TABLE_NAME`：`--val_table_name` 的值
- `LABEL_COL`：`--label_col` 的值
- `KEEP_COLS`：`--keep_cols` 的值（可选，不提供则为空字符串）

输出产物固定写入 `du_risk_training` 项目，记为 `OUTPUT_PROJECT = du_risk_training`（与训练表所在项目无关）。

若任意必填参数缺失，输出上方错误提示后**立即停止**，不再执行后续步骤。

---

### 第一步：创建模型训练节点

调用 `create-train-task` 技能，传入参数：
- 第一个参数：`TRAIN_TABLE_NAME`
- 第二个参数：`VAL_TABLE_NAME`
- 第三个参数：`LABEL_COL`
- 第四个参数：`KEEP_COLS`（若用户未提供则不传此参数）

从返回结果中提取：
- **节点 ID**（CLI 返回 JSON 中的 `Id` 字段），用于第二步
- **节点名称**（`NODE_NAME` 行的值），格式如 `训练任务_手动_20260401_154605_366`
- **时间戳后缀**：节点名称中 `_手动_` 之后的部分，记为 `SUFFIX`（如 `20260401_154605_366`）

根据 `OUTPUT_PROJECT = du_risk_training` 和 `SUFFIX`，按固定模板构造 5 个输出产物表名：
- `训练集打分结果表`：`du_risk_training.model_train_skills_predictions_train_{SUFFIX}`
- `验证集打分结果表`：`du_risk_training.model_train_skills_predictions_val_{SUFFIX}`
- `训练集分箱报告`：`du_risk_training.model_train_skills_predictions_train_report_{SUFFIX}`
- `验证集分箱报告`：`du_risk_training.model_train_skills_predictions_val_report_{SUFFIX}`
- `模型文件`：`du_risk_training.model_train_skills_predictions_train_booster_{SUFFIX}`

**向用户展示：**
```
✅ 第一步完成：节点已创建
节点名称：<node_name>
节点 ID：<node_id>

📦 输出产物（任务完成后可查）：
  训练集打分结果表：du_risk_training.model_train_skills_predictions_train_<SUFFIX>
  验证集打分结果表：du_risk_training.model_train_skills_predictions_val_<SUFFIX>
  训练集分箱报告：du_risk_training.model_train_skills_predictions_train_report_<SUFFIX>
  验证集分箱报告：du_risk_training.model_train_skills_predictions_val_report_<SUFFIX>
  模型文件：du_risk_training.model_train_skills_predictions_train_booster_<SUFFIX>
```

---

### 第二步：发布节点到生产环境

调用 `publish-node` 技能，传入参数：
- `--object-ids <node_id>`（第一步获取的节点 ID）

**向用户展示：**
```
✅ 第二步完成：节点已发布到生产环境
节点任务 ID：<node_task_id>
```

从返回结果中提取 **节点任务 ID**（即 `Node.TaskId` 字段，整数类型），用于第三步。

---

### 第三步：执行节点

调用 `execute-node` 技能，传入参数：
- `--include-node-ids <node_task_id>`（第二步获取的节点任务 ID）
- `--flow-name model_train`

**向用户展示：**
```
✅ 第三步完成：节点已触发运行
实例 ID：<instance_id>
```

从返回结果中提取 **实例 ID**（InstanceId），用于第四步。

---

### 第四步：获取运行日志

等待 **10 秒**（使用 Bash 工具执行 `sleep 10`），让节点有时间启动后，再调用日志接口。

调用 `get-instance-log` 技能，传入参数：
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
🎉 模型训练任务已全部完成！

📋 执行摘要：
  训练表：<TRAIN_TABLE_NAME>
  验证表：<VAL_TABLE_NAME>
  标签列：<LABEL_COL>
  保留列：<KEEP_COLS>（若未指定则显示"默认"）
  节点名称：<node_name>
  节点 ID：<node_id>
  节点任务 ID：<node_task_id>
  实例 ID：<instance_id>
  Logview：<logview_url>

📦 输出产物：
  训练集打分结果表：du_risk_training.model_train_skills_predictions_train_<SUFFIX>
  验证集打分结果表：du_risk_training.model_train_skills_predictions_val_<SUFFIX>
  训练集分箱报告：du_risk_training.model_train_skills_predictions_train_report_<SUFFIX>
  验证集分箱报告：du_risk_training.model_train_skills_predictions_val_report_<SUFFIX>
  模型文件：du_risk_training.model_train_skills_predictions_train_booster_<SUFFIX>
```

---

## 注意事项

- 每一步必须等待上一步成功返回并提取到所需 ID 后，才能继续执行下一步。
- 若任意步骤失败，立即停止并向用户报告具体错误信息，不再执行后续步骤。
- 第四步的 10 秒等待时间是为了确保节点实例已完成初始化，不可省略。
- `publish-node` 返回的 `Node.TaskId`（整数）是 execute-node 需要的节点任务 ID，与节点 ID `Node.Id`（字符串）不同，务必区分。
- 输出产物表名在第一步完成后即可确定，无需解析日志，直接按固定模板拼接。
