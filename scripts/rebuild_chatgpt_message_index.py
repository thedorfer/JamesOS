from pathlib import Path

from jamesos.services.chatgpt_search_v2 import rebuild_message_index


if __name__ == "__main__":
    result = rebuild_message_index()
    print(result)
