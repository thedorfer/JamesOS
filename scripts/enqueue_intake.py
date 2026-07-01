import sys

from jamesos.core.queue import enqueue_job

if len(sys.argv) < 2:
    print("Usage: enqueue_intake.py <title> [source] [source_detail]")
    sys.exit(1)

title = sys.argv[1]
source = sys.argv[2] if len(sys.argv) > 2 else "manual"
source_detail = sys.argv[3] if len(sys.argv) > 3 else ""
content = sys.stdin.read()

print(enqueue_job("intake", {
    "title": title,
    "content": content,
    "source": source,
    "source_detail": source_detail,
}))
