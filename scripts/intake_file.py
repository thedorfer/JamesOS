import sys
from pathlib import Path

from jamesos.services.intake import intake_item

if len(sys.argv) < 2:
    print("Usage: intake_file.py <file_path> [title]")
    sys.exit(1)

file_path = Path(sys.argv[1]).expanduser().resolve()
title = sys.argv[2] if len(sys.argv) > 2 else file_path.stem

if not file_path.exists():
    print(f"File not found: {file_path}")
    sys.exit(1)

try:
    content = file_path.read_text(encoding="utf-8")
except UnicodeDecodeError:
    content = f"File captured for later review: {file_path}"

print(intake_item(title, content, "file", str(file_path)))
