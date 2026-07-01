import sys
from jamesos.services.relationship_engine import write_relationship_report

if len(sys.argv) < 2:
    print("Usage: write_relationship_report.py <entity>")
    sys.exit(1)

print(write_relationship_report(sys.argv[1]))
