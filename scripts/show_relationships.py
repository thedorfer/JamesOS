import sys
from jamesos.services.relationship_engine import get_entity_relationships

if len(sys.argv) < 2:
    print("Usage: show_relationships.py <entity>")
    sys.exit(1)

print(get_entity_relationships(sys.argv[1]))
