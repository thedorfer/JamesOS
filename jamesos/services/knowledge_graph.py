import json
import re
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT

GRAPH_DIR = VAULT / "JamesOS" / "Brain"
GRAPH_FILE = GRAPH_DIR / "knowledge_graph.json"
GRAPH_REPORT = VAULT / "JamesOS" / "Reports" / "Knowledge Graph.md"

ROOTS = [
    VAULT / "Work",
    VAULT / "JamesOS" / "People",
    VAULT / "JamesOS" / "Knowledge",
    VAULT / "JamesOS" / "Memory",
    VAULT / "Archive" / "Inbox" / "Gmail",
    VAULT / "Archive" / "Inbox" / "GCU",
    VAULT / "Archive" / "Inbox" / "Calendar",
]

KNOWN_PEOPLE = [
    "James", "Jade", "Kevin", "Malcolm", "Tom", "Ian", "Elias",
    "Julia", "CJ", "Jidapa", "Kim Keller"
]

KNOWN_PROJECTS = [
    "Paving", "FERC", "GCU", "JamesOS", "UOM", "SuperProject",
    "ERP", "CPMP", "Capital Work Order"
]

KNOWN_ENVS = ["SFM2", "SBX", "R2QA", "DEV", "QA", "PROD"]


def _add_node(nodes, name, kind):
    key = f"{kind}:{name}"
    nodes.setdefault(key, {"id": key, "name": name, "type": kind, "mentions": 0})
    nodes[key]["mentions"] += 1
    return key


def _add_edge(edges, source, target, relation, evidence):
    key = f"{source}|{relation}|{target}|{evidence}"
    edges[key] = {
        "source": source,
        "target": target,
        "relation": relation,
        "evidence": evidence,
    }


def _find_people(text):
    return [p for p in KNOWN_PEOPLE if re.search(rf"\\b{re.escape(p)}\\b", text, re.I)]


def _find_projects(text):
    return [p for p in KNOWN_PROJECTS if re.search(rf"\\b{re.escape(p)}\\b", text, re.I)]


def _find_envs(text):
    return [e for e in KNOWN_ENVS if re.search(rf"\\b{re.escape(e)}\\b", text, re.I)]


def _find_tickets(text):
    return sorted(set(re.findall(r"\\b\\d{5}\\b", text)))


def build_knowledge_graph() -> str:
    nodes = {}
    edges = {}

    for root in ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel = path.relative_to(VAULT).as_posix()
            file_node = _add_node(nodes, rel, "file")

            people = _find_people(text)
            projects = _find_projects(text)
            envs = _find_envs(text)
            tickets = _find_tickets(text)

            person_nodes = [_add_node(nodes, p, "person") for p in people]
            project_nodes = [_add_node(nodes, p, "project") for p in projects]
            env_nodes = [_add_node(nodes, e, "environment") for e in envs]
            ticket_nodes = [_add_node(nodes, t, "ticket") for t in tickets]

            for n in person_nodes + project_nodes + env_nodes + ticket_nodes:
                _add_edge(edges, n, file_node, "mentioned_in", rel)

            for person in person_nodes:
                for project in project_nodes:
                    _add_edge(edges, person, project, "related_to_project", rel)
                for ticket in ticket_nodes:
                    _add_edge(edges, person, ticket, "related_to_ticket", rel)

            for project in project_nodes:
                for ticket in ticket_nodes:
                    _add_edge(edges, project, ticket, "has_ticket", rel)
                for env in env_nodes:
                    _add_edge(edges, project, env, "seen_in_environment", rel)

            for ticket in ticket_nodes:
                for env in env_nodes:
                    _add_edge(edges, ticket, env, "seen_in_environment", rel)

    graph = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }

    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_FILE.write_text(json.dumps(graph, indent=2), encoding="utf-8")

    top_people = sorted(
        [n for n in nodes.values() if n["type"] == "person"],
        key=lambda x: x["mentions"],
        reverse=True,
    )[:20]

    top_tickets = sorted(
        [n for n in nodes.values() if n["type"] == "ticket"],
        key=lambda x: x["mentions"],
        reverse=True,
    )[:20]

    lines = [
        "# Knowledge Graph",
        "",
        f"Updated: {graph['generated_at']}",
        "",
        f"- Nodes: {len(nodes)}",
        f"- Edges: {len(edges)}",
        "",
        "## Top People",
    ]

    lines.extend([f"- {n['name']} — {n['mentions']} mentions" for n in top_people] or ["- None"])

    lines.extend(["", "## Top Tickets"])
    lines.extend([f"- {n['name']} — {n['mentions']} mentions" for n in top_tickets] or ["- None"])

    GRAPH_REPORT.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_REPORT.write_text("\\n".join(lines) + "\\n", encoding="utf-8")

    return f"Built knowledge graph with {len(nodes)} nodes and {len(edges)} edges"


def graph_lookup(query: str, limit: int = 20) -> dict:
    if not GRAPH_FILE.exists():
        build_knowledge_graph()

    graph = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))
    q = query.lower()

    matched_nodes = [
        n for n in graph["nodes"]
        if q in n["name"].lower()
    ][:limit]

    matched_ids = {n["id"] for n in matched_nodes}

    related_edges = [
        e for e in graph["edges"]
        if e["source"] in matched_ids or e["target"] in matched_ids
    ][:limit * 3]

    return {
        "query": query,
        "nodes": matched_nodes,
        "edges": related_edges,
    }
