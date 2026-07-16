#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from jamesos.core.profiles.migration import unitystitches_migration_plan
from jamesos.core.profiles.store import ProfileStore
def main():
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("list");show=commands.add_parser("show");show.add_argument("profile_id");commands.add_parser("plan-migrate-unitystitches")
    apply=commands.add_parser("apply-migrate-unitystitches");apply.add_argument("--confirm-profile-migration",action="store_true")
    args=parser.parse_args();store=ProfileStore()
    if args.command=="list":result={"profiles":[item.to_dict() for item in store.list()]}
    elif args.command=="show":result=store.get(args.profile_id).to_dict()
    else:
        profile=unitystitches_migration_plan();confirmed=args.command=="apply-migrate-unitystitches" and args.confirm_profile_migration
        path=store.save(profile) if confirmed else None;result={"result":"profile_migration_applied" if confirmed else "profile_migration_plan","dry_run":not confirmed,"write_performed":confirmed,"profile":profile.to_dict(),"profile_path":str(path) if path else None,"remote_write_performed":False}
    print(json.dumps(result,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())

