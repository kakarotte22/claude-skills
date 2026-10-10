---
name: publish-node
description: 将节点发布到生产环境。当用户已经创建了一个节点，需要发布到生产环境时使用。
disable-model-invocation: true
---

## 功能

将用户已经创建的节点发布到生产环境。

## 参数

- `--object-ids` (必填): 节点ID
- `--project-id` (可选): 项目ID，默认值为 `302182`

## 执行步骤

### 第一步：解析参数

从用户输入中解析以下参数：
- `--object-ids <值>` 作为 `node_id`（必填）
- `--project-id <值>` 作为 `project_id`；未提供则默认为 `302182`

如果 `--object-ids` 未提供，输出以下错误并停止执行：
```
错误：请提供节点ID
用法：/publish-node --object-ids <节点ID> [--project-id <项目ID>]
示例：/publish-node --object-ids 1700031357290
示例：/publish-node --object-ids 1700031357290 --project-id 999999
```

### 第二步：创建发布流程

执行以下命令创建发布流程：
```bash
aliyun dataworks-public create-pipeline-run --project-id <project_id> --type Online --object-ids "<node_id>" --api-version 2024-05-18 --region cn-hangzhou
```

从返回结果中提取 `Id` 字段，作为后续步骤的 `publish_id`。

**返回样例**
```json
{
  "RequestId": "AFD3B1CB-D91C-59EB-988A-280FBCEC5149",
  "Id": "b7130cff-c3fa-4900-875d-43aeae13dddd"
}
```

如果命令失败或返回结果中无 `Id` 字段，输出错误信息并停止执行：
```
错误：创建发布流程失败，请检查节点ID是否正确
```

### 第三步：依次执行发布阶段

按顺序执行以下四个阶段，**每个阶段必须单独调用一次 Bash 工具，不可将多个阶段用 `&&` 或 `;` 合并为一条命令**。每个阶段必须在上一阶段返回 `"Success": true` 后才能继续。任一阶段失败则立即停止并报告失败的阶段。

#### 3.1 发布到 DEV_CHECK 环境
```bash
aliyun dataworks-public exec-pipeline-run-stage --project-id <project_id> --id "<publish_id>" --code DEV_CHECK --api-version 2024-05-18 --region cn-hangzhou
```

#### 3.2 发布到 DEV 环境
```bash
aliyun dataworks-public exec-pipeline-run-stage --project-id <project_id> --id "<publish_id>" --code DEV --api-version 2024-05-18 --region cn-hangzhou
```

#### 3.3 发布到 PROD_CHECK 环境
```bash
aliyun dataworks-public exec-pipeline-run-stage --project-id <project_id> --id "<publish_id>" --code PROD_CHECK --api-version 2024-05-18 --region cn-hangzhou
```

#### 3.4 发布到 PROD 环境
```bash
aliyun dataworks-public exec-pipeline-run-stage --project-id <project_id> --id "<publish_id>" --code PROD --api-version 2024-05-18 --region cn-hangzhou
```

**每个阶段的返回样例**
```json
{
  "RequestId": "EA2F43D3-444F-5AA6-A125-296E9EC904B4",
  "Success": true
}
```

**阶段失败时的输出格式：**
```
错误：发布阶段 <阶段名> 失败
RequestId: <requestId>
请检查节点配置或联系管理员
```

### 第四步：获取发布后的节点信息

```bash
aliyun dataworks-public get-node --project-id <project_id> --id "<node_id>" --api-version 2024-05-18 --region cn-hangzhou
```

**返回样例**
```json
{
  "RequestId": "B0F470AF-B056-58C1-9CD0-36B168B8CA3D",
  "Node": {
    "ModifyTime": 1775037845000,
    "Owner": "283505032729958038",
    "TaskId": 1034606593,
    "CreateTime": 1775037845000,
    "ProjectId": 302182,
    "Id": "8855376266758523685",
    "Name": "特征重要性_手动_20260401_180358_321"
  }
}
```

### 第五步：格式化输出结果

输出以下格式的发布结果：

```
发布节点结果

阶段执行情况：
DEV_CHECK  ✓
DEV        ✓
PROD_CHECK ✓
PROD       ✓

节点信息：
请求追踪ID: <RequestId>
节点名称:   <Node.Name>
节点ID:     <Node.Id>
TaskId:     <Node.TaskId>
ProjectId:  <Node.ProjectId>
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
|---------------|------|---------|
| 400 | 参数错误 | 检查节点ID是否正确；若报"前序阶段失败"，说明上一阶段被合并执行导致竞争，需重建 pipeline 后逐阶段单独执行 |
| 403 | 权限不足 | 检查AK是否有DataWorks权限 |
| 404 | 实例不存在 | 确认节点ID和项目环境 |
| 500 | 服务端错误 | 稍后重试 |

## 使用示例

使用默认项目ID：
```
/publish-node --object-ids 4679068819058885093
```

指定项目ID：
```
/publish-node --object-ids 4679068819058885093 --project-id 999999
```

输出格式：
```
发布节点结果

阶段执行情况：
DEV_CHECK  ✓
DEV        ✓
PROD_CHECK ✓
PROD       ✓

节点信息：
请求追踪ID: B0F470AF-B056-58C1-9CD0-36B168B8CA3D
节点名称:   特征重要性_手动_20260401_180358_321
节点ID:     4679068819058885093
TaskId:     1034606593
ProjectId:  302182
```
