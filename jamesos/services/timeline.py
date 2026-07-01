import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT

INDEX_ROOT = VAULT / "JamesOS" / "Index"
TIMELINE_ROOT = VAULT / "JamesOS" / "Timeline"


def build_timeline() -> str:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    TIMELINE_ROOT.mkdir(parents=True, exist_ok=True)

    entries = []

    scan_roots = [
        VAULT / "Daily",
        VAULT / "Work",
        VAULT / "GCU",
        VAULT / "UnityStitches",
        VAULT / "Personal",
    ]

    for root in scan_roots:
        if not root.exists():
            continue

        for path in root.rglob("*.md"):
            rel = path.relative_to(VAULT).as_posix()
            modified = datetime.fromtimestamp(path.stat().st_mtime)

            entries.append({
                "date": modified.strftime("%Y-%m-%d"),
                "datetime": modified.strftime("%Y-%m-%d %H:%M"),
                "file": rel,
                "title": path.stem,
            })

    entries = sorted(entries, key=lambda x: x["datetime"], reverse=True)

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "entries": entries,
    }

    (INDEX_ROOT / "timeline.json").write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    by_month = defaultdict(list)
    for entry in entries:
        dt = datetime.strptime(entry["date"], "%Y-%m-%d")
        key = (dt.year, dt.strftime("%B"))
        by_month[key].append(entry)

    for (year, month), month_entries in by_month.items():
        year_dir = TIMELINE_ROOT / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# {month} {year}",
            "",
            f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        current_date = None
        for entry in month_entries:
            if entry["date"] != current_date:
                current_date = entry["date"]
                lines.extend(["", f"## {current_date}"])

            link = Path(entry["file"]).with_suffix("").as_posix()
            lines.append(f"- {entry['datetime']} - [[{link}]]")

        (year_dir / f"{month}.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    return f"Built timeline with {len(entries)} entries"
