import sys
from jamesos.services.memory_service import remember

if len(sys.argv) < 2:
    print("Usage: remember.py <memory text>")
    sys.exit(1)

print(remember(" ".join(sys.argv[1:])))
