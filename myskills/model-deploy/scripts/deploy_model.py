"""
模型部署脚本
将 du_risk_training 空间 模型部署4Agent 目录下的 模型部署_模版 节点
拷贝并配置后发布到生产环境。

实现方式：读取模板节点 spec → 修改配置 → CreateNode 创建新节点 → 发布
"""
import sys
import os
import json
import time
import argparse
import copy
from typing import Dict, Any

from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_dataworks_public20240518.client import Client as DataWorksClient
from alibabacloud_dataworks_public20240518 import models as dw_models


# ── 项目配置 ──────────────────────────────────────────────────
PROJECT_ID = 302182          # du_risk_training 项目空间 ID
TEMPLATE_NODE_ID = "5328940533258691559"   # 模型部署_模版 节点 ID
CONTAINER_PATH = "模型部署4Agent"           # 目标目录路径
ENDPOINT = "dataworks.cn-hangzhou.aliyuncs.com"


# ── 客户端初始化 ───────────────────────────────────────────────
def _build_client() -> DataWorksClient:
    access_key_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
    access_key_secret = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    if not access_key_id or not access_key_secret:
        raise EnvironmentError(
            "请先设置环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID 和 ALIBABA_CLOUD_ACCESS_KEY_SECRET"
        )
    config = open_api_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        endpoint=ENDPOINT,
    )
    return DataWorksClient(config)


runtime = util_models.RuntimeOptions()


# ── Step 1：获取模板节点 spec ──────────────────────────────────
def get_template_spec(client: DataWorksClient) -> Dict:
    print(f"📋 读取模板节点 spec (ID: {TEMPLATE_NODE_ID}) ...")
    req = dw_models.GetNodeRequest(id=TEMPLATE_NODE_ID, project_id=PROJECT_ID)
    resp = client.get_node_with_options(req, runtime)
    spec_str = resp.body.node.spec
    if not spec_str:
        raise ValueError("模板节点 spec 为空")
    spec = json.loads(spec_str)
    print("   模板 spec 读取成功")
    return spec


# ── Step 2：构建新节点的 spec ─────────────────────────────────
def build_new_spec(
    template_spec: Dict,
    node_name: str,
    model_table: str,
    input_table: str,
    output_table: str,
) -> str:
    """
    基于模板 spec 构建新节点的 spec：
    - 移除旧 id（由平台分配）
    - 修改节点名称和路径
    - 替换 spark.model_table / spark.input_table / spark.output_table
    - 配置同周期依赖（input_table）和节点输出（output_table）
    """
    print(f"🔧 构建新节点 spec ...")
    spec = copy.deepcopy(template_spec)

    node = spec["spec"]["nodes"][0]

    # 移除旧 id，由平台重新分配
    node.pop("id", None)
    node.pop("metadata", None)

    # 修改名称
    node["name"] = node_name
    node["script"]["path"] = f"{CONTAINER_PATH}/{node_name}"

    # 移除旧的 script id（新建时不需要）
    node["script"].pop("id", None)

    # 修改 content 中的三个 spark 配置
    content_str = node["script"]["content"]
    content = json.loads(content_str)
    configs: list = content.get("configs", [])

    spark_keys = {
        "spark.model_table": model_table,
        "spark.input_table": input_table,
        "spark.output_table": output_table,
    }
    # 删除旧的同名配置，再追加新的
    for key in spark_keys:
        configs = [c for c in configs if not c.startswith(f"{key}=")]
    for key, val in spark_keys.items():
        configs.append(f"{key}={val}")

    content["configs"] = configs
    node["script"]["content"] = json.dumps(content, ensure_ascii=False)

    # 配置同周期依赖：将 input_table 加入 inputs.nodeOutputs
    node_outputs_in = node.setdefault("inputs", {}).setdefault("nodeOutputs", [])
    # 保留原有依赖（du_risk_training_root），追加 input_table 依赖
    dep = {
        "artifactType": "NodeOutput",
        "sourceType": "Manual",
        "data": input_table,
        "refTableName": input_table,
    }
    if not any(o.get("data") == input_table for o in node_outputs_in):
        node_outputs_in.append(dep)

    # 配置节点输出：output_table
    node_outputs_out = node.setdefault("outputs", {}).setdefault("nodeOutputs", [])
    # 移除旧的系统自动 output（含旧模板名），替换为新的
    node_outputs_out_clean = [o for o in node_outputs_out if o.get("sourceType") != "System"]
    out_entry = {
        "artifactType": "NodeOutput",
        "sourceType": "Manual",
        "data": output_table,
        "refTableName": output_table,
    }
    if not any(o.get("data") == output_table for o in node_outputs_out_clean):
        node_outputs_out_clean.append(out_entry)
    node["outputs"]["nodeOutputs"] = node_outputs_out_clean

    # 更新 flow 中的依赖
    spec["spec"]["flow"] = [
        {
            "depends": [
                {
                    "type": "Normal",
                    "output": "du_risk_training_root",
                    "sourceType": "Manual",
                },
                {
                    "type": "Normal",
                    "output": input_table,
                    "sourceType": "Manual",
                },
            ]
        }
    ]

    # 更新 metadata uuid（移除，让平台分配）
    spec.pop("metadata", None)

    result_str = json.dumps(spec, ensure_ascii=False)
    print(f"   新节点 spec 构建完成，节点名：{node_name}")
    return result_str


