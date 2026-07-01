import sys
from jamesos.services.search_service import search_notes_index

if len(sys.argv) < 2:
    print("Usage: search_notes.py <query>")
    sys.exit(1)

print(search_notes_index(" ".join(sys.argv[1:])))
