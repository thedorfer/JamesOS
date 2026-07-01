import sys
from jamesos.tools.inbox import capture_inbox

if len(sys.argv) < 2:
    print("Usage: capture_inbox.py <title> [source]")
    sys.exit(1)

title = sys.argv[1]
source = sys.argv[2] if len(sys.argv) > 2 else "manual"
content = sys.stdin.read()

print(capture_inbox(title, content, source))