# ── Step 3：创建节点 ──────────────────────────────────────────
def create_node(client: DataWorksClient, spec_str: str) -> str:
    print(f"🆕 创建新节点 ...")
    req = dw_models.CreateNodeRequest(
        project_id=PROJECT_ID,
        scene="DATAWORKS_PROJECT",
        spec=spec_str,
    )
    resp = client.create_node_with_options(req, runtime)
    new_node_id = str(resp.body.id)
    print(f"   节点创建成功，inner_node_id：{new_node_id}")
    return new_node_id


# ── Step 4：发布到生产环境 ────────────────────────────────────
def publish_node(client: DataWorksClient, node_id: str) -> str:
    """执行四阶段发布流程，返回 node_task_id"""
    print("🚀 开始发布到生产环境 ...")

    req = dw_models.CreatePipelineRunRequest(
        project_id=PROJECT_ID,
        type="Online",
        object_ids=[node_id],
    )
    resp = client.create_pipeline_run_with_options(req, runtime)
    publish_uuid = resp.body.id
    print(f"   发布流程 UUID：{publish_uuid}")

    # 等待 BUILD_PACKAGE 自动完成后再执行后续阶段
    print("   等待 BUILD_PACKAGE 完成 ...")
    while True:
        time.sleep(5)
        resp_info = client.get_pipeline_run_with_options(
            dw_models.GetPipelineRunRequest(id=publish_uuid, project_id=PROJECT_ID), runtime)
        build_status = next(
            (s.status for s in resp_info.body.pipeline.stages if s.code == "BUILD_PACKAGE"), None
        )
        print(f"     BUILD_PACKAGE 状态：{build_status}")
        if build_status not in ("Init", "Running"):
            break
    if build_status != "Success":
        raise RuntimeError(f"BUILD_PACKAGE 失败，状态：{build_status}")
    print("   BUILD_PACKAGE 完成 ✓")

    stages = ["DEV_CHECK", "DEV", "PROD_CHECK", "PROD"]
    for stage in stages:
        print(f"   执行阶段：{stage} ...")
        exec_req = dw_models.ExecPipelineRunStageRequest(
            id=publish_uuid,
            code=stage,
            project_id=PROJECT_ID,
        )
        client.exec_pipeline_run_stage_with_options(exec_req, runtime)

        # 轮询等待当前阶段完成（按 Code 字段匹配，不依赖下标）
        status = "Init"
        while True:
            time.sleep(5)
            get_req = dw_models.GetPipelineRunRequest(
                id=publish_uuid,
                project_id=PROJECT_ID,
            )
            resp_info = client.get_pipeline_run_with_options(get_req, runtime)
            # 按 code 找到当前阶段
            stage_status = None
            for s in resp_info.body.pipeline.stages:
                if s.code == stage:
                    stage_status = s.status
                    break
            if stage_status is None:
                print(f"     未找到阶段 {stage}，跳过")
                break
            status = stage_status
            print(f"     阶段 {stage} 状态：{status}")
            if status not in ("Init", "Running"):
                break

        if status not in ("Success", "Skipped"):
            raise RuntimeError(
                f"发布阶段 {stage} 失败，状态：{status}，请到 DataWorks 控制台查看发布详情"
            )
        print(f"   阶段 {stage} 完成 ✓")

    # 获取发布后的 node_task_id
    time.sleep(3)
    get_node_req = dw_models.GetNodeRequest(id=node_id, project_id=PROJECT_ID)
    resp = client.get_node_with_options(get_node_req, runtime)
    node_task_id = str(resp.body.node.task_id) if resp.body.node.task_id else "未获取到"
    print(f"✅ 发布完成，node_task_id：{node_task_id}")
    return node_task_id


# ── 主流程 ────────────────────────────────────────────────────
def deploy_model(
    node_name: str,
    model_table: str,
    input_table: str,
    output_table: str,
) -> Dict[str, Any]:
    client = _build_client()
    new_node_id = None

    try:
        # 1. 读取模板 spec
        template_spec = get_template_spec(client)

        # 2. 构建新节点 spec
        new_spec_str = build_new_spec(
            template_spec, node_name, model_table, input_table, output_table
        )

        # 3. 创建节点
        new_node_id = create_node(client, new_spec_str)

        # 4. 发布到生产
        node_task_id = publish_node(client, new_node_id)

        result = {
            "success": True,
            "inner_node_id": new_node_id,
            "node_task_id": node_task_id,
            "node_name": node_name,
            "message": "模型部署完成，节点已发布到生产环境",
        }

    except Exception as e:
        print(f"\n❌ 部署失败：{e}")
        result = {
            "success": False,
            "inner_node_id": new_node_id,
            "node_task_id": None,
            "node_name": node_name,
            "message": str(e),
        }

    print("\n" + "=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="模型部署工具")
    parser.add_argument("--node_name", required=True, help="新部署任务的名称")
    parser.add_argument("--model_table", required=True, help="模型文件表名（由 model-train 生成）")
    parser.add_argument("--input_table", required=True, help="输入特征表名（分区表）")
    parser.add_argument("--output_table", required=True, help="预测结果输出表名")
    args = parser.parse_args()

    deploy_model(
        node_name=args.node_name,
        model_table=args.model_table,
        input_table=args.input_table,
        output_table=args.output_table,
    )
