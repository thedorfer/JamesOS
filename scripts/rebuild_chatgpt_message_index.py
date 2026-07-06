import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jamesos.services.chatgpt_search_v2 import rebuild_message_index


if __name__ == "__main__":
    result = rebuild_message_index()
    print(f"scanned conversations: {result.get('scanned', 0)}")
    print(f"parsed messages: {result.get('parsed', 0)}")
    print(f"indexed messages: {result.get('indexed', 0)}")
