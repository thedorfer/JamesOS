#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from jamesos.core.agent_manager import AgentManager
def main():
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("list");info=commands.add_parser("info");info.add_argument("agent_id");install=commands.add_parser("install");install.add_argument("path");install.add_argument("--confirm-install",action="store_true")
    remove=commands.add_parser("remove");remove.add_argument("agent_id");remove.add_argument("--confirm-remove",action="store_true")
    enable=commands.add_parser("enable");enable.add_argument("agent_id");enable.add_argument("--confirm-enable",action="store_true")
    disable=commands.add_parser("disable");disable.add_argument("agent_id");disable.add_argument("--confirm-disable",action="store_true")
    doctor=commands.add_parser("doctor");doctor.add_argument("agent_id");permissions=commands.add_parser("permissions");permissions.add_argument("agent_id")
    args=parser.parse_args();manager=AgentManager()
    if args.command=="list":result={"agents":manager.list()}
    elif args.command=="info":result=manager.info(args.agent_id)
    elif args.command=="install":result=manager.install(args.path,args.confirm_install)
    elif args.command=="remove":result=manager.remove(args.agent_id,args.confirm_remove)
    elif args.command=="enable":result=manager.set_enabled(args.agent_id,True,args.confirm_enable)
    elif args.command=="disable":result=manager.set_enabled(args.agent_id,False,args.confirm_disable)
    elif args.command=="permissions":result=manager.permissions(args.agent_id,manager.manifest_for(args.agent_id))
    else:result=manager.doctor(args.agent_id,manager.manifest_for(args.agent_id))
    print(json.dumps(result,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
