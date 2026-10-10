---
name: dataworks-pyspark
description: |
  仅供手动调用。当用户提供一个 DataWorks 表名，要求对该表进行数据处理或计算任务时使用此 skill，
  包括但不限于：特征重要性计算、特征选择、模型训练、图计算、数据统计分析、ETL 处理等。
  该 skill 负责端到端完成：编写 PySpark 脚本 → 上传资源 → 创建任务 → 发布 → 运行 → 监控 → 结果分析。
  注意：此 skill 不自动触发，需用户明确调用（如 /dataworks-pyspark）。
---

# DataWorks PySpark 端到端任务执行

本 skill 将用户的计算需求转化为一个完整的 DataWorks PySpark 任务，从编写代码到获取结果，全程自动化。

## 固定参数

| 参数 | 值 |
|------|-----|
| DataWorks 项目 | `du_risk_training`，项目 ID `302182` |
| 容器 ID | `1700002700001` |
| Spark 版本 | `3.x` |
| 运行环境依赖 | `my_env.tar.gz` |
| Region | `cn-hangzhou` |

---

## 第一步：编写 PySpark 脚本

根据用户描述的需求（输入表名、计算目标、输出方式等），在**当前工作目录**下生成一个 `.py` 文件。

**脚本须知：**

**读写数据：**
- 从 MaxCompute/ODPS 读取表：**必须使用 Spark SQL 方式**，例如 `spark.sql("SELECT * FROM <项目名>.<表名>")`
- ❌ 禁止使用 `spark.read.format("odps")` —— 该方式在当前环境中找不到 odps 数据源驱动，会报 `DATA_SOURCE_NOT_FOUND` 错误
- 写回结果时使用 SQL 方式：先 `df.createOrReplaceTempView("tmp_xxx")`，再 `spark.sql("INSERT OVERWRITE TABLE <表名> PARTITION(...) SELECT ... FROM tmp_xxx")`
- ❌ 禁止使用 `df.write.format("odps")` —— 同上，数据源不可用

**分布式优先原则（核心约束）：**
- ✅ **优先使用分布式 Spark 算子**：`groupBy`、`agg`、`join`、`filter`、`withColumn`、`select`、`Window` 函数等
- ❌ **禁止使用 `toPandas()`**，除非数据量已经明确很小（如聚合后的统计结果，行数 < 10万）
- ❌ **禁止使用 `collect()`** 拉取大量数据到 Driver
- 特征工程、数据清洗、缺失值填充等操作全部用 Spark DataFrame API 完成，不依赖 Pandas

**优先使用 PySpark 原生库，而非单机版本：**

编写脚本前，**必须**先检查所用算法是否有 PySpark 分布式版本，优先级顺序：

| 场景 | ✅ 优先用（PySpark 分布式） | ❌ 避免用（单机版） |
|------|--------------------------|------------------|
| 机器学习模型训练 | `pyspark.ml`（GBTClassifier、RandomForestClassifier、LogisticRegression 等） | `xgboost`（单机）、`sklearn` |
| XGBoost | `xgboost.spark.SparkXGBClassifier` / `SparkXGBRegressor` | `xgboost.XGBClassifier`（单机） |
| 图计算 | `pyspark.ml.feature`、`graphframes.GraphFrame` | `networkx`、`igraph` |
| 特征工程 | `pyspark.ml.feature`（VectorAssembler、StandardScaler、StringIndexer 等） | `sklearn.preprocessing` |
| 统计计算 | `pyspark.sql.functions`、`pyspark.ml.stat` | `scipy.stats`、`numpy` |
| 聚类 | `pyspark.ml.clustering`（KMeans、BisectingKMeans） | `sklearn.cluster` |

**使用单机库的唯一允许场景：**
- 该算法确实没有 PySpark 分布式版本（需在代码注释中说明原因）
- 数据已通过分布式聚合/采样降至合理规模（< 50万行），并在代码中打印实际行数
- 仅用于最终结果的序列化/展示，不涉及大规模数据计算

**其他规范：**
- 在关键节点用 `print()` 输出进度和结果摘要，便于后续从日志中提取关键信息
- 脚本文件名建议格式：`<任务类型>_<表名简写>.py`，例如 `feature_importance_user_behavior.py`

**默认文件名规则：** `<task_type>_<table_shortname>_<YYYYMMDD>.py`

---

### 脚本复核与性能优化（第一步完成后必须执行）

脚本初稿写完后，**必须对脚本进行一轮性能复核**，从以下维度逐一检查并优化，重点关注大规模数据集（亿级行）场景下的运行效率。复核结束后将优化结果写入脚本，再进行后续步骤。

#### 1. 数据读取优化：列裁剪 & 分区裁剪

