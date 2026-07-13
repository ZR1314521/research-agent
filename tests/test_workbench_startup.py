from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkbenchStartupTests(unittest.TestCase):
    def test_dry_run_shows_loopback_module_invocation_and_frontend_command(self) -> None:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "start_workbench.ps1"), "-DryRun"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-m uvicorn research_agent.app:app --host 127.0.0.1 --port 8877", result.stdout)
        self.assertIn("--prefix", result.stdout)
        self.assertIn("workbench start", result.stdout)


if __name__ == "__main__":
    unittest.main()
