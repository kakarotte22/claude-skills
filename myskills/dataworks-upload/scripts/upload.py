"""
阿里云 DataWorks 资源文件上传并发布脚本
从 ~/.aliyun/config.json 读取 AkProfile 鉴权信息

流程：
  查询同名资源（ListFiles）
  → 存在：用户确认后更新（UpdateFile）/ 不存在：创建（CreateResourceFile）
  → 提交（SubmitFile）→ 轮询直到 status==1
  → 发布（DeployFile，自动重试 pipeline not ready）
  → 校验内容（GetFile）

用法（单文件）：
    python upload.py <file_path> [--name <resource_name>] [--project-id <id>]
                     [--file-type <type>] [--folder <path>] [--profile <name>]

用法（批量）：
    python upload.py file1.py file2.py file3.jar [--project-id <id>] [--file-type <type>]

file_type 对应关系（通过 ListFileType 接口确认）：
    12 = Python 资源文件
    13 = JAR 资源文件（二进制，自动 Base64 编码；远端校验 type 字段）
    15 = 普通文件资源
"""

import json
import base64
import sys
import time
import argparse
from pathlib import Path

from alibabacloud_dataworks_public20200518 import models as dw_models


# ── 常量 ──────────────────────────────────────────────────────────────────────

DEFAULT_PROJECT_ID = 302182
BINARY_TYPES       = {13}   # 二进制类型需要 Base64 编码
POLL_INTERVAL      = 3      # 轮询间隔（秒）
POLL_TIMEOUT       = 120    # 最长等待时间（秒）
THROTTLE_WAIT      = 6      # 限流后等待时间（秒）
THROTTLE_RETRY     = 3      # 限流最大重试次数

DEPLOY_DONE   = 1
DEPLOY_FAILED = 2

# 扩展名 → file_type 自动推断表
EXT_TO_FILE_TYPE = {
    ".py":  12,
    ".jar": 13,
}
DEFAULT_FILE_TYPE = 15  # 其他扩展名一律为普通文件

# file_type → 可读名称
FILE_TYPE_NAMES = {12: "Python", 13: "JAR", 15: "File"}


# ── 自定义异常 ────────────────────────────────────────────────────────────────

class UserCancelledError(Exception):
    """用户主动取消操作。"""


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def infer_file_type(file_path: str) -> int:
    ext = Path(file_path).suffix.lower()
    return EXT_TO_FILE_TYPE.get(ext, DEFAULT_FILE_TYPE)


def load_ak_profile(profile_name: str = "AkProfile") -> dict:
    config_path = Path.home() / ".aliyun" / "config.json"
    with open(config_path, "r") as f:
        config = json.load(f)
    for profile in config.get("profiles", []):
        if profile.get("name") == profile_name:
            return {
                "access_key_id": profile["access_key_id"],
                "access_key_secret": profile["access_key_secret"],
                "region_id": profile.get("region_id", "cn-hangzhou"),
            }
    raise ValueError(f"Profile '{profile_name}' not found in {config_path}")


def load_ak_from_env_file(env_file: str) -> dict:
    """从项目 .env 文件读取 AK（2026-09-20 约定：AK 统一从 .env 获取与更新）。

    .env 需含 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET，
    可选 ALIBABA_CLOUD_REGION_ID（默认 cn-hangzhou）。
    """
    env_path = Path(env_file).expanduser()
    if not env_path.exists():
        raise FileNotFoundError(f"env 文件不存在：{env_path}")
    env = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    ak_id = env.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
    ak_secret = env.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    if not ak_id or not ak_secret:
        raise ValueError(f"{env_path} 缺少 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    return {
        "access_key_id": ak_id,
        "access_key_secret": ak_secret,
        "region_id": env.get("ALIBABA_CLOUD_REGION_ID", "cn-hangzhou"),
    }


def resolve_ak(profile_name: str, env_file: str = None) -> dict:
    """AK 来源优先级：--env-file（.env 统一来源）> aliyun config profile。"""
    if env_file:
        return load_ak_from_env_file(env_file)
    return load_ak_profile(profile_name)


