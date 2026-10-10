---
name: rerun-instance
description: 手动重跑 DataWorks 任务实例（rerun-task-instances）。仅支持用户手动调用（/rerun-instance），不允许模型自动触发。
disable-model-invocation: true
---

## 功能

重跑阿里云 DataWorks 中指定的一个或多个任务实例。

## 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--ids` | **必填** | 实例 ID，多个 ID 用空格分隔 |

## 执行步骤

### 第一步：解析并校验参数

从用户输入中提取 `--ids <值>` → `ids`（**必填**，不可为空）。

**如果 `--ids` 未提供或为空，立即输出以下错误并停止执行：**

```
错误：缺少必填参数 --ids

用法：
  /rerun-instance --ids <实例ID>

选项：
  --ids  <ID>  实例 ID，多个 ID 用空格分隔（必填）

示例：
  /rerun-instance --ids 1700045027733
  /rerun-instance --ids 1700045027733 1700045027734
```

### 第二步：执行重跑命令

将参数填入后执行：

```bash
aliyun dataworks-public rerun-task-instances --ids <ids> --api-version 2024-05-18 --region cn-hangzhou
```

### 第三步：解析并展示结果

从返回的 JSON 中读取 `RequestId` 和 `SuccessInfo`，按以下格式输出：

```
实例重跑已触发

请求 ID:  <RequestId>

实例 ID          结果
<instanceId1>    成功
<instanceId2>    失败

提示：可使用 /get-instance-log <InstanceId> 查看节点运行日志。
```

`SuccessInfo` 中每个键为实例 ID，值的 `Success` 字段为 `true` 显示"成功"，`false` 显示"失败"。

若命令执行失败，直接展示错误信息，并根据错误码给出处理建议（见错误处理）。

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
| 400 | 参数错误 | 检查实例 ID 是否正确 |
| 403 | 权限不足 | 确认 AK 拥有 DataWorks 执行权限 |
| 404 | 资源不存在 | 确认实例 ID 是否存在 |
| 500 | 服务端错误 | 稍后重试，或联系管理员 |

## 使用示例

重跑单个实例：
```
/rerun-instance --ids 1700045027733
```

重跑多个实例：
```
/rerun-instance --ids 1700045027733 1700045027734
```
