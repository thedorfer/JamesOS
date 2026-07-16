#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from jamesos.core.agent_manager.package import inspect_package
def main():
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest="command",required=True)
    for name in ("validate","test","pack-plan"):item=commands.add_parser(name);item.add_argument("path")
    args=parser.parse_args();inspection=inspect_package(args.path)
    if args.command=="validate":result={"result":"agent_manifest_valid","agent_id":inspection.manifest.agent_id,"code_executed":False}
    elif args.command=="test":result={"result":"agent_conformance_test_plan","agent_id":inspection.manifest.agent_id,"command":f"python -m unittest discover {Path(args.path).resolve()}","test_executed":False}
    else:result={"result":"agent_pack_plan","agent_id":inspection.manifest.agent_id,"command":f"python -m build {Path(args.path).resolve()}","package_built":False,"package_published":False}
    print(json.dumps(result,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())

