---
name: dataworks-sample-extend
description: |
  仅供手动调用。执行样本拓展任务：在 du_risk_training 项目下创建 PySpark 节点、发布并运行，轮询至任务完成后返回结果。
  接收两个必填参数：seed_table（种子表名）和 pt_start（订单开始日期，格式 20260401）。
  注意：此 skill 不自动触发，需用户明确调用（如 /dataworks-sample-extend）。
disable-model-invocation: true
---

# 样本拓展端到端任务

## 固定参数

| 参数 | 值 |
|------|-----|
| DataWorks 项目 | `du_risk_training`，项目 ID `302182` |
| 手动业务流程名称 | `样本拓展` |
| 容器 ID | `7759492840531556877` |
| 主 Python 资源 | `yingxiao_black_extract_spark.py` |
| Spark 版本 | `3.x` |
| Region | `cn-hangzhou` |

---

## 第一步：核验参数

从用户输入中提取以下两个必填参数：

- **seed_table**：样本拓展种子表名
- **pt_start**：订单开始日期，格式为 8 位纯数字，如 `20260401`

**缺失检查：** 若任一参数未提供，立即停止并提示：

```
❌ 缺少必填参数，请补充后重新调用：
  - seed_table：样本拓展种子表名（例如：du_risk_training.my_seed_table）
  - pt_start：订单开始日期，格式为 8 位数字（例如：20260401）

用法：/dataworks-sample-extend --seed_table <表名> --pt_start <日期>
示例：/dataworks-sample-extend --seed_table du_risk_training.seed_20260401 --pt_start 20260401
```

**合法性检查：** 若参数提供但不合法，立即停止并提示：

- `pt_start` 必须为 8 位纯数字，且能构成合法日期（`YYYYMMDD`）。格式不合法时提示：
  ```
  ❌ 参数不合法：pt_start 必须为 8 位日期数字，格式如 20260401，当前值为 "<用户输入值>"
  ```

参数通过校验后，展示确认信息继续执行：

```
✅ 参数校验通过
  seed_table：<seed_table>
  pt_start：<pt_start>
```

---

## 第二步：生成毫秒时间戳作为 task_id

执行以下命令生成毫秒级时间戳，作为本次任务的唯一 ID（`task_id`）：

```bash
python3 -c "import time; print(int(time.time() * 1000))"
```

将输出的整数值记为 `<task_id>`，例如 `1779947167588`。

展示给用户：
```
🔑 任务 ID（task_id）：<task_id>
```

---

## 第三步：创建 PySpark 任务节点

将代码写入临时文件再执行，避免 shell 转义问题。

**3a. 用 Write 工具将以下代码写入 `/tmp/create_sample_extend_node.py`**，替换 `TASK_ID`、`SEED_TABLE`、`PT_START` 为实际值：

```python
import subprocess, json

TASK_ID    = "<task_id>"        # 第二步生成的毫秒时间戳（字符串形式）
SEED_TABLE = "<seed_table>"     # 用户输入的种子表名
PT_START   = "<pt_start>"       # 用户输入的订单开始日期

NODE_NAME    = f"sample_extend_{TASK_ID}"
MAIN_PY      = "yingxiao_black_extract_spark.py"
CONTAINER_ID = "7759492840531556877"

SPARK_CONFIGS = [
    "spark.driver.cores=8",
    "spark.driver.memory=32g",
    "spark.executor.instances=20",
    "spark.executor.cores=1",
    "spark.executor.memory=32g",
    "spark.driver.maxResultSize=32g",
    "spark.hadoop.odps.cupid.resources=du_risk_training.my_env.tar.gz",
    "spark.hadoop.fs.AbstractFileSystem.oss.impl=com.aliyun.emr.fs.oss.OSS",
    "spark.hadoop.fs.oss.impl=com.aliyun.emr.fs.oss.JindoOssFileSystem",
    "spark.hadoop.odps.spark.version=spark-3.5.2-odps0.34.0",
    "spark.executorEnv.PYTHONPATH=./du_risk_training.my_env.tar.gz/packages",
    "spark.yarn.appMasterEnv.PYTHONPATH=./du_risk_training.my_env.tar.gz/packages",
    "spark.hadoop.odps.spark.alinux3.enabled=true",
    "spark.dynamicAllocation.enabled=false",
    "spark.hadoop.odps.cupid.trusted.services.access.list=dw-risk-data-model.oss-cn-hangzhou-internal.aliyuncs.com",
    f"spark.seed_table={SEED_TABLE}",
    f"spark.pt_start={PT_START}",
    f"spark.task_id={TASK_ID}",
    "spark.p1_threshold=0.5",
    "spark.p2_threshold=0.45",
]

spark_config = {
    "version": "3.x",
    "language": "python",
    "configs": SPARK_CONFIGS,
    "mainPy": MAIN_PY,
    "assistPys": [],
}
resource_ref = f'##@resource_reference{{"{MAIN_PY}"}}'
content = resource_ref + "\n" + json.dumps(spark_config, ensure_ascii=False, separators=(",", ":"))

spec = {
    "version": "1.1.0",
    "kind": "Node",
    "spec": {
        "nodes": [
            {
                "id": "",
                "recurrence": "Normal",
                "timeout": 0,
                "instanceMode": "T+1",
                "rerunMode": "Allowed",
                "rerunTimes": 3,
                "rerunInterval": 180000,
                "datasource": {"name": "du_risk_training", "type": "odps"},
                "script": {
                    "language": "python",
                    "path": NODE_NAME,
                    "runtime": {"command": "ODPS_SPARK", "commandTypeId": 225},
                    "content": content,
                },
                "trigger": {"type": "Manual", "timezone": "Asia/Shanghai"},
                "runtimeResource": {
                    "resourceGroup": "Serverless_res_group_235454102432001_733371449043168",
                    "resourceGroupName": "du_risk_serverless_scheduler",
                },
                "name": NODE_NAME,
                "inputs": {"nodeOutputs": []},
            }
        ]
    },
}

proc = subprocess.run([
    'aliyun', 'dataworks-public', 'create-node',
    '--project-id', '302182',
    '--container-id', CONTAINER_ID,
    '--scene', 'DATAWORKS_MANUAL_WORKFLOW',
    '--spec', json.dumps(spec, ensure_ascii=False),
    '--api-version', '2024-05-18',
    '--region', 'cn-hangzhou'
], capture_output=True, text=True)

print('NODE_NAME:', NODE_NAME)
print('STDOUT:', proc.stdout)
print('STDERR:', proc.stderr)
print('RC:', proc.returncode)
```

