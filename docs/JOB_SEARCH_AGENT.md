# Job Search Agent

Phase 1 is a provider-neutral, local-only system for job discovery ingestion, normalization, deduplication, ranking, shortlisting, and application preparation. It does not fetch job URLs or submit applications.

## Architecture

`CareerAgent` exposes Agent OS capabilities for ingestion, reading, ranking, shortlisting, preparation, review, approval, and manually recording submission. Reusable logic lives in `job_ingestion`, `job_search`, `job_ranking`, and `application_preparer`; durable JSON records use `CareerStore`.

`career.application.submit` is intentionally absent and unsupported.

## Sources and adapters

- `EmailJobAlertAdapter` parses local LinkedIn, Indeed, Dice, Monster, recruiter, and employer email text.
- `ManualJobAdapter` accepts pasted text, local text/JSON files, or URL metadata without fetching URLs.
- `EmployerCareerAdapter` is an abstract read-only fixture interface.
- `GenericATSAdapter` normalizes supplied Greenhouse, Lever, Workday, or similar records without live requests.

Imported descriptions are untrusted data. Text resembling instructions cannot invoke tools or change policy.

## Storage

Production paths resolve below `~/JamesOSData/JamesOS/Career` with `inbox`, `jobs`, `applications`, `evidence`, `reports`, and `archive` sections. Directories are created only on an explicit confirmed local write. Tests redirect the root to temporary directories.

## Private profile

Career profiles are JSON files under `~/JamesOSData/JamesOS/Profiles`. The schema supports titles, locations, work settings, compensation, employment types, industries, required/preferred technologies, exclusions, sponsorship/work authorization facts, clearance, relocation, travel, resume references, truthful reusable answers, daily limits, and approval mode. The repository contains only `examples/career_profile.example.json` with fake values.

## Normalization, duplicates, and ranking

Normalized records contain source identity, canonical URL, job details, evidence hashes, duplicate groups, status, and timestamps. Tracking parameters are removed from URLs. Exact URL/source IDs/content hashes identify exact duplicates. Identity fields and conservative text similarity produce uncertain matches, which are retained for human review rather than silently merged.

Ranking is deterministic and explains title, skills, seniority, location, work setting, compensation, employment type, recency, blockers, uncertainty, evidence, and missing information. Technologies are profile data, never private hard-coded experience.

## Application proposals and approval

Preparation records the job, match analysis, only profile-supported strengths, resume reference/hash, drafts, answers, unanswered sensitive questions, source references, checklist, destination, and manual submission method. The SHA-256 binds the complete proposal. Any change invalidates approval.

Preparation, editing, shortlisting, and approval never submit. `mark-submitted` only records a submission performed outside JamesOS and requires a separately confirmed transition from an exact approved proposal.

## CLI

Use `python scripts/job_search.py` with `ingest-email`, `ingest-manual`, `list`, `show`, `rank`, `shortlist`, `prepare`, `review`, `approve`, `mark-submitted`, or `report`. Mutating commands are dry-run unless `--confirm` is supplied. There is no submission command.

## Security boundaries

No credentials, cookies, provider tokens, scraping, browser automation, CAPTCHA handling, bulk applications, external requests, automatic attestations, fabricated qualifications, automatic sensitive answers, or retries are implemented. Paths and state transitions are validated; durable files use atomic replacement and private permissions.

Future provider integration requires separate authorization, provider terms review, approved read-only APIs/adapters, rate and audit controls, connector threat modeling, and dedicated tests. Live application submission remains outside Phase 1.
