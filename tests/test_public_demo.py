"""Public multi-case workbench demo: safety, shape and reproducibility gates.

`demo.html` is the page a reviewer opens first. It must stay fully synthetic,
self-contained, organised by checklist subject (not a flat event stream), and
it must carry the Qichacha-shaped subject profile with the connector's own
"0 hits != no risk" caveat.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_demo  # noqa: E402

DEMO_JSON = ROOT / "examples" / "demo_workbench_data.json"
DEMO_HTML = ROOT / "demo.html"

FORBIDDEN = ("LN20", "sk-", "ghp_", "github_pat_", "Bearer ",
             "yeepay", "boss.", "merchantNo")
INTERNAL_HOST = re.compile(
    r"boss\.[a-z0-9-]+\.(?:com|cn)|@[a-z0-9-]+\.(?:com|cn)\b",
    re.I,
)


def _payload() -> dict:
    return json.loads(DEMO_JSON.read_text(encoding="utf-8"))


class PublicDemoSafetyTests(unittest.TestCase):
    def test_published_data_is_synthetic_only(self):
        p = _payload()
        blob = json.dumps(p, ensure_ascii=False)
        self.assertEqual(p["schema"], "ln-agent-demo-workbench/1.1")
        for marker in FORBIDDEN:
            self.assertNotIn(marker, blob, f"real-data marker leaked: {marker}")
        self.assertIsNone(INTERNAL_HOST.search(blob), "internal system URL leaked")
        self.assertIsNone(re.search(r"(?<!\d)\d{15,18}(?!\d)", blob),
                          "document-sized number leaked into public demo")
        for case in p["cases"]:
            self.assertTrue(case["case_id"].startswith("SYN-"))
            for hit in case["hits"]:
                self.assertIn("example.org", hit["source_domain"])
                self.assertFalse(hit["source_domain"].startswith("http"))

    def test_shape_matches_the_validated_run(self):
        p = _payload()
        t = p["totals"]
        self.assertEqual((t["cases"], t["hits"], t["workers"]), (8, 154, 4))
        self.assertEqual(sum(c["hit_count"] for c in p["cases"]), 154)
        counts = sorted((c["hit_count"] for c in p["cases"]), reverse=True)
        self.assertEqual(counts[:2], [88, 49], "large parallel checklists missing")
        dist = t["conclusion_distribution"]
        for conclusion in ("命中", "疑似命中", "未命中", "无法确定"):
            self.assertGreater(dist[conclusion], 0, f"missing outcome {conclusion}")
        self.assertEqual(sum(dist.values()), 154)

    def test_checklist_level_view_and_per_hit_progress(self):
        p = _payload()
        for case in p["cases"]:
            self.assertEqual(len(case["hits"]), case["hit_count"])
            for hit in case["hits"]:
                self.assertEqual(len(hit["stages"]), 5)
                self.assertEqual(len(hit["stage_ms"]), 5)
                self.assertTrue(hit["path"])
                self.assertIn(hit["conclusion_status"],
                              ("DRAFT_NOT_APPROVED", "NO_CONCLUSION"))
                self.assertIn(hit["source_domain"], hit["reason"])
                self.assertIn(hit["ln_id"], hit["reason"])
                if hit["conclusion"] == "无法确定":
                    self.assertIn("无法确定", hit["reason"])
                    self.assertNotIn("误报", hit["reason"])
        reasons = [h["reason"] for c in p["cases"] for h in c["hits"]]
        self.assertGreater(len(set(reasons)), 100,
                           "per-hit reasons collapsed into templates again")

    def test_qcc_shaped_profile_and_connector_discipline(self):
        p = _payload()
        for case in p["cases"]:
            prof = case["profile"]
            self.assertTrue(prof["synthetic"])
            self.assertIn("企查查", prof["connector"])
            for tool in ("get_company_profile", "get_company_risk_scan",
                         "get_executive_risk_scan"):
                self.assertIn(tool, prof["tools"])
            self.assertEqual(prof["risk_scan"]["dimensions"],
                             35 if case["entity_type"] == "企业" else 18)
            self.assertIn("未发起实时查询", prof["note"])
            self.assertTrue(prof["display"])
        html = DEMO_HTML.read_text(encoding="utf-8")
        self.assertIn("0 命中仅代表结构化维度当前无记录，不等于主体无风险", html)

    def test_timing_math_is_consistent(self):
        p = _payload()
        for case in p["cases"]:
            engine = round(sum(h["duration_ms"] for h in case["hits"]), 1)
            self.assertAlmostEqual(case["engine_ms"], engine, places=1)
            self.assertAlmostEqual(case["wall_ms"], round(engine / 4, 1), places=1)
            self.assertAlmostEqual(case["mean_ms_per_hit"],
                                   round(engine / case["hit_count"], 1), places=1)
            self.assertGreater(case["speedup"], 3.5)
            for hit in case["hits"]:
                self.assertAlmostEqual(sum(hit["stage_ms"]), hit["duration_ms"],
                                       delta=0.4)
        t = p["totals"]
        self.assertAlmostEqual(t["mean_ms_per_hit"],
                               round(t["engine_ms"] / t["hits"], 1), places=1)
        self.assertLess(t["mean_wall_ms_per_hit"], t["mean_ms_per_hit"],
                        "post-parallel share must be smaller than one hit's cost")

    def test_concurrency_model_starts_all_subjects_together(self):
        p = _payload()
        cc, t = p["concurrency"], p["totals"]
        self.assertTrue(cc["cases_start_together"])
        self.assertEqual(cc["workers_per_case"], 4)
        self.assertEqual(cc["total_workers_if_isolated"], 32)
        self.assertAlmostEqual(t["wall_ms"],
                               max(c["wall_ms"] for c in p["cases"]), places=1)
        self.assertAlmostEqual(t["wall_ms_shared_pool"],
                               round(t["engine_ms"] / 4, 1), places=1)
        self.assertAlmostEqual(t["wall_ms_serial_cases"],
                               round(sum(c["wall_ms"] for c in p["cases"]), 1),
                               places=1)
        # The old bug: treating the post-parallel share as one hit's cost and
        # then dividing by 4 again (double-counted speedup).
        self.assertGreater(t["mean_ms_per_hit"], 300)
        self.assertLess(t["mean_wall_ms_per_hit"], 120)
        self.assertIn("39 轮", cc["why_not_one_hit"])
        html = DEMO_HTML.read_text(encoding="utf-8")
        self.assertIn("同时开始", html)
        self.assertIn("为什么不是", html)
        self.assertIn("总墙钟由最慢的那张单决定", html)

    def test_html_embeds_the_same_data_and_has_no_external_resources(self):
        html = DEMO_HTML.read_text(encoding="utf-8")
        self.assertIn('id="demo-data"', html)
        self.assertNotIn("__DEMO_DATA__", html)
        for pattern in ("<script src=", "<link rel=\"stylesheet\"",
                        "fetch(", "XMLHttpRequest", "<img src=\"http"):
            self.assertNotIn(pattern, html, f"external resource: {pattern}")
        match = re.search(
            r'<script type="application/json" id="demo-data">(.*?)</script>',
            html, re.S)
        self.assertIsNotNone(match)
        embedded = json.loads(match.group(1).replace("<\\/", "</"))
        self.assertEqual(embedded, _payload())

    def test_html_has_subject_cards_detail_view_and_simulation_controls(self):
        html = DEMO_HTML.read_text(encoding="utf-8")
        for needle in ('id="cases"', 'id="detail"', 'id="profile"',
                       'id="runall"', 'id="runcase"', 'id="more"',
                       'location.hash', 'autorun', '4 workers'):
            self.assertIn(needle, html, f"missing demo capability: {needle}")
        self.assertIn("按<strong>工单主体</strong>组织", html)

    def test_generator_is_reproducible(self):
        self.assertEqual(build_demo.build(), _payload())

    def test_demo_owns_the_pages_entry_and_replay_does_not_overwrite_it(self):
        self.assertEqual((ROOT / "index.html").read_text(encoding="utf-8"),
                         build_demo.INDEX_HTML)
        replay_src = (ROOT / "scripts" / "build_replay.py").read_text(encoding="utf-8")
        self.assertNotIn("INDEX_HTML.write_text", replay_src)
        self.assertNotIn("url=replay.html", replay_src)

    def test_sanitizer_rejects_real_markers_and_shape_drift(self):
        p = build_demo.build()
        p["cases"][0]["subject"] = "LN20-SYNTHETIC-LEAK-MARKER"
        with self.assertRaises(RuntimeError):
            build_demo._assert_synthetic(p)
        p = build_demo.build()
        p["totals"]["hits"] = 155
        with self.assertRaises(RuntimeError):
            build_demo._assert_synthetic(p)


if __name__ == "__main__":
    unittest.main()
