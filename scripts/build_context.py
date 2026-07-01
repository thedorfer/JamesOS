import sys
from jamesos.services.context_builder import build_context

if len(sys.argv) < 2:
    print("Usage: build_context.py <entity>")
    sys.exit(1)

print(build_context(" ".join(sys.argv[1:])))