def create_client(ak: dict):
    from alibabacloud_dataworks_public20200518.client import Client
    from alibabacloud_tea_openapi import models as open_api_models

    config = open_api_models.Config(
        access_key_id=ak["access_key_id"],
        access_key_secret=ak["access_key_secret"],
        endpoint=f"dataworks.{ak['region_id']}.aliyuncs.com",
    )
    return Client(config)


def with_throttle_retry(fn, *args, **kwargs):
    """遇到限流（Throttling）时自动等待重试，最多 THROTTLE_RETRY 次。"""
    for attempt in range(THROTTLE_RETRY + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if "Throttling" in str(e) and attempt < THROTTLE_RETRY:
                print(f"      请求限流，{THROTTLE_WAIT}s 后重试（第 {attempt + 1}/{THROTTLE_RETRY} 次）...")
                time.sleep(THROTTLE_WAIT)
            else:
                raise


def read_file_content(file_path: str, file_type: int) -> str:
    if file_type in BINARY_TYPES:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()


# ── 核心操作 ──────────────────────────────────────────────────────────────────

def find_existing_file(client, project_id: int, resource_name: str, file_type: int):
    """按精确文件名查询，返回 file_id 或 None。"""
    resp = with_throttle_retry(
        client.list_files,
        dw_models.ListFilesRequest(
            project_id=project_id,
            exact_file_name=resource_name,
            file_types=str(file_type),
            page_number=1,
            page_size=1,
        ),
    )
    files = resp.body.data.files if resp.body.data else None
    if files and files[0].file_name == resource_name:
        return files[0].file_id
    return None


def upload_or_update(client, content: str, resource_name: str, project_id: int,
                     file_type: int, folder_path: str, register_to_engine: bool,
                     file_path: str, auto_yes: bool = False):
    existing_id = find_existing_file(client, project_id, resource_name, file_type)
    type_name = FILE_TYPE_NAMES.get(file_type, str(file_type))

    if existing_id:
        if not auto_yes:
            print(f"\n⚠️  发现同名资源：{resource_name}（FileId={existing_id}，项目 {project_id}）")
            answer = input("已存在同名资源，是否覆盖？输入 yes 确认，其他任意键取消：").strip().lower()
            if answer != "yes":
                raise UserCancelledError("用户取消覆盖操作")
        else:
            print(f"\n[复用] 同名资源已存在：{resource_name}（FileId={existing_id}）——--yes 复用覆盖（固定资源名约定）")
        print(f"[1/4] 更新中：{file_path} -> 项目 {project_id} / {resource_name}（{type_name}, FileId={existing_id}）")
        with_throttle_retry(
            client.update_file,
            dw_models.UpdateFileRequest(
                project_id=project_id,
                file_id=existing_id,
                content=content,
            ),
        )
        print(f"      更新成功  FileId={existing_id}")
        return existing_id
    else:
        print(f"[1/4] 上传中：{file_path} -> 项目 {project_id} / {resource_name}（{type_name}，新建）")
        resp = with_throttle_retry(
            client.create_resource_file,
            dw_models.CreateResourceFileRequest(
                project_id=project_id,
                file_name=resource_name,
                file_folder_path=folder_path,
                file_type=file_type,
                origin_resource_name=resource_name,
                register_to_calc_engine=register_to_engine,
                content=content,
            ),
        )
        file_id = resp.body.data
        print(f"      上传成功  FileId={file_id}")
        return file_id


def submit_file(client, project_id: int, file_id: int, comment: str = "auto submit"):
    print(f"[2/4] 提交中：FileId={file_id}")
    resp = with_throttle_retry(
        client.submit_file,
        dw_models.SubmitFileRequest(
            project_id=project_id,
            file_id=file_id,
            comment=comment,
        ),
    )
    deployment_id = resp.body.data
    print(f"      提交任务已创建  DeploymentId={deployment_id}")

    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        d = with_throttle_retry(
            client.get_deployment,
            dw_models.GetDeploymentRequest(
                project_id=project_id,
                deployment_id=deployment_id,
            ),
        ).body.data.deployment

        if d.status == DEPLOY_DONE:
            print("      提交完成")
            return deployment_id
        if d.status == DEPLOY_FAILED:
            raise RuntimeError(f"提交失败：{d.error_message}")

        print(f"      提交进行中，等待 {POLL_INTERVAL}s ...")
        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"提交超时（>{POLL_TIMEOUT}s），DeploymentId={deployment_id}")


