from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


JOB_STATUSES = {"discovered","screened_out","shortlisted","preparing","awaiting_review","approved","submitted","rejected","interview","offer","archived"}
APPROVAL_MODES = {"single_final", "staged"}


def now() -> str:
    return datetime.now().astimezone().isoformat()


@dataclass
class NormalizedJob:
    job_id: str; source: str; source_job_id: str | None = None; canonical_url: str | None = None
    title: str | None = None; company: str | None = None; location: str | None = None; work_setting: str | None = None
    salary_min: int | None = None; salary_max: int | None = None; salary_currency: str | None = None
    employment_type: str | None = None; description: str | None = None; requirements: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list); date_found: str = field(default_factory=now); date_posted: str | None = None
    source_evidence: dict[str, Any] = field(default_factory=dict); content_sha256: str = ""; duplicate_group_id: str | None = None
    status: str = "discovered"; created_at: str = field(default_factory=now); updated_at: str = field(default_factory=now)
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, value): return cls(**value)


@dataclass
class CareerProfile:
    profile_id: str = "career_example"; target_job_titles: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list); work_settings: list[str] = field(default_factory=list)
    minimum_compensation: int | None = None; employment_types: list[str] = field(default_factory=list)
    preferred_industries: list[str] = field(default_factory=list); required_technologies: list[str] = field(default_factory=list)
    preferred_technologies: list[str] = field(default_factory=list); excluded_employers: list[str] = field(default_factory=list)
    excluded_staffing_arrangements: list[str] = field(default_factory=list); sponsorship_requirements: str | None = None
    work_authorization_facts: list[str] = field(default_factory=list); clearance_restrictions: list[str] = field(default_factory=list)
    relocation_preference: str | None = None; travel_tolerance: str | None = None; resume_file_references: list[str] = field(default_factory=list)
    reusable_answers: dict[str, str] = field(default_factory=dict); maximum_applications_per_day: int = 1; approval_mode: str = "single_final"
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, value): return cls(**value)


@dataclass
class ApplicationProposal:
    application_id: str; job_id: str; status: str; proposal: dict[str, Any]; proposal_sha256: str
    approval: dict[str, Any] | None = None; transitions: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=now); updated_at: str = field(default_factory=now)
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, value): return cls(**value)


def validate_profile(profile: CareerProfile) -> CareerProfile:
    if profile.approval_mode not in APPROVAL_MODES: raise ValueError("unsupported career approval mode")
    if not isinstance(profile.maximum_applications_per_day, int) or not 1 <= profile.maximum_applications_per_day <= 100:
        raise ValueError("maximum applications per day must be between 1 and 100")
    for name in ("target_job_titles","preferred_locations","work_settings","employment_types","required_technologies","preferred_technologies",
                 "excluded_employers","excluded_staffing_arrangements","work_authorization_facts","resume_file_references"):
        if not isinstance(getattr(profile, name), list): raise ValueError(f"{name} must be a list")
    forbidden=("password","token","cookie","session","secret")
    if any(term in key.casefold() for key in profile.reusable_answers for term in forbidden): raise ValueError("career profile contains a forbidden secret field")
    return profile
