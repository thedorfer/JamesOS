import sys
from jamesos.services.context_builder import write_context_report

if len(sys.argv) < 2:
    print("Usage: write_context_report.py <entity>")
    sys.exit(1)

print(write_context_report(" ".join(sys.argv[1:])))
