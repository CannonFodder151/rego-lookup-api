"""Repo-wide guard: every GitHub Actions workflow must parse strictly.

GitHub silently drops a workflow file containing a duplicate mapping key —
no check-run is created and the file still looks present on main (AUT-4776).
This covers every workflow in the repo, not just security-scan.yml.

Run: python3 tests/test_workflow_lint.py
"""

import unittest
from pathlib import Path

import yaml

from test_security_scan_workflow import StrictLoader

REPO = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO / ".github/workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.y*ml"))


class WorkflowLintTest(unittest.TestCase):
    def test_workflows_exist(self):
        self.assertTrue(WORKFLOWS, "no workflow files found")

    def test_every_workflow_parses_without_duplicate_keys(self):
        for path in WORKFLOWS:
            with self.subTest(workflow=path.name):
                doc = yaml.load(path.read_text(), Loader=StrictLoader)
                self.assertIsInstance(doc, dict)
                self.assertIn("jobs", doc)
                self.assertTrue(doc["jobs"], f"{path.name}: empty jobs map")


if __name__ == "__main__":
    import sys

    result = unittest.main(argv=[sys.argv[0], "-v"], exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)