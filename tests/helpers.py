"""测试辅助：在临时目录里搭建一个完整的演示环境。"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from homeshift.context import AppContext
from homeshift.datagen.generate import init_dataset


def make_ctx(tmpdir: str | Path, days: int = 28) -> AppContext:
    ctx = AppContext(root=Path(tmpdir))
    init_dataset(ctx, days=days, seed=42, end=date(2026, 7, 26))
    ctx.store.ensure_default_profile()
    return ctx


class TempEnv:
    """with TempEnv() as ctx: ... 用完自动清理。"""

    def __init__(self, days: int = 28):
        self.days = days
        self._tmp = None

    def __enter__(self) -> AppContext:
        self._tmp = tempfile.TemporaryDirectory()
        return make_ctx(self._tmp.name, days=self.days)

    def __exit__(self, *exc) -> None:
        self._tmp.cleanup()
