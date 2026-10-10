---
name: execute-node
description: 手动执行 DataWorks 上的任务节点（触发 run-manual-dag-nodes）。仅支持用户手动调用（/execute-node），不允许模型自动触发。
disable-model-invocation: true
---

## 功能

在阿里云 DataWorks 生产环境中，手动触发指定业务流程（DAG）中的一个或多个节点运行。

## 参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--include-node-ids` | **必填** | — | 节点任务 ID，多个 ID 用逗号分隔 |
| `--flow-name` | **必填** | — | 业务流程（DAG）名称 |
| `--project-name` | 选填 | `du_risk_training` | DataWorks 项目名称 |
| `--biz-date` | 选填 | 昨日，格式 `YYYY-MM-DD 00:00:00` | 业务日期 |

## 执行步骤

### 第一步：解析并校验参数

从用户输入中提取：
- `--include-node-ids <值>` → `node_ids`（**必填**，不可为空）
- `--flow-name <值>` → `flow_name`（**必填**，不可为空）
- `--project-name <值>` → `project_name`，默认 `du_risk_training`
- `--biz-date <值>` → `biz_date`，默认为**当前日期的前一天**，格式 `YYYY-MM-DD 00:00:00`

**如果 `--include-node-ids` 或 `--flow-name` 未提供或为空，立即输出以下错误并停止执行：**

```
错误：缺少必填参数 --include-node-ids 或 --flow-name

用法：
  /execute-node --include-node-ids <节点ID> --flow-name <流程名> [选项]

选项：
  --include-node-ids  <ID>          节点任务ID（必填）
  --flow-name         <名称>        业务流程名称（必填）
  --project-name      <名称>        项目名称（默认：du_risk_training）
  --biz-date          <日期>        业务日期（默认：昨日，格式：2020-11-11 00:00:00）

示例：
  /execute-node --include-node-ids 1034632028 --flow-name get_feature_importance4ai
  /execute-node --include-node-ids 1034632028 --flow-name my_flow --biz-date "2025-01-15 00:00:00"
  /execute-node --include-node-ids 1034632028 --flow-name my_flow --project-name my_project
```

### 第二步：计算默认业务日期

若用户未指定 `--biz-date`，执行以下命令获取昨日日期：

```bash
date -v-1d "+%Y-%m-%d 00:00:00"
```

### 第三步：执行命令

将参数填入后执行：

```bash
aliyun dataworks-public run-manual-dag-nodes \
  --project-env PROD \
  --project-name "<project_name>" \
  --flow-name "<flow_name>" \
  --biz-date "<biz_date>" \
  --include-node-ids <node_ids> \
  --api-version 2020-05-18 \
  --region cn-hangzhou
```

### 第四步：查询运行实例

从第三步结果中提取 `DagId`，执行以下命令查询本次 DAG 产生的实例：

```bash
aliyun dataworks-public list-manual-dag-instances \
  --project-env PROD \
  --project-name "<project_name>" \
  --dag-id <DagId> \
  --api-version 2020-05-18 \
  --region cn-hangzhou
```

**返回样例**：

```json
{
  "Instances": [
    {
      "Status": "SUCCESS",
      "ModifyTime": 1773975021629,
      "InstanceId": 1700013667788,
      "DagType": "BUSINESS_PROCESS_DAG",
      "NodeName": "策略推荐_手动_副本脚本_20260319_tets_api",
      "CreateTime": 1773974459964,
      "ParamValues": "",
      "CreateUser": "283505032729958038",
      "CycTime": 1773849600000,
      "BeginWaitTimeTime": 1773974460126,
      "DagId": 1700011020636,
      "BeginRunningTime": 1773974465623,
      "FinishTime": 1773975021629,
      "TaskType": "MANUAL",
      "NodeId": 1034176597,
      "BeginWaitResTime": 1773974460665,
      "BizDate": 1773763200000
    }
  ],
  "RequestId": "7858f3db53ce1649b81ae6e0d9e8812b"
}
```

从返回结果中提取每个实例的 `InstanceId`、`NodeName`、`Status`。

若查询失败或 `Instances` 为空，跳过此步骤，实例 ID 显示为 `获取失败，请手动查询`。

### 第五步：解析并展示结果

按以下格式输出最终结果（单个实例）：

```
节点执行已触发

节点 ID:      <node_ids>
项目名称:     <project_name>
业务流程:     <flow_name>
业务日期:     <biz_date>

请求追踪 ID:  <RequestId>
业务流程 ID:  <DagId>
实例 ID:      <InstanceId>  (<NodeName>, <Status>)

提示：可使用 /get-instance-log <InstanceId> 查看节点运行日志。
```

若有多个实例，每个实例单独一行展示：

```
实例 ID:      <InstanceId1>  (<NodeName1>, <Status1>)
实例 ID:      <InstanceId2>  (<NodeName2>, <Status2>)
```

## 错误处理

### 1. 未安装 aliyun CLI

提示用户安装：

```bash
brew install aliyun-cli
```

### 2. 未配置 AccessKey

提示用户配置：

```bash
aliyun configure set \
  --profile AkProfile \
  --mode AK \
  --access-key-id <yourAccessKeyID> \
  --access-key-secret <yourAccessKeySecret> \
  --region "cn-hangzhou"
```

### 3. 常见错误码

| HttpStatusCode | 含义 | 处理建议 |
|----------------|------|---------|
| 400 | 参数错误 | 检查节点 ID、项目名、业务流程名是否正确 |
| 403 | 权限不足 | 确认 AK 拥有 DataWorks 执行权限 |
| 404 | 资源不存在 | 确认节点 ID 和流程名存在于指定项目 |
| 500 | 服务端错误 | 稍后重试，或联系管理员 |

## 使用示例

最简调用（必填参数）：
```
/execute-node --include-node-ids 1034632028 --flow-name get_feature_importance4ai
```

指定业务日期：
```
/execute-node --include-node-ids 1034632028 --flow-name get_feature_importance4ai --biz-date "2025-01-15 00:00:00"
```

完整参数调用：
```
/execute-node --include-node-ids 1034632028 --flow-name get_feature_importance4ai --project-name du_risk_training --biz-date "2025-01-15 00:00:00"
```
