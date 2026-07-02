import sys
from jamesos.services.intelligence import smart_search

if len(sys.argv) < 2:
    print("Usage: smart_search.py <query>")
    sys.exit(1)

print(smart_search(" ".join(sys.argv[1:])))