- **只读必要列**：用 `SELECT col1, col2, ...` 替代 `SELECT *`，减少序列化和传输开销。
- **下推过滤条件**：在 SQL 中直接加 `WHERE` 过滤，让 MaxCompute 在存储层完成裁剪，避免把不需要的数据拉到 Spark。
- **分区表优先指定分区**：如果源表有分区字段，在 SQL 中加分区过滤（`WHERE ds = '...'`）。

```python
# ❌ 差：读取全部列、全部分区
df = spark.sql("SELECT * FROM project.big_table")

# ✅ 好：只读需要的列，并下推过滤
df = spark.sql("""
    SELECT user_id, feature_a, feature_b, label
    FROM project.big_table
    WHERE ds = '20260526' AND is_valid = 1
""")
```

#### 2. 缓存策略：合理使用 cache / persist

- **多次复用的 DataFrame 才缓存**：只对被后续多个算子重复使用的 DataFrame 调用 `cache()` 或 `persist()`；一次性使用的不缓存。
- **用完及时释放**：调用 `df.unpersist()` 释放内存，避免 OOM。
- **大数据集选择合适存储级别**：内存不够时用 `MEMORY_AND_DISK` 而非默认 `MEMORY_ONLY`。

```python
from pyspark import StorageLevel

df_base.persist(StorageLevel.MEMORY_AND_DISK)  # 亿级数据建议用此级别

# ... 多处复用 df_base ...

df_base.unpersist()  # 用完释放
```

#### 3. Shuffle 优化

- **调整 shuffle partition 数**：默认 200 通常不适合大数据集，建议按 `数据量(GB) × 2 ~ 4` 估算，亿级数据可设 500～2000。
- **减少不必要的 shuffle**：避免对大表做不必要的 `distinct()`、`orderBy()`、`repartition()`。
- **合并小文件**：写出前用 `coalesce()` 减少输出文件数，避免产生大量小文件。

```python
# 在 SparkSession 创建后或算子前设置
spark.conf.set("spark.sql.shuffle.partitions", "1000")  # 按实际数据量调整

# 写出前合并小文件
df_result.coalesce(50).createOrReplaceTempView("tmp_result")
```

#### 4. Join 策略优化

- **小表 Join 大表时强制 Broadcast**：小表（< 200MB）用 `broadcast()` hint，避免 shuffle join。
- **大表 Join 大表**：确保两张表的 Join Key 分布均匀，避免数据倾斜。

```python
from pyspark.sql.functions import broadcast

# 小表 broadcast join
df_result = df_large.join(broadcast(df_small), on="key", how="left")
```

#### 5. 数据倾斜处理

如果 Join Key 或 GroupBy Key 分布严重不均（某些 Key 占比 > 10%），需要处理倾斜：

- **Salting 方案**：对倾斜 Key 加随机后缀打散，Join 后再聚合。
- **倾斜检测**：先用 `df.groupBy("key").count().orderBy("count", ascending=False).show(20)` 查看 Key 分布，再决定是否需要 salting。

```python
import pyspark.sql.functions as F

# 倾斜检测
df.groupBy("user_id").count().orderBy("count", ascending=False).show(20)

# Salting（倾斜严重时使用）
SALT_NUM = 20
df_salted = df_large.withColumn("salt", (F.rand() * SALT_NUM).cast("int")) \
                    .withColumn("salted_key", F.concat(F.col("key"), F.lit("_"), F.col("salt")))
df_small_expanded = df_small.withColumn("salt", F.explode(F.array([F.lit(i) for i in range(SALT_NUM)]))) \
                             .withColumn("salted_key", F.concat(F.col("key"), F.lit("_"), F.col("salt")))
df_joined = df_salted.join(df_small_expanded, on="salted_key", how="left")
```

#### 6. UDF 优化：优先使用 pandas_udf 替代 Python UDF

- **普通 Python UDF 逐行处理**，序列化开销极大，亿级数据下性能极差。
- **pandas_udf 批量处理**，基于 Arrow 序列化，性能比普通 UDF 快 10～100 倍。
- **最优先**：用原生 Spark SQL 函数（`F.when`、`F.regexp_extract` 等）替代任何 UDF。

```python
# ❌ 差：普通 Python UDF，逐行调用
@udf("double")
def normalize(x):
    return x / 100.0

# ✅ 好：pandas_udf，批量向量化处理
from pyspark.sql.functions import pandas_udf
import pandas as pd

@pandas_udf("double")
def normalize_vec(x: pd.Series) -> pd.Series:
    return x / 100.0

# ✅ 最优：直接用 Spark SQL 原生函数
df = df.withColumn("normalized", F.col("value") / 100.0)
```

#### 7. 驱动端瓶颈检查

扫描脚本中所有 `collect()`、`toPandas()`、`show()` 的使用位置：

