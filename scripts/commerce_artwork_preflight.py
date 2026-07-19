from __future__ import annotations

import argparse
import json
from pathlib import Path

from jamesos.core.profiles.selection import load_commerce_profile_by_id
from jamesos.services.commerce_artwork import render_typography_candidates


def main()->int:
    parser=argparse.ArgumentParser(description="Generate and validate private local typography artwork without provider contact.")
    parser.add_argument("--profile",required=True);parser.add_argument("--phrase-file",type=Path,required=True);parser.add_argument("--local-only",action="store_true",required=True)
    args=parser.parse_args();phrase=args.phrase_file.read_text(encoding="utf-8");profile=load_commerce_profile_by_id(args.profile,required=True)
    result=render_typography_candidates(phrase=phrase,profile=profile)
    safe={key:result[key] for key in ("generation_backend","decorative_generation_performed","exact_phrase","candidate_count","selected_candidate_id","candidates","publication_state","order_state")}
    for row in safe["candidates"]:row.pop("sha256",None)
    print(json.dumps(safe,indent=2));return 0 if all(item["eligible"] for item in result["candidates"]) else 1


if __name__=="__main__":raise SystemExit(main())
