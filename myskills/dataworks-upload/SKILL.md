---
name: dataworks-upload
description: 上传本地文件到阿里云 DataWorks 资源。当用户说"上传资源到DataWorks"、"上传xx文件到xx项目"、"把这个文件上传到dataworks"、"dataworks上传"时触发此技能。即使用户只提到"上传资源"而没有明确说dataworks，只要上下文涉及阿里云或DataWorks项目，也应触发此技能。
---

# DataWorks 资源上传技能

## 依赖

- Python 包：`alibabacloud-dataworks-public20200518`（运行前确认已安装）
- 鉴权文件：`~/.aliyun/config.json`，需包含 `AkProfile`（access_key_id / access_key_secret / region_id）

## 资源类型对照表

| file_type | 类型 | 内容编码 | 触发扩展名 |
|-----------|------|---------|-----------|
| 12 | Python 资源 | 原始文本 | `.py` |
| 13 | JAR 资源 | Base64 二进制 | `.jar` |
| 15 | 普通文件资源 | 原始文本 | 其他 |

> `file_type` 由脚本根据扩展名自动推断，无需手动指定。

## 执行步骤

1. **收集必要参数**（从用户消息提取，缺少的逐一询问）：
   - `files`：本地文件路径，支持多个（批量上传）
   - `--name`：资源名（仅单文件时有效，默认取文件名）
   - `--project-id`：DataWorks 项目 ID，**未指定时默认为 302182**
   - `--folder`：资源目录，默认 `/`
   - `--profile`：AK profile 名称，默认 `AkProfile`
   - `--yes`：复用覆盖模式（2026-09-20 人工约定）——固定资源名复用时使用，
     发现同名资源直接覆盖更新、不交互询问（探索任务编排场景必备，避免卡在交互确认）

2. **调用上传脚本**（技能目录在上下文顶部 `Base directory` 字段中）：

```bash
# 单文件（资源名默认取文件名）
python <skill_dir>/scripts/upload.py "<file_path>"

# 单文件指定资源名
python <skill_dir>/scripts/upload.py "<file_path>" --name "<resource_name>"

# 固定资源名复用覆盖（--yes：同名直接更新，不交互）
python <skill_dir>/scripts/upload.py "<file_path>" --name "<fixed_name>" --yes

# 指定项目 ID
python <skill_dir>/scripts/upload.py "<file_path>" --project-id 302182

# 批量上传多个文件
python <skill_dir>/scripts/upload.py file1.py file2.py file3.jar
```

脚本输出示例：
```
      文件类型自动推断：.py -> file_type=12
[1/4] 上传中（或更新中）... FileId=xxx
[2/4] 提交中 ... 提交完成
[3/4] 发布中 ... 发布成功
[4/4] 校验中 ... 校验通过 ✓
```

3. **返回结果**：校验通过后告知用户 `FileId`；批量上传结束后展示汇总结果。

## 脚本行为说明

- **文件存在性检查**：文件不存在时立即提示并退出，不发起任何 API 请求
- **自动推断类型**：根据扩展名推断 `file_type`，无需用户指定
- **查重确认**：发现同名同类型资源时，**必须等待用户输入 `yes`** 才执行覆盖，其他输入直接终止
- **一次读取**：文件内容只读取一次，上传和校验复用同一份数据
- **异步等待**：`SubmitFile` 轮询使用限流保护；`DeployFile` 遇到 `pipe line is not ready` 自动重试
- **限流重试**：所有 API 调用遇到 `Throttling.User` 自动等待 6s 重试，最多 3 次
- **批量上传**：多文件共用同一客户端，单个文件失败不影响其余文件，结束后打印汇总

## 常见错误排查

| 错误码 / 关键字 | 原因 | 解决方法 |
|---------------|------|---------|
| `文件不存在` | file_path 路径有误 | 确认文件路径 |
| `Throttling.User` | 请求频率过高 | 脚本自动重试，无需手动干预 |
| `pipe line is not ready` | pipeline 未就绪 | 脚本自动重试，无需手动干预 |
| 资源内容乱码 | 文本文件被 Base64 编码 | 脚本已按类型自动处理 |
| `Profile not found` | config.json 中无对应 profile | 检查 `~/.aliyun/config.json` 的 profile 名称 |
| `校验失败` | 远端内容与本地不一致 | 检查网络或重新执行上传 |
