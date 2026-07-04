from __future__ import annotations

from pathlib import Path

from jamesos.config import VAULT

PROFILE_PATH = VAULT / "JamesOS" / "People" / "James.md"

DEFAULT_PROFILE = """# James Allendoerfer

Canonical person: James Allendoerfer
Aliases: James, Jim, @thedorfer
Role in JamesOS: owner, primary user, person being assisted
Email: thedorfer@gmail.com

## Stable context

- James is the person Jade is speaking to.
- When imported history mentions James Allendoerfer, James, Jim, or @thedorfer in a personal context, treat that as the user unless the source clearly says otherwise.
- Do not describe James as an unrelated third party.
- Say "you" and "your" when referring to James's work, history, files, preferences, or projects.

## Known work and projects

- James works in software/integration development.
- Major current project family: JamesOS / Jade.
- Work context often includes CGI, WGL/Washington Gas, Oracle, PL/SQL, SFM, R2QA, SBX, Paving, FERC, CPMP, and people such as Malcolm, Kevin, Tom, Ian, and Luke.
- Teaching context includes GCU courses and student support.

## Response behavior

- Ground answers in JamesOS data when possible.
- Prefer practical, direct answers.
- Avoid raw paths, JSON, or implementation details unless James asks.
"""


def ensure_identity_profile() -> Path:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not PROFILE_PATH.exists():
        PROFILE_PATH.write_text(DEFAULT_PROFILE, encoding="utf-8")
    return PROFILE_PATH


def identity_context() -> str:
    path = ensure_identity_profile()
    return path.read_text(encoding="utf-8", errors="ignore")[:4000]
