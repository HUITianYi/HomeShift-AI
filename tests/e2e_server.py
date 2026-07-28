"""为 Playwright 启动隔离的临时 HomeShift API，不触碰项目 data/。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from homeshift.api import create_app  # noqa: E402
from tests.helpers import make_ctx  # noqa: E402


with tempfile.TemporaryDirectory(prefix="homeshift_e2e_") as folder:
    make_ctx(folder, days=28)
    uvicorn.run(create_app(Path(folder)), host="127.0.0.1", port=18000)
