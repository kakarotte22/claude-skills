---
name: get-instance-log
description: 获取 DataWorks 实例的运行日志。当用户需要查询节点实例日志信息时使用。
disable-model-invocation: true
---

## 功能

查询 DataWorks 生产环境或开发环境下指定实例的运行日志。

## 参数

- `$0` (必填): 实例ID (Instance ID)

## 执行步骤

1. **验证参数**: 确认用户提供了实例ID
2. **执行命令**: 调用阿里云 CLI 获取日志
3. **解析结果**: 提取关键信息并格式化展示

## 命令

```bash
aliyun dataworks-public get-instance-log \
  --instance-id "$0" \
  --project-env PROD \
  --api-version 2020-05-18 \
  --region cn-hangzhou
```

### 环境参数

- `--project-env PROD`: 生产环境（默认）
- `--project-env DEV`: 开发环境（如需要可替换）

## 输出解析

命令返回 JSON 格式结果，包含：
- `RequestId`: 请求追踪ID
- `HttpStatusCode`: HTTP状态码
- `Data`: 日志内容（字符串格式，包含 `\r\n` 换行符）

### 日志内容格式化

从 `Data` 字段中提取并完整输出以下信息：

**1. 基本信息**
- 任务状态：匹配 `Current task status:(.+)` 提取
- 节点名称：匹配 `SKYNET_NODENAME=(.+):` 提取
- logview URL：匹配 `logview url: (.+)` 提取

**2. Spark 参数（完整列出所有 `--conf` 行）**

日志中每个 `--conf` 后紧跟一行 `key=value`，需完整提取所有键值对并对齐展示，例如：
```
spark.driver.cores                                    = 8
spark.driver.memory                                   = 32g
spark.executor.instances                              = 50
spark.executor.cores                                  = 2
spark.executor.memory                                 = 8g
spark.input_table_name                                = du_risk_training_dev.xxx
spark.task_id                                         = 20260403_135240_374
spark.label_col                                       = is_bad
spark.app.main.file                                   = local:///workdir/get_feature_importance.py
...（其余所有 --conf 参数）
```

**重要**：`spark.app.main.file` 是主 Python 资源文件，**必须单独高亮展示**，提取文件名部分（去掉 `local:///workdir/` 前缀），格式如下：
```
主 Python 文件: get_feature_importance.py
```

**3. 提交状态**
- ODPS InstanceId：匹配 `InstanceId: (.+)` 提取
- Application 最终状态：最后一条 `Application report` 中的 `state: (.+)` 值

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
| 400 | 参数错误 | 检查实例ID是否正确 |
| 403 | 权限不足 | 检查AK是否有DataWorks权限 |
| 404 | 实例不存在 | 确认实例ID和项目环境 |
| 500 | 服务端错误 | 稍后重试 |

### 4. 实例ID无效
如果用户未提供实例ID或格式错误，提示：
> 请提供有效的实例ID，例如：`/get-instance-log 123456789`

## 使用示例

用户调用：
```
/get-instance-log 1700031357290
```

输出格式：
```
实例日志查询结果

实例ID:   1700031357290
环境:     PROD
节点名称:  特征重要性_手动_20260403_135240_374
任务状态:  RUNNING
主 Python 文件: get_feature_importance.py
logview: http://logview.odps.aliyun.com/logview/?h=...

Spark 参数：
────────────────────────────────
spark.driver.cores                                    = 8
spark.driver.memory                                   = 32g
spark.executor.instances                              = 50
spark.executor.cores                                  = 2
spark.executor.memory                                 = 8g
spark.hadoop.odps.cupid.resources                     = du_risk_training.my_env.tar.gz
spark.input_table_name                                = du_risk_training_dev.sell_fake_test_sample4skill
spark.task_id                                         = 20260403_135240_374
spark.label_col                                       = is_fake
spark.app.main.file                                   = local:///workdir/get_feature_importance.py
...（完整列出所有 --conf 参数）
────────────────────────────────

提交状态：
ODPS InstanceId: 20260403055554271gr2oioj2vxg
Application 状态: RUNNING
```
