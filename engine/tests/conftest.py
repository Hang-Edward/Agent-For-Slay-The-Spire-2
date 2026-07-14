"""Pytest 配置 — 添加 engine 目录到 Python 路径。"""
import sys
import os

# 将 engine 目录加入 sys.path，使测试能正确导入模块
_engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _engine_dir not in sys.path:
    sys.path.insert(0, _engine_dir)
