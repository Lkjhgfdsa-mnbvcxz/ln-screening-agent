"""Usage: python run.py examples/demo_case.json --research examples/research_fixtures.json"""
import argparse
import json
from pathlib import Path
from ln_agent import Case, Policy, Orchestrator, FixtureResearchTool


def main():
    p = argparse.ArgumentParser(description="LN dynamic route agent: OFFLINE / READ-ONLY")
    p.add_argument("case", help="A synthetic case JSON path")
    p.add_argument("--research", default="", help="Mock source facts JSON path")
    p.add_argument("--out", default="", help="Optional result JSON path")
    args = p.parse_args()
    raw = json.loads(Path(args.case).read_text(encoding="utf-8"))
    fixture = json.loads(Path(args.research).read_text(encoding="utf-8")) if args.research else {}
    report = Orchestrator(Policy(), FixtureResearchTool(fixture)).run(Case.from_dict(raw))
    data = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(data + "\n", encoding="utf-8")
    print(data)

if __name__ == "__main__":
    main()
