import sys
from jamesos.services.memory_engine import write_memory_report

if len(sys.argv) < 2:
    print("Usage: memory_report.py <entity>")
    sys.exit(1)

print(write_memory_report(" ".join(sys.argv[1:])))
