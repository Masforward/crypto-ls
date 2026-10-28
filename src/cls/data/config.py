"""读取项目根目录的 config.yaml 配置（数据根目录等）。"""
import os

import yaml

# 项目根目录 = src/cls/data 往上四层（crypto-ls/config.yaml）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_CONFIG_PATH = os.path.join(_ROOT, "config.yaml")


def load_config():
    """读取 config.yaml，返回字典；文件不存在则返回空字典。"""
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def data_dir():
    """返回数据根目录（默认 data）。"""
    return load_config().get("data_dir", "data")