def deploy_file(client, project_id: int, file_id: int, comment: str = "auto deploy"):
    print(f"[3/4] 发布中：FileId={file_id}")
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        try:
            with_throttle_retry(
                client.deploy_file,
                dw_models.DeployFileRequest(
                    project_id=project_id,
                    file_id=file_id,
                    comment=comment,
                ),
            )
            print("      发布成功")
            return
        except Exception as e:
            if "pipe line is not ready" in str(e):
                print(f"      Pipeline 未就绪，等待 {POLL_INTERVAL}s 后重试...")
                time.sleep(POLL_INTERVAL)
            else:
                raise
    raise TimeoutError(f"发布超时（>{POLL_TIMEOUT}s），FileId={file_id}")


def verify_content(client, project_id: int, file_id: int, local_content: str,
                   file_type: int):
    print(f"[4/4] 校验中：读取远端内容...")
    resp = with_throttle_retry(
        client.get_file,
        dw_models.GetFileRequest(
            project_id=project_id,
            file_id=file_id,
        ),
    )
    remote_content = resp.body.data.file.content or ""

    # JAR 等二进制文件：远端返回 JSON 元数据，只校验 type 字段
    if file_type in BINARY_TYPES:
        try:
            meta = json.loads(remote_content)
            expected_type = FILE_TYPE_NAMES.get(file_type, "").upper()
            if meta.get("type", "").upper() == expected_type:
                print(f"      校验通过：远端资源类型确认为 {expected_type} ✓")
                return
            else:
                raise ValueError(f"远端 type={meta.get('type')}，期望 {expected_type}")
        except json.JSONDecodeError:
            raise ValueError(f"远端返回内容无法解析：{remote_content[:100]}")

    # 文本文件：直接比对内容
    if remote_content.strip() == local_content.strip():
        print("      校验通过：远端内容与本地一致 ✓")
    else:
        print("      校验失败：远端内容与本地不一致！")
        print(f"      本地长度={len(local_content)}  远端长度={len(remote_content)}")
        raise ValueError("上传内容校验失败，请重新上传")


# ── 主逻辑 ────────────────────────────────────────────────────────────────────

def upload_and_publish(
    file_path: str,
    resource_name: str,
    project_id: int = DEFAULT_PROJECT_ID,
    file_type: int = None,
    folder_path: str = "/",
    register_to_engine: bool = False,
    profile_name: str = "AkProfile",
    env_file: str = None,
    client=None,
    auto_yes: bool = False,
):
    # 文件存在性检查
    if not Path(file_path).exists():
        raise FileNotFoundError(f"文件不存在：{file_path}")

    # 自动推断 file_type（合并进 [1/4] 步骤，提示统一）
    if file_type is None:
        file_type = infer_file_type(file_path)

    if client is None:
        ak = resolve_ak(profile_name, env_file)
        client = create_client(ak)

    # 只读取一次文件内容，后续步骤复用
    content = read_file_content(file_path, file_type)

    file_id = upload_or_update(client, content, resource_name, project_id,
                                file_type, folder_path, register_to_engine, file_path,
                                auto_yes=auto_yes)
    submit_file(client, project_id, file_id)
    deploy_file(client, project_id, file_id)
    verify_content(client, project_id, file_id, content, file_type)

    print(f"\n完成！资源 {resource_name} 已发布到项目 {project_id}，FileId={file_id}")
    return file_id


