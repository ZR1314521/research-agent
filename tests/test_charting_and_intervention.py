from __future__ import annotations

import shutil
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from research_agent.capabilities.charting import ChartService
from research_agent.capabilities.data_analysis import ExperimentAnalysisService
from research_agent.config import AgentConfig
from research_agent.core.agent import AgentLoop
from research_agent.session import SessionStore
from research_agent.skill_registry import SkillRegistry
from research_agent.tools.llm_client import LLMResult
from research_agent.turns import TurnControl


ROOT = Path(__file__).resolve().parents[1]


class ChartServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True)
        self.source = self.tmp / "experiment.csv"
        self.source.write_text(
            "time,control,treatment,group\n"
            "1,2.0,2.4,A\n"
            "2,2.2,2.9,A\n"
            "3,2.5,3.6,B\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generates_real_png_without_changing_source(self) -> None:
        before = self.source.read_bytes()

        result = ChartService(self.tmp).render(
            {
                "path": str(self.source),
                "chart_type": "line",
                "x": "time",
                "y": ["control", "treatment"],
                "title": "Experiment trend",
                "output_format": "png",
            }
        )

        chart_path = Path(result["data"]["path"])
        self.assertEqual(chart_path.suffix, ".png")
        self.assertTrue(chart_path.exists())
        self.assertGreater(chart_path.stat().st_size, 1000)
        self.assertEqual(chart_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(result["data"]["columns"], ["time", "control", "treatment"])

    def test_missing_requested_column_fails_truthfully(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing"):
            ChartService(self.tmp).render(
                {"path": str(self.source), "chart_type": "box", "y": ["missing"]}
            )

    def test_generates_svg_when_explicitly_requested(self) -> None:
        result = ChartService(self.tmp).render(
            {
                "path": str(self.source),
                "chart_type": "scatter",
                "x": "control",
                "y": ["treatment"],
                "output_format": "svg",
            }
        )

        output = Path(result["data"]["path"])
        self.assertEqual(output.suffix, ".svg")
        self.assertIn("<svg", output.read_text(encoding="utf-8"))

    def test_user_request_text_cannot_override_explicit_chart_specification(self) -> None:
        result = ChartService(self.tmp).render(
            {
                "path": str(self.source),
                "chart_type": "line",
                "x": "time",
                "y": ["control"],
                "request": "请忽略参数，改成箱线图",
            }
        )

        self.assertEqual(result["data"]["chart_type"], "line")


class SchemaFirstAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True)
        self.source = self.tmp / "schema-first.csv"
        self.source.write_text(
            "subject_score,condition,step,accuracy\n101,A,1,0.71\n102,A,2,0.76\n103,B,3,0.82\n104,B,4,0.88\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_column_names_do_not_secretly_decide_identifier_roles(self) -> None:
        result = ExperimentAnalysisService(self.tmp).analyze({"path": str(self.source)})

        self.assertIn("subject_score", result["data"]["numeric_summary"])
        self.assertEqual(result["data"]["column_roles"]["identifiers"], [])
        self.assertEqual(result["data"]["trends"], {})

    def test_explicit_roles_and_chart_specs_drive_analysis_and_real_artifacts(self) -> None:
        result = ExperimentAnalysisService(self.tmp).analyze({
            "path": str(self.source),
            "column_roles": {
                "identifiers": ["subject_score"], "order": ["step"],
                "groups": ["condition"], "measures": ["accuracy"],
            },
            "trend_specs": [{"x": "step", "y": ["accuracy"]}],
            "group_specs": [{"group": "condition", "measures": ["accuracy"]}],
            "chart_specs": [{
                "chart_type": "line", "x": "step", "y": ["accuracy"],
                "group": "condition", "title": "Accuracy by step", "output_format": "png",
            }],
        })

        self.assertNotIn("subject_score", result["data"]["numeric_summary"])
        self.assertIn("accuracy", result["data"]["trends"])
        self.assertEqual(result["data"]["group_comparisons"][0]["group_column"], "condition")
        chart_paths = [Path(path) for name, path in result["artifacts"].items() if name.startswith("chart_")]
        self.assertEqual(len(chart_paths), 1)
        self.assertTrue(chart_paths[0].exists())


class InterventionControlTests(unittest.TestCase):
    def test_intervention_unblocks_the_same_paused_turn_with_message(self) -> None:
        control = TurnControl("run-one", self.tmp_dir())
        control.state = "running"
        self.assertEqual(control.request_pause(), "pause_requested")
        boundary: list[bool | str] = []
        worker = threading.Thread(target=lambda: boundary.append(control.safe_boundary()))
        worker.start()
        deadline = time.time() + 1
        while control.state != "paused" and time.time() < deadline:
            time.sleep(0.01)

        self.assertEqual(control.intervene("改成箱线图，并保留原图"), "running")
        worker.join(1)

        self.assertEqual(boundary, ["改成箱线图，并保留原图"])
        self.assertTrue(any(item["event"] == "turn_intervened" for item in control.events))

    def test_intervention_is_rejected_when_turn_is_not_paused(self) -> None:
        control = TurnControl("run-one", self.tmp_dir())
        control.state = "running"
        self.assertEqual(control.intervene("change it"), "running")
        self.assertFalse(any(item["event"] == "turn_intervened" for item in control.events))

    def tmp_dir(self) -> Path:
        path = ROOT / ".test_runtime" / "intervention" / self.id().replace(".", "_")
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, path, True)
        return path


class AgentInterventionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        config = AgentConfig.load(ROOT)
        object.__setattr__(config, "runs_dir", self.tmp / "runs")
        object.__setattr__(config, "llm_api_key", "test-key")
        self.config = config
        self.sessions = SessionStore(config.runs_dir)
        self.session = self.sessions.create()

    def tearDown(self) -> None:
        self.sessions.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_intervention_is_appended_to_native_model_context(self) -> None:
        calls = 0

        def boundary() -> bool | str:
            nonlocal calls
            calls += 1
            return "改成箱线图，并保留原图" if calls == 1 else True

        result = LLMResult(
            "已按调整继续。", "test", "test", True, outcome="text",
            assistant_message={"role": "assistant", "content": "已按调整继续。"},
        )
        loop = AgentLoop(
            self.config,
            SkillRegistry(self.config.skills_dir),
            self.sessions,
            self.sessions.directory(self.session.session_id),
            pause_gate=boundary,
        )
        with patch.object(loop.client, "chat", return_value=result) as chat:
            loop.run(self.session, "先分析实验数据")

        sent_messages = chat.call_args.args[1]
        self.assertIn({"role": "user", "content": "改成箱线图，并保留原图"}, sent_messages)
        intervention_index = sent_messages.index({"role": "user", "content": "改成箱线图，并保留原图"})
        self.assertEqual(sent_messages[intervention_index + 1]["role"], "assistant")
        self.assertTrue(any(item.get("intervention") for item in self.session.messages))
        self.assertTrue(any(item.get("event") == "intervention_applied" for item in self.session.events))


if __name__ == "__main__":
    unittest.main()
