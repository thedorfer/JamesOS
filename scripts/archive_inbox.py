import sys
from jamesos.services.inbox_actions import archive_inbox_item

if len(sys.argv) < 2:
    print("Usage: archive_inbox.py <filename or partial title>")
    sys.exit(1)

print(archive_inbox_item(" ".join(sys.argv[1:])))
