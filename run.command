#!/bin/bash
# 工资 / 打卡计算程序 —— 一键启动
# 用法1：在 Finder 里双击本文件（会自动弹出终端并打开界面）
# 用法2：在终端执行  ./run.command
# 退出：在终端按 Ctrl+C，或直接关掉终端窗口

cd "$(dirname "$0")" || exit 1
exec .venv/bin/python main.py
