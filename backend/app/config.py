from __future__ import annotations

import os
import threading
from typing import Any, Dict
import yaml
from .models import AppSettings


_CONFIG_PATH = os.environ.get("RSS_AI_CONFIG", os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
_CONFIG_PATH = os.path.abspath(_CONFIG_PATH)

_lock = threading.RLock()


def ensure_default_config():
    # If config.yaml does not exist, copy from example
    cfg_dir = os.path.dirname(_CONFIG_PATH)
    if not os.path.exists(cfg_dir):
        os.makedirs(cfg_dir, exist_ok=True)
    if not os.path.exists(_CONFIG_PATH):
        example_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.example.yaml"))
        if os.path.exists(example_path):
            with open(example_path, "r", encoding="utf-8") as f:
                data = f.read()
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(data)


def config_path() -> str:
    return _CONFIG_PATH


def load_settings() -> AppSettings:
    ensure_default_config()
    with _lock:
        if not os.path.exists(_CONFIG_PATH):
            return AppSettings()
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return AppSettings(**data)


def save_settings(settings: AppSettings) -> None:
    with _lock:
        # Convert to dict in snake_case keys (Pydantic already uses snake_case)
        data = settings.model_dump()
        cfg_dir = os.path.dirname(_CONFIG_PATH)
        os.makedirs(cfg_dir, exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