- **`collect()`**：只允许用于行数极少的聚合结果（< 10万行），且必须在代码注释中注明预期行数。
- **`toPandas()`**：同上，必须先 `count()` 确认行数并打印，再调用。
- **`show()`**：生产脚本中只用于调试，最终脚本可保留少量用于打印摘要，行数限制在 50 以内。

#### 8. Spark SQL 关键配置复核

根据任务类型，检查以下配置是否已在脚本或 Spark 配置中合理设置：

| 配置项 | 推荐值（大数据场景） | 说明 |
|--------|-------------------|------|
| `spark.sql.shuffle.partitions` | 500～2000 | 按数据量调整，默认 200 太小 |
| `spark.sql.adaptive.enabled` | `true` | 开启 AQE，自动处理倾斜和动态分区 |
| `spark.sql.adaptive.coalescePartitions.enabled` | `true` | AQE 自动合并小 partition |
| `spark.sql.adaptive.skewJoin.enabled` | `true` | AQE 自动处理 Join 倾斜 |
| `spark.sql.autoBroadcastJoinThreshold` | `209715200`（200MB） | 适当放大 broadcast 阈值 |

在脚本 `SparkSession` 创建后统一设置：

```python
spark.conf.set("spark.sql.shuffle.partitions", "1000")
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", str(200 * 1024 * 1024))
```

#### 复核完成后的输出格式

复核并修改脚本后，向用户简要说明做了哪些优化：

```
🔍 脚本性能复核完成，已进行以下优化：
  ✅ 列裁剪：SELECT * → 指定必要列，减少 XX 列
  ✅ 缓存策略：对 df_processed 添加 persist(MEMORY_AND_DISK)，用完 unpersist
  ✅ Shuffle 分区：spark.sql.shuffle.partitions 设为 1000
  ✅ 开启 AQE：自动处理倾斜和动态分区合并
  ✅ 广播 Join：df_label（小表）改用 broadcast() hint
  ⚠️  发现 toPandas() 调用：确认聚合后行数 < 10万，已添加 count() 校验
```

---

## 第二步：确认文件名

生成脚本后，展示文件名给用户，询问是否需要修改：

```
📄 已生成脚本文件：<filename>.py
是否需要修改文件名？如不需要，请直接确认继续。
```

若用户指定新文件名，使用 Edit/Bash 工具将文件重命名为用户指定的名称，然后继续。

---

## 第三步：上传 Python 文件到 DataWorks 资源

调用 `dataworks-upload` skill 将 py 文件上传为资源：

- 项目 ID：`302182`
- 上传成功后记录**资源文件名**（即上传后的资源名称，后续步骤使用）

---

## 第四步：创建 PySpark 任务节点并发布，获取节点的 任务ID

调用 `alibabacloud-dataworks-datastudio-develop` skill，告知以下信息，让其负责创建节点并发布到生产环境：

- **任务类型**：ODPS_SPARK（PySpark）
- **项目**：du_risk_training，项目 ID 302182
- **场景**：手动业务流程（DATAWORKS_MANUAL_WORKFLOW）
- **容器 ID**：7275101358233842533
- **主 Python 资源**：第三步上传的资源文件名
- **Spark 版本**：3.x
- **Spark 配置**：以下默认配置（用户可修改、新增或删除）
- **资源组**：du_risk_serverless_scheduler

**在调用前**，先将下方默认配置展示给用户确认，用户可修改任意配置项：

```
📋 即将使用以下 Spark 配置（如需修改请告知）：
  spark.driver.cores=8
  spark.driver.memory=32g
  spark.executor.instances=20
  spark.executor.cores=1
  spark.executor.memory=32g
  spark.driver.maxResultSize=32g
  spark.hadoop.odps.cupid.resources=du_risk_training.my_env.tar.gz
  spark.hadoop.fs.AbstractFileSystem.oss.impl=com.aliyun.emr.fs.oss.OSS
  spark.hadoop.fs.oss.impl=com.aliyun.emr.fs.oss.JindoOssFileSystem
  spark.hadoop.odps.spark.version=spark-3.5.2-odps0.34.0
  spark.executorEnv.PYTHONPATH=./du_risk_training.my_env.tar.gz/packages
  spark.yarn.appMasterEnv.PYTHONPATH=./du_risk_training.my_env.tar.gz/packages
  spark.hadoop.odps.spark.alinux3.enabled=true
  spark.hadoop.odps.kube.mode=true
  spark.dynamicAllocation.enabled=false
  spark.hadoop.odps.cupid.trusted.services.access.list=dw-risk-data-model.oss-cn-hangzhou-internal.aliyuncs.com
是否确认？如需修改请直接说明。
```

