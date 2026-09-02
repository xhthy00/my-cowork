#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hooks.json 占位符替换安装器。

将 hooks.json 中的 {{PYTHON_BIN}} 和 {{HOOKS_DIR}} 占位符替换为真实路径，
生成可直接加载的 hooks 配置，降低对运行时占位符替换能力的依赖。

用法：
  # 1. 自动探测（推荐）：用当前 Python 解释器 + 脚本所在目录作为 HOOKS_DIR
  python install_hooks.py

  # 2. 通过命令行参数指定
  python install_hooks.py --python-bin /usr/bin/python3 --hooks-dir /path/to/hooks

  # 3. 通过环境变量指定
  PYTHON_BIN=/usr/bin/python3 HOOKS_DIR=/path/to/hooks python install_hooks.py

  # 4. 指定输出路径（默认输出到 hooks.installed.json，不覆盖原模板）
  python install_hooks.py --output /path/to/hooks.final.json

  # 5. 原地覆盖（谨慎使用）
  python install_hooks.py --in-place

优先级：命令行参数 > 环境变量 > 自动探测
"""
import argparse
import json
import os
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(
        description="hooks.json 占位符替换安装器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--python-bin",
        default=os.environ.get("PYTHON_BIN", ""),
        help="Python 解释器路径（默认：当前 sys.executable，或环境变量 PYTHON_BIN）",
    )
    parser.add_argument(
        "--hooks-dir",
        default=os.environ.get("HOOKS_DIR", ""),
        help="hook 脚本目录（默认：本脚本所在目录，或环境变量 HOOKS_DIR）",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="输入 hooks.json 模板路径（默认：本脚本上级目录的 hooks.json）",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="输出路径（默认：与输入同目录的 hooks.installed.json，不覆盖原模板）",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="原地覆盖输入文件（谨慎使用，会丢失模板占位符；自动备份为 .bak）",
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 解析 Python 解释器路径
    python_bin = args.python_bin or sys.executable
    if not os.path.isabs(python_bin):
        python_bin = os.path.abspath(python_bin)
    if not os.path.isfile(python_bin):
        print("[INSTALL-HOOKS] 错误：Python 解释器不存在: %s" % python_bin, file=sys.stderr)
        return 1

    # 解析 hooks 目录
    hooks_dir = args.hooks_dir or script_dir
    if not os.path.isabs(hooks_dir):
        hooks_dir = os.path.abspath(hooks_dir)
    if not os.path.isdir(hooks_dir):
        print("[INSTALL-HOOKS] 错误：hooks 目录不存在: %s" % hooks_dir, file=sys.stderr)
        return 1

    # 解析输入路径（默认上级目录的 hooks.json）
    input_path = args.input or os.path.abspath(os.path.join(script_dir, "..", "hooks.json"))
    if not os.path.isfile(input_path):
        print("[INSTALL-HOOKS] 错误：hooks.json 模板不存在: %s" % input_path, file=sys.stderr)
        return 1

    # 解析输出路径
    if args.in_place:
        output_path = input_path
    else:
        output_path = args.output or os.path.join(
            os.path.dirname(input_path), "hooks.installed.json"
        )
        output_path = os.path.abspath(output_path)

    # 读取模板
    try:
        with open(input_path, encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        print("[INSTALL-HOOKS] 错误：读取模板失败: %s" % e, file=sys.stderr)
        return 1

    # 替换占位符（Windows 路径反斜杠在 JSON 字符串中需转义）
    python_bin_escaped = python_bin.replace("\\", "\\\\")
    hooks_dir_escaped = hooks_dir.replace("\\", "\\\\")
    replacements = {
        "{{PYTHON_BIN}}": python_bin_escaped,
        "{{HOOKS_DIR}}": hooks_dir_escaped,
    }
    result = raw
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    # 验证 JSON 合法性
    try:
        json.loads(result)
    except json.JSONDecodeError as e:
        print("[INSTALL-HOOKS] 错误：替换后 JSON 解析失败: %s" % e, file=sys.stderr)
        print("[INSTALL-HOOKS] 替换结果片段：", file=sys.stderr)
        print(result[:500], file=sys.stderr)
        return 1

    # 原地覆盖时先备份
    if args.in_place:
        bak = input_path + ".bak"
        try:
            shutil.copy2(input_path, bak)
            print("[INSTALL-HOOKS] 已备份原模板到: %s" % bak)
        except OSError as e:
            print("[INSTALL-HOOKS] 警告：备份失败: %s" % e, file=sys.stderr)

    # 写入输出
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)
    except OSError as e:
        print("[INSTALL-HOOKS] 错误：写入输出失败: %s" % e, file=sys.stderr)
        return 1

    # 摘要
    print("[INSTALL-HOOKS] 安装成功")
    print("  模板: %s" % input_path)
    print("  输出: %s" % output_path)
    print("  Python: %s" % python_bin)
    print("  Hooks Dir: %s" % hooks_dir)
    if not args.in_place:
        print("")
        print("下一步：将 %s 接入你的 Agent 运行时 hooks 配置入口" % output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
