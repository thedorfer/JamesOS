import sys
from jamesos.services.context_engine import build_context_report

if len(sys.argv) < 2:
    print("Usage: context_report.py <query> [--ai]")
    sys.exit(1)

use_ai = "--ai" in sys.argv
query = " ".join(arg for arg in sys.argv[1:] if arg != "--ai")
print(build_context_report(query, use_ai=use_ai))
