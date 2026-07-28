"""可选的真实模型中英文冒烟测试；只使用临时合成家庭，不修改项目 data/。"""

from __future__ import annotations

import tempfile
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from homeshift.api import create_app
from homeshift.config import save_config_patch
from tests.helpers import make_ctx


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="homeshift_live_smoke_") as folder:
        root = Path(folder)
        make_ctx(root, days=28)
        save_config_patch(
            {
                "llm": {
                    "provider": "deepseek",
                    "model": "deepseek-v4-pro",
                    "max_tool_rounds": 10,
                }
            },
            root,
        )
        client = TestClient(create_app(root))
        success = True
        for locale in ("zh", "en"):
            response = client.post("/api/v1/diagnose", json={"locale": locale})
            body = response.json()
            if response.status_code == 200:
                run = body["run"]
                print(
                    f"{locale}: status=200 mode={run['mode']} "
                    f"provider={run['provider']} model={run['model']} "
                    f"trace={len(run['trace'])} final_chars={len(run['final_text'])}",
                    flush=True,
                )
            else:
                success = False
                error = body.get("error", {})
                print(
                    f"{locale}: status={response.status_code} code={error.get('code')} "
                    f"message={error.get('message')}",
                    flush=True,
                )
        return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
