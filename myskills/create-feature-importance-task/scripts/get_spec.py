from datetime import datetime
import argparse
import json

# 固定不变的 Spark 基础配置，每行一条方便维护
_BASE_SPARK_CONFIGS = [
    "spark.driver.cores=8",
    "spark.driver.memory=32g",
    "spark.executor.instances=20",
    "spark.executor.cores=4",
    "spark.executor.memory=32g",
    "spark.driver.maxResultSize=32g",
    "spark.hadoop.odps.cupid.resources=du_risk_training.my_env.tar.gz",
    "spark.hadoop.fs.AbstractFileSystem.oss.impl=com.aliyun.emr.fs.oss.OSS",
    "spark.hadoop.fs.oss.impl=com.aliyun.emr.fs.oss.JindoOssFileSystem",
    "spark.hadoop.odps.spark.version=spark-3.5.2-odps0.34.0",
    "spark.executorEnv.PYTHONPATH=./du_risk_training.my_env.tar.gz/packages",
    "spark.yarn.appMasterEnv.PYTHONPATH=./du_risk_training.my_env.tar.gz/packages",
    "spark.hadoop.odps.spark.alinux3.enabled=true",
    "spark.hadoop.odps.kube.mode=true",
    "spark.dynamicAllocation.enabled=false",
    "spark.hadoop.odps.cupid.trusted.services.access.list=dw-risk-data-model.oss-cn-hangzhou-internal.aliyuncs.com",
    "spark.hadoop.odps.cupid.shuffle.partition.max.size=256",
    "spark.hadoop.odps.cupid.shuffle.partition.min.size=64",
]


def generate_task_id() -> str:
    """生成基于时间的 task_id，格式为 YYYYMMDD_HHMMSS_mmm"""
    now = datetime.now()
    return now.strftime("%Y%m%d_%H%M%S") + f"_{now.microsecond // 1000:03d}"


def build_script_content(input_table_name: str, label_col: str, task_id: str, exclude_cols="request_id,user_id,uid,userid") -> str:
    """构建 ODPS Spark 节点的 script content 字符串。

    格式为两行：首行是资源引用声明，第二行是 Spark 配置 JSON。
    使用 json.dumps 序列化，避免参数含特殊字符时破坏 JSON 结构。
    """
    dynamic_configs = [
        f"spark.input_table_name={input_table_name}",
        f"spark.task_id={task_id}",
        f"spark.label_col={label_col}",
        f"spark.exclude_cols={exclude_cols}",
    ]
    spark_config = {
        "version": "3.x",
        "language": "python",
        "configs": _BASE_SPARK_CONFIGS + dynamic_configs,
        "mainPy": "get_feature_importance.py",
        "assistPys": [],
    }
    resource_ref = '##@resource_reference{"get_feature_importance.py"}'
    return resource_ref + "\n" + json.dumps(spark_config, ensure_ascii=False, separators=(",", ":"))


def create_node_spec(input_table_name: str, label_col: str, exclude_cols="request_id,user_id,uid,userid") -> str:
    """生成 DataWorks 节点 spec JSON 字符串。

    Args:
        input_table_name: 输入表名，格式为 project.table
        label_col: 标签列名

    Returns:
        节点 spec 的 JSON 字符串，可直接传给 aliyun CLI 的 --spec 参数
    """
    task_id = generate_task_id()
    node_name = f"特征重要性_手动_{task_id}"

    spec = {
        "version": "1.1.0",
        "kind": "Node",
        "spec": {
            "nodes": [
                {
                    "id": "",  # DataWorks 创建后自动填充
                    "recurrence": "Normal",
                    "timeout": 0,
                    "instanceMode": "T+1",
                    "rerunMode": "Allowed",
                    "rerunTimes": 3,
                    "rerunInterval": 180000,
                    "datasource": {"name": "du_risk_training", "type": "odps"},
                    "script": {
                        "language": "python",
                        "path": node_name,
                        "runtime": {"command": "ODPS_SPARK", "commandTypeId": 225},
                        "content": build_script_content(input_table_name, label_col, task_id,exclude_cols),
                    },
                    "trigger": {"type": "Manual", "timezone": "Asia/Shanghai"},
                    "runtimeResource": {
                        "resourceGroup": "Serverless_res_group_235454102432001_733371449043168",
                        "resourceGroupName": "du_risk_serverless_scheduler",
                    },
                    "name": node_name,
                    "inputs": {"nodeOutputs": []},
                }
            ]
        },
    }

    return json.dumps(spec, ensure_ascii=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成特征重要性任务的 DataWorks 节点 spec")
    parser.add_argument("--input_table_name", required=True, help="输入表名，格式为 project.table")
    parser.add_argument("--label_col", required=True, help="标签列名")
    parser.add_argument("--exclude_cols", required=False, help="排除列，如：uid,req_id")
    args = parser.parse_args()

    print(create_node_spec(args.input_table_name, args.label_col, args.exclude_cols), end="")
