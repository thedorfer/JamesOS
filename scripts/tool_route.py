import sys
from jamesos.services.tool_router import route_tool

if len(sys.argv) < 2:
    print("Usage: tool_route.py <question>")
    sys.exit(1)

print(route_tool(" ".join(sys.argv[1:])))
