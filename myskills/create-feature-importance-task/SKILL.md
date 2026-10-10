---
name: create-feature-importance-task
description: 在阿里云 DataWorks 中创建特征重要性（Feature Importance）计算任务（ODPS Spark 节点）。当用户需要对 ODPS 表计算特征重要性、提交特征重要性分析任务到 DataWorks 手动工作流、或需要创建风控特征筛选任务时，主动使用此技能。输入参数为输入表名、标签列名（label column），以及可选的排除列列表。
disable-model-invocation: true
---

## 功能

在阿里云 DataWorks 手动工作流中创建特征重要性计算节点（ODPS Spark 任务），自动生成带唯一任务ID的节点 spec 并提交到指定项目容器。

## 参数

- $ARGUMENTS[0] (必填): 输入表名，格式为 `project.table`，例如 `du_risk_training.test_table`
- $ARGUMENTS[1] (必填): 标签列名，例如 `is_bad`
- $ARGUMENTS[2] (选填): 排除列，逗号分隔，例如 `uid,req_id`。不传则使用默认值 `request_id,user_id,uid,userid`

缺少必填参数时，提示：
```
❌ 缺少必填参数，用法：
/create-feature-importance-task <输入表名> <标签列名> [排除列]
示例：/create-feature-importance-task du_risk_training.test_table is_bad
示例（指定排除列）：/create-feature-importance-task du_risk_training.test_table is_bad uid,req_id
```

## 执行步骤

1. **验证参数**: 确认用户提供了输入表名和标签列名
2. **执行命令**: 用 Python subprocess 一次性完成 spec 生成和节点提交
3. **解析结果**: 提取关键信息并格式化展示

## 执行命令

**重要**：spec 的 `content` 字段含 `\n` 换行符，shell 变量拼接会破坏 JSON 结构导致 400 错误。必须用 Python subprocess 传参，绕过 shell 转义。

以单个 `python3 -c "..."` Bash 命令执行：

```python
import subprocess, json

# 构造命令，--exclude_cols 为可选参数
cmd = [
    'python', 'scripts/get_spec.py',
    '--input_table_name', '$ARGUMENTS[0]',
    '--label_col', '$ARGUMENTS[1]'
]
# 若用户提供了第三个参数（排除列），则追加；否则脚本使用默认值
exclude_cols = '$ARGUMENTS[2]'
if exclude_cols:
    cmd.extend(['--exclude_cols', exclude_cols])

# 第一步：生成 spec（只调用一次，避免重复调用产生不同时间戳）
result = subprocess.check_output(
    cmd,
    cwd='/Users/admin/.claude/skills/create-feature-importance-task'
)
spec = json.loads(result)

# 从同一份 spec 对象中提取节点名称，不得再次调用 get_spec.py
node_name = spec['spec']['nodes'][0]['name']
spec_str = json.dumps(spec, ensure_ascii=False)

# 第二步：提交节点
proc = subprocess.run([
    'aliyun', 'dataworks-public', 'create-node',
    '--project-id', '302182',
    '--container-id', '7571626032124099758',
    '--scene', 'DATAWORKS_MANUAL_WORKFLOW',
    '--spec', spec_str,
    '--api-version', '2024-05-18',
    '--region', 'cn-hangzhou'
], capture_output=True, text=True)

print('NODE_NAME:', node_name)
print('STDOUT:', proc.stdout)
print('STDERR:', proc.stderr)
print('RC:', proc.returncode)
```

**返回样例**：
```
NODE_NAME: 特征重要性_手动_20260401_154605_366
STDOUT: {
  "RequestId": "4A91805D-7AAE-5BE4-86DC-5EBC7A3A79D7",
  "Id": "8593609032826935290"
}
RC: 0
```
- `NODE_NAME`：从 spec 中提取的节点名称（与提交内容一致）
- `Id`：节点唯一标识符
- `RequestId`：请求追踪ID

## 输出格式

从脚本输出的 `NODE_NAME` 行提取节点名称，并提取后缀，该后缀与结果表名后缀相同，从 CLI 返回（STDOUT）中提取 Id 和 RequestId，格式化展示：

```
✅ 特征重要性任务创建成功
节点名称：特征重要性_手动_20260401_154605_366
节点 ID：8593609032826935290
请求 ID：4A91805D-7AAE-5BE4-86DC-5EBC7A3A79D7
输入表名： du_risk_training.test_table
标签列名：is_bad
排除列：request_id,user_id,uid,userid（默认）
结果表名：du_risk_training.test_table_feature_importance_20260401_154605_366
```

若用户显式指定了排除列，则"排除列"一行展示用户传入的值（不加"默认"备注）。

## 错误处理

### 1. 未安装 aliyun CLI
```bash
brew install aliyun-cli
```

### 2. 未配置 AccessKey
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
| 400 | 参数错误/JSON格式错误 | 确认使用 Python subprocess 方式执行，勿用 shell 变量拼接 |
| 403 | 权限不足 | 检查 AK 是否具有 DataWorks 节点创建权限 |
| 404 | 资源不存在 | 确认 project-id (302182) 和 container-id 是否正确 |
| 500 | 服务端错误 | 稍后重试 |
