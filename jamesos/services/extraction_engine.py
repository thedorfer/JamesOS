import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT

EXTRACTIONS_FILE = VAULT / "JamesOS" / "Database" / "extractions.json"
GRAPH_FILE = VAULT / "JamesOS" / "Database" / "unified_graph.json"

CONCEPTS = {
    "Travel": ["flight", "airline", "united", "jetblue", "expedia", "hotel", "reservation", "booking", "airport", "trip", "travel"],
    "GCU": ["gcu", "grand canyon", "student", "grade", "grading", "rubric", "halo", "class", "course", "discussion"],
    "Work": ["ticket", "bug", "deploy", "migration", "schema", "sql", "oracle", "wgl", "sfm2", "sbx"],
    "Family": ["birthday", "wife", "daughter", "dad", "mom", "kids", "school"],
    "Finance": ["receipt", "order", "payment", "invoice", "bank", "treasury", "account"],
}

TICKET_RE = re.compile(r"\b\d{5}\b")
EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _md_files() -> list[Path]:
    ignore = [".obsidian", ".trash", "JamesOS/Database"]
    files = []
    for path in VAULT.rglob("*.md"):
        rel = path.relative_to(VAULT).as_posix()
        if any(part in rel for part in ignore):
            continue
        files.append(path)
    return files


def extract_entities() -> str:
    EXTRACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "files": {},
    }

    for path in _md_files():
        rel = path.relative_to(VAULT).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        lower = text.lower()

        concepts = []
        for concept, terms in CONCEPTS.items():
            if any(term in lower for term in terms):
                concepts.append(concept)

        people = sorted(set(re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\b", text)))[:50]

        output["files"][rel] = {
            "title": path.stem,
            "concepts": sorted(concepts),
            "tickets": sorted(set(TICKET_RE.findall(text))),
            "emails": sorted(set(EMAIL_RE.findall(text))),
            "phones": sorted(set(PHONE_RE.findall(text))),
            "possible_people": people,
            "preview": _clean(text[:500]),
        }

    EXTRACTIONS_FILE.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return f"Extracted entities from {len(output['files'])} files"


def build_unified_graph() -> str:
    if not EXTRACTIONS_FILE.exists():
        extract_entities()

    data = json.loads(EXTRACTIONS_FILE.read_text(encoding="utf-8"))
    graph = defaultdict(lambda: {"type": "", "files": set(), "links": defaultdict(set)})

    for file, info in data.get("files", {}).items():
        file_node = file
        graph[file_node]["type"] = "file"
        graph[file_node]["files"].add(file)

        for concept in info.get("concepts", []):
            graph[concept]["type"] = "concept"
            graph[concept]["files"].add(file)
            graph[concept]["links"]["files"].add(file_node)
            graph[file_node]["links"]["concepts"].add(concept)

        for ticket in info.get("tickets", []):
            graph[ticket]["type"] = "ticket"
            graph[ticket]["files"].add(file)
            graph[ticket]["links"]["files"].add(file_node)
            graph[file_node]["links"]["tickets"].add(ticket)

        for email in info.get("emails", []):
            graph[email]["type"] = "email"
            graph[email]["files"].add(file)
            graph[email]["links"]["files"].add(file_node)
            graph[file_node]["links"]["emails"].add(email)

    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "nodes": {
            k: {
                "type": v["type"],
                "files": sorted(v["files"]),
                "links": {lk: sorted(lv) for lk, lv in v["links"].items()},
            }
            for k, v in graph.items()
        },
    }

    GRAPH_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return f"Built unified graph with {len(out['nodes'])} nodes"
