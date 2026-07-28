"""应用上下文：把配置、数据访问、持久记忆装配到一起。

所有工具函数（agent/tools.py）通过这一个对象访问系统能力，
测试时可指向临时目录，实现完全隔离。
"""

from __future__ import annotations

from pathlib import Path

from .config import PROJECT_ROOT, load_config
from .datastore.store import Store
from .datastore.usage import UsageStore


class AppContext:
    def __init__(self, root: Path | None = None, config: dict | None = None):
        self.root = Path(root) if root else PROJECT_ROOT
        self.config = config or load_config(self.root)
        self.data_dir = self.root / self.config["data_dir"]
        self.usage = UsageStore(self.data_dir)
        self.store = Store(self.data_dir)
