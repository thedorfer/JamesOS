#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from jamesos.core.career.models import CareerProfile
from jamesos.core.career.storage import CareerStore
from jamesos.services.application_preparer import ApplicationPreparer
from jamesos.services.job_search import JobSearchService,load_career_profile
from jamesos.config import VAULT

def main():
    parser=argparse.ArgumentParser(description="Local-only job discovery and application preparation")
    parser.add_argument("--profile",type=Path,default=VAULT/"JamesOS"/"Profiles"/"career.json");sub=parser.add_subparsers(dest="command",required=True)
    for name in ("ingest-email","ingest-manual"):
        p=sub.add_parser(name);p.add_argument("--file",type=Path,required=True);p.add_argument("--confirm",action="store_true")
    sub.add_parser("list");show=sub.add_parser("show");show.add_argument("--job-id",required=True)
    rank=sub.add_parser("rank");rank.add_argument("--job-id",required=True)
    short=sub.add_parser("shortlist");short.add_argument("--job-id",required=True);short.add_argument("--confirm",action="store_true")
    prep=sub.add_parser("prepare");prep.add_argument("--job-id",required=True);prep.add_argument("--resume-reference");prep.add_argument("--confirm",action="store_true")
    review=sub.add_parser("review");review.add_argument("--application-id",required=True)
    approve=sub.add_parser("approve");approve.add_argument("--application-id",required=True);approve.add_argument("--proposal-sha256",required=True);approve.add_argument("--confirm",action="store_true")
    submitted=sub.add_parser("mark-submitted");submitted.add_argument("--application-id",required=True);submitted.add_argument("--confirm",action="store_true")
    report=sub.add_parser("report");report.add_argument("--confirm",action="store_true")
    args=parser.parse_args();profile=load_career_profile(args.profile);store=CareerStore();jobs=JobSearchService(store,profile);apps=ApplicationPreparer(store,profile)
    if args.command=="ingest-email":result=jobs.ingest_email(args.file,confirmed=args.confirm)
    elif args.command=="ingest-manual":result=jobs.ingest_manual(args.file,confirmed=args.confirm)
    elif args.command=="list":result={"jobs":[x.to_dict() for x in store.list_jobs()]}
    elif args.command=="show":result=store.get_job(args.job_id).to_dict()
    elif args.command=="rank":result=jobs.rank(args.job_id)
    elif args.command=="shortlist":result=jobs.shortlist(args.job_id,confirmed=args.confirm)
    elif args.command=="prepare":result=apps.prepare(args.job_id,confirmed=args.confirm,resume_reference=args.resume_reference)
    elif args.command=="review":result=apps.review(args.application_id)
    elif args.command=="approve":result=apps.approve(args.application_id,args.proposal_sha256,confirmed=args.confirm)
    elif args.command=="mark-submitted":result=apps.mark_submitted(args.application_id,confirmed=args.confirm)
    else:result=jobs.report(write=args.confirm)
    print(json.dumps(result,indent=2,default=str));return 0
if __name__=="__main__":raise SystemExit(main())