用户确认后，将最终配置一并传给 `alibabacloud-dataworks-datastudio-develop` skill，由其完成节点创建和发布，并获取**任务 ID**。

---

## 第五步：运行任务，获取实例 ID

使用 `run-manual-dag-nodes`（API 版本 2020-05-18）触发任务运行，该方式会在运维中心的手动业务流程下正常产生实例，可正常查询。

**业务日期**：取昨日日期，格式 `YYYY-MM-DD 00:00:00`，例如 `2026-05-25 00:00:00`。

```bash
# 第一步：触发运行，获取 DagId
aliyun dataworks-public run-manual-dag-nodes \
  --project-env PROD \
  --project-name "du_risk_training" \
  --flow-name "<手动业务流程名称>" \
  --biz-date "<昨日日期，格式：2026-05-25 00:00:00>" \
  --include-node-ids <任务ID> \
  --api-version 2020-05-18 \
  --region cn-hangzhou
```

> **flow-name 说明**：即第四步中节点所在的手动业务流程名称。可通过 `get-node` 返回的 `Script.Path` 字段获取，格式为 `<flow-name>/<node-name>`，取第一段即为 flow-name。

从返回结果中提取 `DagId`，再查询本次产生的实例 ID：

```bash
# 第二步：查询实例 ID
aliyun dataworks-public list-manual-dag-instances \
  --project-env PROD \
  --project-name "du_risk_training" \
  --dag-id <DagId> \
  --api-version 2020-05-18 \
  --region cn-hangzhou
```

从返回的 `Instances` 列表中提取 `InstanceId`，展示给用户：

```
🚀 任务已提交运行
DagId：<DagId>
实例 ID：<InstanceId>
节点名称：<NodeName>
当前状态：<Status>
```

---

## 第六步：轮询实例运行状态

使用 `/loop 5m` 每隔 5 分钟查询一次实例运行状态，使用第五步从 `list-manual-dag-instances` 获取的 `InstanceId`：

```bash
export ALIBABA_CLOUD_CONNECT_TIMEOUT=10000
export ALIBABA_CLOUD_READ_TIMEOUT=30000
aliyun dataworks-public get-task-instance \
  --region cn-hangzhou \
  --id <InstanceId> \
  --user-agent AlibabaCloud-Agent-Skills/alibabacloud-dataworks-data-ops
```

获取任务的运行状态，根据状态进行后续处理：
**状态映射：**

| Status 值 | 含义 | 处理 |
|-----------|------|------|
| `NotRun` / `Waiting` / `Running` / `WaitTime` / `WaitResource` | 运行中 | 继续等待，下次轮询 |
| `Success` | 运行成功 | 停止轮询，进入第七步（情况二）|
| `Failure` | 运行失败 | 停止轮询，进入第七步（情况一）|

每次轮询输出：
```
⏳ [<当前时间>] 实例 <InstanceId> 状态：<Status>，下次检查约 5 分钟后...
```

---

## 第七步：获取结果

从实例运行日志中提取 LogView URL，再调用 `logview-stdout` skill 提取 Driver StdOut 输出。

### 情况一：任务运行失败

调用 `logview-stdout` skill 获取完整输出后：

1. 分析错误原因，常见类型：
   - **OOM**（内存不足）：调整 `spark.driver.memory` / `spark.executor.memory`，回到**第四步**
   - **代码逻辑错误**（如 KeyError、AttributeError）：修改 PySpark 脚本，回到**第一步**
   - **数据源不存在**（`DATA_SOURCE_NOT_FOUND: odps`）：脚本使用了 `spark.read.format("odps")`，改为 `spark.sql("SELECT * FROM ...")` 方式，回到**第一步**
   - **单机库 OOM / 性能问题**（如 xgboost/sklearn 在 Driver 上处理大数据导致崩溃）：改用对应的 PySpark 分布式版本（如 `SparkXGBClassifier`、`pyspark.ml`），回到**第一步**
   - **表不存在或权限问题**：提示用户检查表名和权限，修正后回到**第一步**
   - **资源超时**：增加 executor 数量或调整并发配置，回到**第四步**

2. 向用户说明分析结论，并明确告知将回到哪一步重试：

```
❌ 任务运行失败
错误类型：<分析结论>
错误摘要：<关键错误信息>

处理方案：<修改方向>
→ 将回到第X步重新执行...
```

### 情况二：任务运行成功

调用 `logview-stdout` skill 获取完整输出后，提取关键信息展示：

```
✅ 任务运行成功！
实例 ID：<InstanceId>

📊 关键输出：
<从 StdOut 中提取的业务相关信息，如：
  - 处理记录数
  - 输出表/分区信息
  - 核心计算结果（特征重要性 Top N、模型指标等）
  - 运行耗时>
```

