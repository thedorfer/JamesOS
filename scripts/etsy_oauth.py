#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from jamesos.integrations import etsy_oauth
def _main():
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest="command",required=True);commands.add_parser("start");complete=commands.add_parser("complete");complete.add_argument("--callback-url",required=True);commands.add_parser("status");args=parser.parse_args()
    result=etsy_oauth.start() if args.command=="start" else etsy_oauth.complete(args.callback_url) if args.command=="complete" else etsy_oauth.status();print(json.dumps(result,indent=2));return 0
if __name__=="__main__":raise SystemExit(_main())
