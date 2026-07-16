from __future__ import annotations

import json
import shutil
import unittest
from threading import Event
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_agent.capabilities.papers import PaperAcquisitionService
from research_agent.capabilities.references import ReferenceService
from research_agent.capabilities.documents import DocumentService
from research_agent.session import ChatSession, SessionStore
from research_agent.capabilities.workspace import WorkspaceService
from research_agent.config import AgentConfig
from research_agent.logging import ModelCallLogger
from research_agent.tools.llm_client import LLMClient


ROOT = Path(__file__).resolve().parents[1]


class RuntimeHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_project_env_is_authoritative_and_legacy_aliases_are_ignored(self) -> None:
        (self.tmp / ".env").write_text(
            "RESEARCH_AGENT_LLM_PROVIDER=provider\nRESEARCH_AGENT_LLM_MODEL=model\nRESEARCH_AGENT_LLM_BASE_URL=https://example.test/v1\nRESEARCH_AGENT_LLM_API_KEY=key\nMODEL_NAME=ignored\n",
            encoding="utf-8",
        )
        config = AgentConfig.load(self.tmp)
        self.assertEqual(config.llm_model, "model")
        self.assertTrue(config.llm_configured)

    def test_model_operations_share_provider_config_instead_of_static_budgets(self) -> None:
        config = AgentConfig.load(self.tmp)
        self.assertEqual(config.llm_retry, 0)
        self.assertEqual(config.llm_max_tokens, 0)
        self.assertFalse(hasattr(__import__("research_agent.tools.llm_client", fromlist=["OPERATION_BUDGETS"]), "OPERATION_BUDGETS"))

    def test_structured_model_safety_envelope_is_configurable(self) -> None:
        (self.tmp / ".env").write_text(
            "RESEARCH_AGENT_STRUCTURED_LLM_TIMEOUT=73\n"
            "RESEARCH_AGENT_STRUCTURED_LLM_MAX_TOKENS=2048\n"
            "RESEARCH_AGENT_STRUCTURED_LLM_RETRY=2\n"
            "RESEARCH_AGENT_LITERATURE_MAX_BATCH_QUERIES=3\n"
            "RESEARCH_AGENT_LITERATURE_SCREENING_LIMIT=17\n",
            encoding="utf-8",
        )
        config = AgentConfig.load(self.tmp)
        self.assertEqual(config.structured_llm_timeout_seconds, 73)
        self.assertEqual(config.structured_llm_max_tokens, 2048)
        self.assertEqual(config.structured_llm_retry, 2)
        self.assertEqual(config.literature_max_batch_queries, 3)
        self.assertEqual(config.literature_screening_limit, 17)

    def test_pre_cancelled_model_call_never_touches_network(self) -> None:
        event = Event()
        event.set()
        result = LLMClient(AgentConfig.load(ROOT), ModelCallLogger(self.tmp), event).complete("agent_decision", "hello")
        self.assertEqual(result.error, "cancelled")
        self.assertFalse(result.used_remote_model)

    def test_workspace_delete_requires_confirmation_and_is_reversible(self) -> None:
        source = self.tmp / "source.txt"
        source.write_text("keep", encoding="utf-8")
        service = WorkspaceService(self.tmp, self.tmp / "session")
        with self.assertRaises(ValueError):
            service.operate({"operation": "delete", "path": "source.txt"})
        result = service.operate({"operation": "delete", "path": "source.txt", "confirmed": True})
        self.assertFalse(source.exists())
        self.assertTrue(Path(result["artifacts"]["recycled_file"]).exists())

    def test_open_access_download_rejects_non_pdf(self) -> None:
        papers = self.tmp / "papers.json"
        papers.write_text(json.dumps([{"title": "A", "doi": "10.1/x", "open_access_url": "https://example.test/a"}]), encoding="utf-8")

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, _limit): return b"not a pdf"

        with patch("urllib.request.urlopen", return_value=Response()):
            result = PaperAcquisitionService(self.tmp / "session").acquire({}, str(papers))
        record = result["data"]["records"][0]
        self.assertEqual(record["status"], "not_downloaded")
        self.assertIn("response_is_not_a_pdf", record["error"])

    def test_iop_profile_generates_a_reference_file(self) -> None:
        source = self.tmp / "refs.bib"
        source.write_text("@article{x, author={A Author}, title={A title}, journal={Journal}, year={2024}, doi={10.1/example}}", encoding="utf-8")
        service = ReferenceService(AgentConfig.load(ROOT), self.tmp / "session")
        service.session_dir.mkdir()
        result = service.format({"path": str(source), "styles": ["iop"], "output_mode": "list"}, {})
        output = Path(result["artifacts"]["references_iop"])
        self.assertTrue(output.exists())
        self.assertIn("IOP Publishing", output.read_text(encoding="utf-8"))

    def test_markdown_to_docx_creates_report_and_import_copy(self) -> None:
        source = self.tmp / "source.md"
        source.write_text("# Title\n\n| A | B |\n|---|---|\n| 1 | 2 |", encoding="utf-8")
        result = DocumentService(self.tmp / "session").convert({"path": str(source), "target_format": "docx"}, {})
        self.assertTrue(Path(result["artifacts"]["converted_document"]).exists())
        self.assertTrue(Path(result["artifacts"]["conversion_report"]).exists())
        reverse = DocumentService(self.tmp / "session").convert({"path": result["artifacts"]["converted_document"], "target_format": "markdown"}, {})
        self.assertTrue(Path(reverse["artifacts"]["converted_document"]).exists())

    def test_document_convert_accepts_md_alias(self) -> None:
        source = self.tmp / "source.docx"
        source.write_bytes(b"placeholder")
        service = DocumentService(self.tmp / "session")

        def convert(command, **_kwargs):
            Path(command[3]).write_text("# Converted", encoding="utf-8")
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        with patch.object(service, "_pandoc", return_value=self.tmp / "pandoc"), patch(
            "research_agent.capabilities.documents.subprocess.run", side_effect=convert
        ):
            result = service.convert({"path": str(source), "target_format": "md"}, {})

        self.assertEqual(result["data"]["target_format"], "markdown")
        self.assertEqual(Path(result["artifacts"]["converted_document"]).suffix, ".md")

    def test_reset_context_keeps_files_but_removes_artifact_references(self) -> None:
        store = SessionStore(self.tmp / "runs")
        self.addCleanup(store.close)
        session = store.create()
        file = store.directory(session.session_id) / "keep.txt"
        file.write_text("keep", encoding="utf-8")
        session.artifacts["keep"] = str(file); session.goal = "old"; session.add_message("user", "old")
        store.reset_context(session)
        self.assertTrue(file.exists())
        self.assertFalse(session.artifacts); self.assertFalse(session.messages); self.assertEqual(session.goal, "")

    def test_save_retries_a_transient_session_file_lock(self) -> None:
        store = SessionStore(self.tmp / "runs")
        self.addCleanup(store.close)
        session = store.create()
        session.metadata["saved"] = "after-lock"
        original_replace = Path.replace
        attempts = 0

        def transient_replace(source: Path, target: Path) -> Path:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise PermissionError("session file locked")
            return original_replace(source, target)

        with patch.object(Path, "replace", autospec=True, side_effect=transient_replace), patch(
            "research_agent.session.time.sleep"
        ) as sleep:
            path = store.save(session)

        self.assertEqual(attempts, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["metadata"]["saved"], "after-lock")

    def test_save_raises_and_keeps_existing_session_for_a_persistent_lock(self) -> None:
        store = SessionStore(self.tmp / "runs")
        self.addCleanup(store.close)
        session = store.create()
        path = store.directory(session.session_id) / "session.json"
        original_payload = path.read_text(encoding="utf-8")
        session.metadata["saved"] = "blocked"
        lock_error = PermissionError("session file remains locked")

        with patch.object(Path, "replace", autospec=True, side_effect=lock_error), patch(
            "research_agent.session.time.sleep"
        ) as sleep, self.assertRaises(PermissionError) as raised:
            store.save(session)

        self.assertIs(raised.exception, lock_error)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(path.read_text(encoding="utf-8"), original_payload)


if __name__ == "__main__":
    unittest.main()
