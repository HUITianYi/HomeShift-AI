"""FastAPI Web 边界测试：状态隔离、显式 Mock、提案/提交与追踪。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from homeshift.agent.prompts import build_system_prompt
from homeshift.api import create_app
from homeshift.context import AppContext

from .helpers import make_ctx


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_ctx(self.root, days=28)
        self.client = TestClient(create_app(self.root))

    def tearDown(self):
        self.temp.cleanup()

    def select_mock(self):
        response = self.client.put(
            "/api/v1/settings/model",
            json={"mode": "mock", "provider": "mock", "model": None},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def complete_diagnosis(self):
        response = self.client.post("/api/v1/diagnose", json={"locale": "zh"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["run"]["operation"], "diagnose")

    def test_status_workspace_and_cors(self):
        root = self.client.get("/", follow_redirects=False)
        self.assertEqual(root.status_code, 307)
        self.assertEqual(root.headers["location"], "/docs")
        self.assertEqual(self.client.get("/favicon.ico").status_code, 204)

        status = self.client.get("/api/v1/status")
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()["ready"])
        workspace = self.client.get("/api/v1/workspace").json()
        self.assertEqual(workspace["agents"]["count"], 7)
        self.assertIn("runtime", workspace)
        self.assertFalse(workspace["runtime"]["workflow"]["diagnosis_completed"])
        preflight = self.client.options(
            "/api/v1/status",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(preflight.headers["access-control-allow-origin"], "http://localhost:5173")

    def test_web_auto_provider_is_blocked(self):
        response = self.client.post("/api/v1/diagnose", json={"locale": "zh"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "configuration_missing")

    def test_proposal_does_not_persist_until_commit(self):
        self.select_mock()
        self.complete_diagnosis()
        proposal = self.client.post("/api/v1/plan/propose", json={"locale": "zh"})
        self.assertEqual(proposal.status_code, 200, proposal.text)
        payload = proposal.json()
        self.assertEqual(payload["run"]["mode"], "mock")
        self.assertTrue(payload["run"]["proposal"]["actions"])
        self.assertFalse(AppContext(root=self.root).store.get_active_plan())
        self.assertTrue(all(step["tool"] != "save_plan" for step in payload["run"]["trace"]))
        self.assertIn("propose_plan", [step["tool"] for step in payload["run"]["trace"]])

        action_ids = [item["id"] for item in payload["run"]["proposal"]["actions"]]
        committed = self.client.post(
            "/api/v1/plan/commit",
            json={
                "action_ids": action_ids,
                "rationale": "用户确认",
                "confirmed_by_user": True,
            },
        )
        self.assertEqual(committed.status_code, 200, committed.text)
        self.assertEqual(committed.json()["plan"]["version"], 1)
        expected = committed.json()["plan"]["expected_per_month"]
        self.assertIn("cost", expected)
        self.assertIn("currency", expected)

    def test_tracking_simulation_is_visibly_marked(self):
        self.select_mock()
        self.complete_diagnosis()
        proposal = self.client.post("/api/v1/plan/propose", json={"locale": "zh"}).json()
        action_ids = [item["id"] for item in proposal["run"]["proposal"]["actions"]]
        self.client.post(
            "/api/v1/plan/commit",
            json={"action_ids": action_ids, "rationale": "test", "confirmed_by_user": True},
        )
        response = self.client.post(
            "/api/v1/tracking/simulate-week",
            json={"adherence": 0.85},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["tracking"]["kind"], "synthetic")
        self.assertTrue(response.json()["workspace"]["track"]["available"])

    def test_real_tracking_upload_appends_after_current_data(self):
        self.select_mock()
        self.complete_diagnosis()
        proposal = self.client.post("/api/v1/plan/propose", json={"locale": "zh"}).json()
        action_ids = [item["id"] for item in proposal["run"]["proposal"]["actions"]]
        self.client.post(
            "/api/v1/plan/commit",
            json={"action_ids": action_ids, "rationale": "test", "confirmed_by_user": True},
        )
        current = AppContext(root=self.root)
        start = current.usage.load_usage()[-1][0] + timedelta(minutes=30)
        lines = ["timestamp,kwh"]
        for index in range(48 * 3):
            ts = start + timedelta(minutes=30 * index)
            lines.append(f"{ts:%Y-%m-%dT%H:%M},0.300")
        response = self.client.post(
            "/api/v1/tracking/import",
            data={"value_unit": "kwh", "weather_source": "none"},
            files={"file": ("after.csv", "\n".join(lines), "text/csv")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["tracking"]["kind"], "real")
        self.assertEqual(response.json()["tracking"]["rows"], 144)

    def test_new_import_resets_plan_memory_and_trace(self):
        self.select_mock()
        self.complete_diagnosis()
        proposal = self.client.post("/api/v1/plan/propose", json={"locale": "zh"}).json()
        action_ids = [item["id"] for item in proposal["run"]["proposal"]["actions"]]
        self.client.post(
            "/api/v1/plan/commit",
            json={"action_ids": action_ids, "rationale": "test", "confirmed_by_user": True},
        )
        no_confirm = self.client.post(
            "/api/v1/datasets/import",
            data={"dataset": "synthetic", "window_days": 14},
        )
        self.assertEqual(no_confirm.status_code, 409)
        self.assertEqual(no_confirm.json()["error"]["code"], "reset_confirmation_required")
        imported = self.client.post(
            "/api/v1/datasets/import",
            data={
                "dataset": "synthetic",
                "window_days": 14,
                "weather_source": "none",
                "confirm_reset": "true",
            },
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        fresh = AppContext(root=self.root)
        self.assertIsNone(fresh.store.get_active_plan())
        self.assertFalse((fresh.data_dir / "last_trace.json").exists())
        self.assertFalse((fresh.data_dir / "workflow_state.json").exists())

    def test_workflow_blocks_plan_and_review_jump_steps(self):
        self.select_mock()
        blocked_plan = self.client.post("/api/v1/plan/propose", json={"locale": "zh"})
        self.assertEqual(blocked_plan.status_code, 409)
        self.assertEqual(
            blocked_plan.json()["error"]["code"],
            "workflow_prerequisite_missing",
        )

        self.complete_diagnosis()
        workflow = self.client.get("/api/v1/workspace").json()["runtime"]["workflow"]
        self.assertTrue(workflow["diagnosis_completed"])
        self.assertEqual(workflow["last_operation"], "diagnosis")

        blocked_commit = self.client.post(
            "/api/v1/plan/commit",
            json={
                "action_ids": ["standby_cut"],
                "rationale": "skip proposal",
                "confirmed_by_user": True,
            },
        )
        self.assertEqual(blocked_commit.status_code, 409)
        self.assertEqual(
            blocked_commit.json()["error"]["code"],
            "workflow_prerequisite_missing",
        )

        proposal = self.client.post("/api/v1/plan/propose", json={"locale": "zh"}).json()
        action_ids = [item["id"] for item in proposal["run"]["proposal"]["actions"]]
        self.client.post(
            "/api/v1/plan/commit",
            json={"action_ids": action_ids, "rationale": "test", "confirmed_by_user": True},
        )
        blocked_review = self.client.post("/api/v1/review", json={"locale": "zh"})
        self.assertEqual(blocked_review.status_code, 409)
        self.assertEqual(blocked_review.json()["error"]["code"], "tracking_missing")


class PromptLocalizationTest(unittest.TestCase):
    def test_region_currency_and_language_are_dynamic(self):
        config = {
            "region": {"name": "Sceaux, France", "climate": "temperate", "currency": "EUR"},
            "tariff": {},
        }
        zh = build_system_prompt(config, "zh")
        en = build_system_prompt(config, "en")
        self.assertIn("Sceaux, France", zh)
        self.assertIn("EUR", zh)
        self.assertIn("temperate", en)
        self.assertNotIn("服务于新加坡", zh)
