import sys
from jamesos.services.intake import intake_item

if len(sys.argv) < 2:
    print("Usage: intake.py <title> [source] [source_detail]")
    sys.exit(1)

title = sys.argv[1]
source = sys.argv[2] if len(sys.argv) > 2 else "manual"
source_detail = sys.argv[3] if len(sys.argv) > 3 else ""
content = sys.stdin.read()

print(intake_item(title, content, source, source_detail))
