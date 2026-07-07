#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from jamesos.services.image_worker import create_test_image_job


def main() -> None:
    parser = argparse.ArgumentParser(description="Create one approval-gated local ComfyUI test image job. Does not execute.")
    parser.add_argument("--positive-prompt", default="UnityStitches inclusive pride product art, clean bold typography, print ready design")
    parser.add_argument("--negative-prompt", default="copyrighted logos, trademarked characters, hateful symbols, explicit content, watermark, blurry, misspelled text")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--brand-id", default="unitystitches")
    parser.add_argument("--draft-path", default="")
    args = parser.parse_args()

    result = create_test_image_job(
        positive_prompt=args.positive_prompt,
        negative_prompt=args.negative_prompt,
        seed=args.seed,
        width=args.width,
        height=args.height,
        brand_id=args.brand_id,
        draft_path=args.draft_path,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
