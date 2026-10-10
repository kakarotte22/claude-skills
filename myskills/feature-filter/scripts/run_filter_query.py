"""
feature-filter skill 辅助脚本
通过 pyodps 执行三类操作：
  1. 查询特征重要性表，返回需剔除的 feature_name 列表（--importance_table + --filter_sql）
  2. 获取指定表的所有列名和分区列名（--get_columns）
  3. 执行建表 SQL（--create_table_project + --create_table_sql）

AK 自动从 ~/.aliyun/config.json 读取，不通过命令行传入。
"""

import argparse
import json
import os
import sys

try:
    import odps
except ImportError:
    print(
        "❌ 未检测到 pyodps，请先安装：\n"
        "\n"
        "    pip install pyodps\n"
        "\n"
        "安装完成后重新执行即可。",
        file=sys.stderr,
    )
    sys.exit(2)


def load_ak():
    """从 ~/.aliyun/config.json 读取当前 profile 的 AK 信息"""
    config_path = os.path.expanduser("~/.aliyun/config.json")
    try:
        with open(config_path) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print(
            f"❌ 未找到阿里云配置文件：{config_path}\n"
            "请先运行 `aliyun configure` 完成配置，或手动创建该文件。",
            file=sys.stderr,
        )
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ 配置文件格式错误（{config_path}）：{e}", file=sys.stderr)
        sys.exit(1)

    current = cfg.get("current")
    if not current:
        print(
            "❌ 配置文件中未找到 'current' 字段，请检查 ~/.aliyun/config.json",
            file=sys.stderr,
        )
        sys.exit(1)

    profile = next((p for p in cfg.get("profiles", []) if p["name"] == current), None)
    if profile is None:
        print(
            f"❌ 未找到名为 '{current}' 的 profile，请检查 ~/.aliyun/config.json",
            file=sys.stderr,
        )
        sys.exit(1)

    return (
        profile["access_key_id"],
        profile["access_key_secret"],
        profile.get("region_id", "cn-hangzhou"),
    )


def get_odps(project: str) -> odps.ODPS:
    ak_id, ak_secret, region = load_ak()
    endpoint = f"http://service.{region}.maxcompute.aliyun.com/api"
    return odps.ODPS(
        access_id=ak_id,
        secret_access_key=ak_secret,
        project=project,
        endpoint=endpoint,
    )


def parse_project_table(full_name: str):
    """将 'project.table' 拆分为 (project, table)"""
    parts = full_name.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"表名格式错误，应为 project.table，实际为：{full_name}")
    return parts[0], parts[1]


def query_excluded_features(importance_table, filter_sql, extra_exclude=None):
    """
    执行 filter_sql 查询特征重要性表，输出需要剔除的 feature_name 列表。
    filter_sql 必须是完整 SELECT 语句（含 FROM 子句），返回列必须包含 feature_name。
    extra_exclude 为逗号分隔的额外强制剔除特征名，直接输出，不经过重要性表查询。
    每行输出格式：FEATURE:<feature_name>
    重复特征名自动去重（同一特征名只输出一次）。
    """
    project, _ = parse_project_table(importance_table)
    o = get_odps(project)

    seen = set()
    with o.execute_sql(filter_sql).open_reader() as reader:
        for record in reader:
            feature_name = record["feature_name"]
            if feature_name and feature_name not in seen:
                seen.add(feature_name)
                print(f"FEATURE:{feature_name}")

    if extra_exclude:
        for name in extra_exclude.split(","):
            name = name.strip()
            if name and name not in seen:
                seen.add(name)
                print(f"FEATURE:{name}")


def get_columns(full_table_name):
    """
    获取指定表的所有列名和分区列名。
    普通列输出格式：COLUMN:<col_name>
    分区列输出格式：PARTITION:<col_name>
    """
    project, table_name = parse_project_table(full_table_name)
    o = get_odps(project)

    table = o.get_table(table_name)
    for col in table.table_schema.columns:
        print(f"COLUMN:{col.name}")
    for part in table.table_schema.partitions:
        print(f"PARTITION:{part.name}")


def execute_create_table(project, create_table_sql):
    """执行建表 SQL，等待完成后输出 CREATE_TABLE:success"""
    o = get_odps(project)
    instance = o.execute_sql(create_table_sql)
    instance.wait_for_success()
    print("CREATE_TABLE:success")


def main():
    parser = argparse.ArgumentParser(description="feature-filter 辅助脚本")

    # 三种操作模式，互斥
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--importance_table", help="特征重要性表名 project.table，配合 --filter_sql 查询需剔除特征")
    group.add_argument("--get_columns", help="获取该表所有列名和分区列名，格式 project.table")
    group.add_argument("--create_table_project", help="执行建表 SQL 所用的 project，配合 --create_table_sql 使用")

    parser.add_argument("--filter_sql", help="完整 SELECT SQL（含 FROM 子句），查询需剔除的特征（结果含 feature_name 列）")
    parser.add_argument("--extra_exclude", help="逗号分隔的额外强制剔除特征名，直接加入排除列表，不经过重要性表查询")
    parser.add_argument("--create_table_sql", help="完整的 CREATE TABLE AS SELECT SQL")

    args = parser.parse_args()

    if args.importance_table:
        if not args.filter_sql:
            print("❌ --importance_table 模式需同时提供 --filter_sql", file=sys.stderr)
            sys.exit(1)
        query_excluded_features(args.importance_table, args.filter_sql, args.extra_exclude)

    elif args.get_columns:
        get_columns(args.get_columns)

    elif args.create_table_project:
        if not args.create_table_sql:
            print("❌ --create_table_project 模式需同时提供 --create_table_sql", file=sys.stderr)
            sys.exit(1)
        execute_create_table(args.create_table_project, args.create_table_sql)


if __name__ == "__main__":
    main()
