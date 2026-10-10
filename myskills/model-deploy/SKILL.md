---
name: model-deploy
description: 仅供手动调用。当用户需要将通过 model-train 技能训练好的模型部署到 DataWorks 生产环境时使用此技能。用户会提供任务名称、模型表名、输入特征表名和输出结果表名，技能将自动完成：从模板拷贝节点、修改配置、设置调度依赖和输出、发布到生产环境的全流程。触发关键词：模型部署、部署模型、deploy model、model-deploy。注意：此技能不自动触发，需用户明确调用（如 /model-deploy）。
version: 1.0.0
tags: [dataworks, aliyun, spark, model-deploy, machine-learning]
---

# 模型部署技能（model-deploy）

## 技能概述

本技能用于将通过 `model-train` 技能训练完成的模型部署到阿里云 DataWorks 生产环境。基于 `du_risk_training` 空间 `模型部署4Agent` 目录下的 `模型部署_模版` 节点，读取其 spec 并按用户参数修改后创建新节点，再执行完整发布流程。

## 必选参数

在开始之前，先向用户确认以下四个必选参数（如果用户已在调用时提供则无需重复询问）：

| 参数 | 说明 |
|------|------|
| `node_name` | 新部署任务的名称 |
| `model_table` | 由 `model-train` 保存的模型文件表名 |
| `input_table` | 输入数据表名（必须是分区表，包含模型预测所需全部特征） |
| `output_table` | 输出表名，用于存放模型预测结果 |

## 执行步骤

收集完四个参数后，直接运行以下命令（一键完成全部流程）：

```bash
python /Users/admin/.claude/skills/model-deploy/scripts/deploy_model.py \
  --node_name "<node_name>" \
  --model_table "<model_table>" \
  --input_table "<input_table>" \
  --output_table "<output_table>"
```

### 脚本内部执行流程

1. **读取模板 spec** —— 从 `模型部署_模版`（节点 ID: `5328940533258691559`）读取完整 spec
2. **构建新节点 spec** —— 修改以下内容：
   - 节点名称改为 `<node_name>`，路径改为 `模型部署4Agent/<node_name>`
   - 替换三个 Spark 配置项：
     ```
     spark.model_table=<model_table>
     spark.input_table=<input_table>
     spark.output_table=<output_table>
     ```
   - 将 `<input_table>` 加入 `inputs.nodeOutputs` 作为同周期依赖
   - 将 `<output_table>` 注册为节点输出（`outputs.nodeOutputs`）
3. **创建节点** —— 调用 `CreateNode` API（`scene=DATAWORKS_PROJECT`）
4. **发布到生产** —— 依次执行 `DEV_CHECK → DEV → PROD_CHECK → PROD` 四个阶段（每阶段完成后按 `stage.code` 字段轮询状态，再推进下一阶段）

### 确认结果

脚本执行完毕后，向用户展示：
- `inner_node_id`：新节点 ID
- `node_task_id`：发布后的调度任务 ID
- 各阶段执行状态

## 关键配置

- **项目空间**：`du_risk_training`（Project ID: `302182`）
- **模板节点 ID**：`5328940533258691559`
- **目标目录**：`模型部署4Agent`
- **发布阶段**：共 5 个（`BUILD_PACKAGE` 自动执行，脚本只需触发后 4 个）

## 错误处理

- **节点已存在**：检查 `node_name` 是否与目录内已有节点重名
- **输出表冲突**：DataWorks 不允许两个节点注册同一 `output_table`，每张输出表只能有一个生产节点写入
- **DEV_CHECK 报"前一阶段失败"**：`BUILD_PACKAGE` 是异步的，脚本已在执行 DEV_CHECK 前自动等待其完成
- **发布阶段失败**：查看具体阶段的 `Message` 字段，可到 DataWorks 控制台查看发布详情

## 前置条件

1. 已配置阿里云访问凭证：
   ```bash
   export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key"
   export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_secret"
   ```

2. 已安装必要依赖：
   ```bash
   pip install alibabacloud-dataworks-public20240518
   pip install alibabacloud-tea-openapi
   pip install alibabacloud-tea-util
   ```
