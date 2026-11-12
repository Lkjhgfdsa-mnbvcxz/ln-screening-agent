"""Publication gate: no real business datum may reach the public repository.

The gate detects by SHAPE only, so this test file itself must not contain a
literal real-looking identifier.  Suspicious strings are assembled at runtime.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_sensitive  # noqa: E402


class PublicationGateTests(unittest.TestCase):
    def test_working_tree_is_clean(self):
        findings = check_sensitive.scan()
        self.assertEqual(findings, {}, f"public files contain real markers: {findings}")

    def test_gate_rejects_real_shaped_case_id(self):
        fake = "LN" + "20999" + "888777666"
        hits = check_sensitive.find_in_text("case " + fake)
        self.assertTrue(any(reason == "real LN case id" for reason, _ in hits))

    def test_gate_rejects_internal_host(self):
        fake = "boss" + "." + "internal-example" + ".com"
        hits = check_sensitive.find_in_text("url " + fake)
        self.assertTrue(any(reason == "internal host" for reason, _ in hits))

    def test_gate_rejects_provider_secret(self):
        fake = "sk-" + "proj-" + "A" * 24
        hits = check_sensitive.find_in_text("key " + fake)
        self.assertTrue(any(reason == "provider secret" for reason, _ in hits))

    def test_gate_rejects_document_sized_number(self):
        fake = "1" * 18
        hits = check_sensitive.find_in_text("id " + fake)
        self.assertTrue(any("identity" in reason or "credit" in reason
                            for reason, _ in hits))

    def test_gate_rejects_out_of_repo_vocabulary_term(self):
        hits = check_sensitive.find_in_text("subject: Example Person",
                                           vocab=["Example Person"])
        self.assertTrue(any(reason == "local sensitive vocabulary" for reason, _ in hits))

    def test_no_real_case_id_in_any_published_revision(self):
        """History matters: a public repo exposes every old blob."""
        revs = subprocess.check_output(["git", "rev-list", "--all"], cwd=ROOT,
                                       text=True).split()
        self.assertTrue(revs)
        pattern = "LN" + "20[0-9]{9,}"
        # No "--" separator: everything after it would be treated as a PATH,
        # making the historical scan silently a no-op.
        result = subprocess.run(["git", "grep", "-I", "-l", "-E", pattern] + revs,
                                cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1,
                         "a real-shaped case id is present in git history:\n" +
                         result.stdout[:800])

    def test_generated_pages_are_scanned_too(self):
        paths = {p.name for p in check_sensitive.tracked_files()}
        for name in ("demo.html", "replay.html", "index.html",
                     "examples/demo_workbench_data.json"):
            short = name.split("/")[-1]
            self.assertIn(short, paths, f"generated page missing from gate: {name}")


if __name__ == "__main__":
    unittest.main()
