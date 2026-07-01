import subprocess
import sys

from jamesos.services.intake import intake_item

if len(sys.argv) < 2:
    print("Usage: intake_clipboard.py <title> [source_detail]")
    sys.exit(1)

title = sys.argv[1]
source_detail = sys.argv[2] if len(sys.argv) > 2 else "clipboard"

try:
    content = subprocess.check_output(["xclip", "-selection", "clipboard", "-o"], text=True)
except Exception:
    try:
        content = subprocess.check_output(["xsel", "--clipboard", "--output"], text=True)
    except Exception as exc:
        print(f"Could not read clipboard. Install xclip: sudo apt install xclip\n{exc}")
        sys.exit(1)

print(intake_item(title, content, "clipboard", source_detail))
