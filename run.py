"""LN Intelligent Screening Agent – offline CLI; synthetic data only.

Quick demo: python3 run.py demo
Custom JSON: python3 run.py examples/demo_case.json --research examples/research_fixtures.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ln_agent import Case, Policy, Orchestrator, FixtureResearchTool


def main() -> None:
    parser = argparse.ArgumentParser(description="LN screening agent | SYNTHETIC, OFFLINE, READ-ONLY")
    parser.add_argument("case", nargs="?", default="demo", help="'demo', 'inspect', or input case JSON")
    parser.add_argument("--research", default="", help="Mock research fixture JSON")
    parser.add_argument("--out", default="", help="Optional output report JSON path")
    parser.add_argument("--port", type=int, default=8765, help="Local workbench port (web mode)")
    args = parser.parse_args()

    if args.case == "llm-status":
        from ln_agent.llm_adapter import LLMConfig
        print(json.dumps(LLMConfig.from_env().status(),ensure_ascii=False,indent=2))
        return

    if args.case == "web":
        from ln_agent.workbench.server import serve
        serve(port=args.port)
        return
    if args.case == "inspect":
        from ln_agent.skill_catalog import PRIMARY, ADDITIONAL, load_skill
        from ln_agent.tool_catalog import tool_status
        print("AGENT ROLES: Orchestrator | DecisionRouter | InvestigationAgent | SuspicionAgent")
        print("SKILLS (loaded from skills/*/contract.json):")
        for name in list(PRIMARY.values()) + sorted(ADDITIONAL):
            info = load_skill(name)
            print(f"  {name:<24} {info['id']}")
        print("TOOLS (live availability):")
        for name, status in tool_status().items():
            print(f"  {name:<24} {status}")
        return

    if args.case == "demo":
        if args.research:
            parser.error("--research is for a custom case; omit it for demo")
        from scripts.run_two_cases import run_pair
        output = run_pair()
        for label, item in output["cases"].items():
            decision = item["report"]["results"][0]
            print(f"{label}: {decision['route']} | report_draft={decision['disposition']['report_recommended']} "
                  f"| manual_queue={decision['disposition']['manual_queue_required']}")
        print("PASS: two synthetic offline cases")
        out = Path(args.out) if args.out else None
    else:
        case = Case.from_dict(json.loads(Path(args.case).read_text(encoding="utf-8")))
        fixture = (json.loads(Path(args.research).read_text(encoding="utf-8"))
                   if args.research else {})
        output = Orchestrator(Policy(), FixtureResearchTool(fixture)).run(case)
        out = Path(args.out) if args.out else None
        if out is None:
            print(json.dumps(output, ensure_ascii=False, indent=2))

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Report: {out}")


if __name__ == "__main__":
    main()