def batch_upload(file_paths: list, project_id: int, folder_path: str,
                 profile_name: str, file_type: int = None, auto_yes: bool = False,
                 env_file: str = None):
    """批量上传多个文件，共用同一个客户端连接。"""
    ak = resolve_ak(profile_name, env_file)
    client = create_client(ak)

    results = []
    for i, fp in enumerate(file_paths, 1):
        print(f"\n{'='*50}")
        print(f"[{i}/{len(file_paths)}] 处理文件：{fp}")
        print('='*50)
        try:
            file_id = upload_and_publish(
                file_path=fp,
                resource_name=Path(fp).name,
                project_id=project_id,
                file_type=file_type,
                folder_path=folder_path,
                profile_name=profile_name,
                client=client,
                auto_yes=auto_yes,
            )
            results.append({"file": fp, "file_id": file_id, "status": "成功"})
        except UserCancelledError:
            results.append({"file": fp, "file_id": None, "status": "已取消"})
        except Exception as e:
            results.append({"file": fp, "file_id": None, "status": f"失败：{e}"})
            print(f"      ❌ 上传失败：{e}")

    print(f"\n{'='*50}")
    print("批量上传结果：")
    for r in results:
        status_icon = "✓" if r["status"] == "成功" else "✗"
        print(f"  {status_icon} {Path(r['file']).name:30s}  {r['status']}")
    return results


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="上传文件到阿里云 DataWorks 资源并发布",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例：
  # 单文件（资源名默认取文件名，类型自动推断）
  python upload.py my_script.py

  # 指定资源名和项目
  python upload.py my_script.py --name utils.py --project-id 302182

  # 批量上传
  python upload.py file1.py file2.py file3.jar

  # 批量上传并统一指定类型
  python upload.py file1 file2 --file-type 15

file_type 自动推断：.py -> 12（Python），.jar -> 13（JAR），其他 -> 15（File）
默认项目 ID：{DEFAULT_PROJECT_ID}
        """,
    )
    parser.add_argument("files", nargs="+", help="本地文件路径，支持多个")
    parser.add_argument("--name", "-n", help="资源名（仅单文件时有效，默认取文件名）")
    parser.add_argument("--project-id", "-p", type=int, default=DEFAULT_PROJECT_ID,
                        help=f"DataWorks 项目 ID（默认 {DEFAULT_PROJECT_ID}）")
    parser.add_argument("--file-type", "-t", type=int,
                        help="文件类型（12=Python, 13=JAR, 15=File，默认按扩展名推断）")
    parser.add_argument("--folder", "-f", default="/", help="资源目录（默认 /）")
    parser.add_argument("--profile", default="AkProfile", help="AK profile 名称")
    parser.add_argument("--env-file", help="AK 来源 .env 文件（2026-09-20 约定：AK 统一从 .env 获取，"
                                          "优先级高于 --profile）")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="复用覆盖模式：发现同名资源直接覆盖更新，不交互询问"
                             "（固定资源名复用约定，配合 --name 固定名使用）")

    args = parser.parse_args()

    try:
        if len(args.files) == 1:
            upload_and_publish(
                file_path     = args.files[0],
                resource_name = args.name or Path(args.files[0]).name,
                project_id    = args.project_id,
                file_type     = args.file_type,
                folder_path   = args.folder,
                profile_name  = args.profile,
                env_file      = args.env_file,
                auto_yes      = args.yes,
            )
        else:
            if args.name:
                print("警告：批量模式下 --name 参数无效，资源名将使用各文件的文件名")
            batch_upload(
                file_paths   = args.files,
                project_id   = args.project_id,
                folder_path  = args.folder,
                profile_name = args.profile,
                file_type    = args.file_type,
                env_file     = args.env_file,
                auto_yes     = args.yes,
            )
    except UserCancelledError as e:
        print(f"已取消：{e}")
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"错误：{e}")
        sys.exit(1)
