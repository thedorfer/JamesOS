from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jamesos.services.creative_studio import (
    approve_creative_job,
    create_sample_image_job,
    create_sample_product_job,
    fail_creative_job,
    get_creative_job,
    health,
    list_creative_jobs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Jade Creative Studio")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    sub.add_parser("create-sample-image-job")
    sub.add_parser("create-sample-product-job")
    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--status")

    show = sub.add_parser("show")
    show.add_argument("job_id")

    approve = sub.add_parser("approve")
    approve.add_argument("job_id")

    fail = sub.add_parser("fail")
    fail.add_argument("job_id")
    fail.add_argument("reason", nargs="?", default="")

    args = parser.parse_args()

    if args.command == "health":
        result = health()
    elif args.command == "create-sample-image-job":
        result = create_sample_image_job()
    elif args.command == "create-sample-product-job":
        result = create_sample_product_job()
    elif args.command == "list":
        result = list_creative_jobs(args.status)
    elif args.command == "show":
        result = get_creative_job(args.job_id)
    elif args.command == "approve":
        result = approve_creative_job(args.job_id)
    else:
        result = fail_creative_job(args.job_id, args.reason)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