**3b. 用 Bash 工具执行：**

```bash
python3 /tmp/create_sample_extend_node.py
```

从输出中提取：
- `NODE_NAME`：节点名称，格式 `sample_extend_<task_id>`
- STDOUT JSON 中的 `Id`：节点 ID（字符串，如 `"8855376266758523685"`）

展示给用户：
```
✅ 第三步完成：PySpark 节点已创建
节点名称：<NODE_NAME>
节点 ID：<Id>
```

若命令失败（RC != 0），立即停止并展示错误信息。

---

## 第四步：发布节点到生产环境

调用 `publish-node` skill，传入参数：

```
/publish-node --object-ids <节点ID>
```

发布成功后，从返回结果中提取 **TaskId**（整数，如 `1034606593`），记为 `<task_node_id>`。

展示给用户：
```
✅ 第四步完成：节点已发布到生产环境
节点 TaskId：<task_node_id>
```

---

## 第五步：触发任务运行

使用 `run-manual-dag-nodes`（API 版本 2020-05-18）触发任务运行。

**业务日期**：取昨日日期，格式 `YYYY-MM-DD 00:00:00`，例如 `2026-05-27 00:00:00`。

```bash
aliyun dataworks-public run-manual-dag-nodes \
  --project-env PROD \
  --project-name "du_risk_training" \
  --flow-name "样本拓展" \
  --biz-date "<昨日日期，格式：YYYY-MM-DD 00:00:00>" \
  --include-node-ids <task_node_id> \
  --api-version 2020-05-18 \
  --region cn-hangzhou
```

从返回结果中提取 `DagId`，再查询实例 ID：

```bash
aliyun dataworks-public list-manual-dag-instances \
  --project-env PROD \
  --project-name "du_risk_training" \
  --dag-id <DagId> \
  --api-version 2020-05-18 \
  --region cn-hangzhou
```

从返回的 `Instances` 列表中提取 `InstanceId`，记为 `<instance_id>`。

展示给用户：
```
✅ 第五步完成：任务已提交运行
DagId：<DagId>
实例 ID：<instance_id>
节点名称：<NODE_NAME>
当前状态：<Status>
```

---

## 第六步：轮询实例运行状态

使用 `/loop 5m` 每隔 5 分钟查询一次实例运行状态，查询命令如下：

```bash
export ALIBABA_CLOUD_CONNECT_TIMEOUT=10000
export ALIBABA_CLOUD_READ_TIMEOUT=30000
aliyun dataworks-public get-task-instance \
  --region cn-hangzhou \
  --id <instance_id> \
  --user-agent AlibabaCloud-Agent-Skills/alibabacloud-dataworks-data-ops
```

**状态映射：**

| Status 值 | 含义 | 处理 |
|-----------|------|------|
| `NotRun` / `Waiting` / `Running` / `WaitTime` / `WaitResource` | 运行中 | 继续等待，下次轮询 |
| `Success` | 运行成功 | 停止轮询，进入第七步（成功分支）|
| `Failure` | 运行失败 | 停止轮询，进入第七步（失败分支）|

每次轮询输出：
```
⏳ [<当前时间>] 实例 <instance_id> 状态：<Status>，下次检查约 5 分钟后...
```

---

## 第七步：返回运行结果

### 情况一：任务运行失败

```
❌ 样本拓展任务运行失败

任务信息：
  task_id：<task_id>
  节点名称：<NODE_NAME>
  实例 ID：<instance_id>
  seed_table：<seed_table>
  pt_start：<pt_start>

请检查日志排查失败原因，或联系相关人员处理。
```

### 情况二：任务运行成功

```
✅ 样本拓展任务运行成功！

任务信息：
  task_id：<task_id>
  节点名称：<NODE_NAME>
  实例 ID：<instance_id>
  seed_table：<seed_table>
  pt_start：<pt_start>

📦 结果表：
  merchant_rank.tmp_yingxiao_black_final_result_<task_id>
```

---

## 错误处理

### aliyun CLI 未安装
```bash
brew install aliyun-cli
```

### AccessKey 未配置
```bash
aliyun configure set \
  --profile AkProfile \
  --mode AK \
  --access-key-id <yourAccessKeyID> \
  --access-key-secret <yourAccessKeySecret> \
  --region "cn-hangzhou"
```

### 常见错误码

| HttpStatusCode | 含义 | 处理建议 |
|----------------|------|---------|
| 400 | 参数错误 / JSON 格式错误 | 确认使用 Python subprocess 方式，勿用 shell 变量拼接 |
| 403 | 权限不足 | 检查 AK 是否具有 DataWorks 节点创建权限 |
| 404 | 资源不存在 | 确认 project-id (302182) 和 container-id 是否正确 |
| 500 | 服务端错误 | 稍后重试 |
