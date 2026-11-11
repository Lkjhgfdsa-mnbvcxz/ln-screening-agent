"""Local document mode. No network / LN system access / automatic dispositions.

python run_documents.py examples/document_case.json examples/document_manifest.json --out document_report.json
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from ln_agent import Case,Policy,Orchestrator
from ln_agent.document_tools import DocumentFixtureResearchTool

def load_manifest(manifest_path:Path)->dict:
    root=manifest_path.resolve().parent
    config=json.loads(manifest_path.read_text(encoding="utf-8"))
    result={}
    for item in config["documents"]:
        docid=item["id"]
        if docid in result:raise ValueError(f"duplicate document ID: {docid}")
        resolved=(root/item["file"]).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("document path escapes manifest directory")
        if not resolved.is_file():raise FileNotFoundError(resolved)
        if resolved.stat().st_size>10*1024*1024:raise ValueError("document too large")
        result[docid]={**item,"data":resolved.read_bytes()}
    return result

def main():
    p=argparse.ArgumentParser(description="LN OFFLINE document intelligence + dynamic router")
    p.add_argument("case",type=Path)
    p.add_argument("manifest",type=Path)
    p.add_argument("--out",type=Path,default=None)
    args=p.parse_args()
    case=Case.from_dict(json.loads(args.case.read_text(encoding="utf-8")))
    tool=DocumentFixtureResearchTool(load_manifest(args.manifest))
    report=Orchestrator(Policy(),tool).run(case)
    result=json.dumps(report,ensure_ascii=False,indent=2)
    if args.out:args.out.write_text(result+"\n",encoding="utf-8")
    print(result)

if __name__=="__main__":main()
