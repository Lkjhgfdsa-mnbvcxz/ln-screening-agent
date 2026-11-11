"""Public replay safety + reproducibility regressions.

The static replay is the only execution artifact that is published. These tests
make sure it can never carry real business data, external resources or
forbidden automatic actions, and that its embedded event stream still matches
what the engine actually emits.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_replay  # noqa: E402

REPLAY_JSON = ROOT / "examples" / "workbuddy_capture_replay.json"
REPLAY_HTML = ROOT / "replay.html"
INDEX_HTML = ROOT / "index.html"

FORBIDDEN = ("LN20", "sk-", "ghp_", "github_pat_", "Bearer ")
INTERNAL_HOST = re.compile(
    r"boss\.[a-z0-9-]+\.(?:com|cn)|@[a-z0-9-]+\.(?:com|cn)\b",
    re.I,
)


def _payload() -> dict:
    return json.loads(REPLAY_JSON.read_text(encoding="utf-8"))


class PublicReplaySafetyTests(unittest.TestCase):
    def test_replay_json_is_synthetic_only(self):
        p = _payload()
        blob = json.dumps(p, ensure_ascii=False)
        self.assertEqual(p["schema"], "ln-agent-replay/1.0")
        self.assertTrue(p["case"]["case_id"].startswith("SYN-"))
        self.assertEqual(p["case"]["hits"], 3)
        self.assertGreaterEqual(p["execution"]["event_count"], 60)
        for marker in FORBIDDEN:
            self.assertNotIn(marker, blob, f"real-data marker leaked: {marker}")
        self.assertIsNone(INTERNAL_HOST.search(blob), "internal system URL leaked")
        self.assertIsNone(re.search(r"(?<!\d)\d{15,18}(?!\d)", blob),
                          "document-sized number leaked into public replay")
        for match in re.findall(r'"source_url"\s*:\s*"([^"]+)"', blob):
            self.assertTrue(match.startswith("synthetic://"))

    def test_replay_never_contains_automatic_actions(self):
        p = _payload()
        for hit in p["hits"]:
            self.assertFalse(hit["automatically_sent"])
            self.assertFalse(hit["automatically_cleared"])
            self.assertFalse(hit["manual_queue_required"])
            self.assertIn(hit["business_conclusion_status"],
                          ("DRAFT_NOT_APPROVED", "NO_CONCLUSION"))
        self.assertEqual(p["execution"]["stats"]["manual_queue_tasks"], 0)

    def test_model_facts_stay_unchecked_in_published_evidence(self):
        p = _payload()
        model_facts = [f for hit in p["hits"] for f in hit["research_facts"]
                       if f.get("origin") == "model_extracted"]
        self.assertTrue(model_facts, "synthetic replay should exercise the LLM tool")
        for fact in model_facts:
            self.assertFalse(fact.get("checked", True))

    def test_html_embeds_the_same_data_and_loads_no_external_resource(self):
        html = REPLAY_HTML.read_text(encoding="utf-8")
        self.assertIn('id="replay-data"', html)
        self.assertNotIn("__REPLAY_DATA__", html)
        for pattern in ("<script src=", "<link rel=\"stylesheet\"",
                        "fetch(", "XMLHttpRequest", "<img src=\"http"):
            self.assertNotIn(pattern, html, f"external resource: {pattern}")
        match = re.search(
            r'<script type="application/json" id="replay-data">(.*?)</script>',
            html, re.S)
        self.assertIsNotNone(match)
        embedded = json.loads(match.group(1).replace("<\\/", "</"))
        self.assertEqual(embedded, _payload())

    def test_pages_entry_redirects_to_the_replay(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn("url=replay.html", html)
        self.assertIn('href="replay.html"', html)
        self.assertFalse((ROOT / "docs" / "replay.html").exists(),
                         "stale duplicate replay page must not be published")

    def test_sanitizer_rejects_real_markers(self):
        p = _payload()
        p["case"]["notes"] = "LN20-SYNTHETIC-LEAK-MARKER"
        with self.assertRaises(RuntimeError):
            build_replay._assert_synthetic(p)

    def test_sanitizer_rejects_automatic_send(self):
        p = _payload()
        p["hits"][0]["automatically_sent"] = True
        with self.assertRaises(RuntimeError):
            build_replay._assert_synthetic(p)

    def test_embedded_events_match_a_fresh_engine_run(self):
        p = _payload()
        _, fresh = build_replay._run_case()
        published = Counter((e["kind"], e["hit_id"])
                            for e in p["execution"]["events"])
        generated = Counter((e["kind"], e["hit_id"]) for e in fresh)
        self.assertEqual(published, generated)
        self.assertEqual(len(fresh), p["execution"]["event_count"])

    def test_published_aggregates_contain_no_business_fields(self):
        agg = _payload()["validation"]["authorized_local_aggregates"]
        self.assertEqual(set(agg) & {"case_ids", "names", "urls", "logs"}, set())
        self.assertEqual(agg["manual_queue_tasks"], 0)
        self.assertEqual(agg["automatic_sends"], 0)


if __name__ == "__main__":
    unittest.main()
