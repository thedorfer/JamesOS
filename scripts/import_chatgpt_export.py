import argparse
from pathlib import Path

from jamesos.services.chatgpt_importer import import_chatgpt_export


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an official ChatGPT export into JamesOS.")
    parser.add_argument("zip_path", help="Path to the ChatGPT export zip file")
    parser.add_argument("--limit", type=int, default=None, help="Optional max conversations for testing")
    args = parser.parse_args()

    result = import_chatgpt_export(Path(args.zip_path), limit=args.limit)
    print(result)


if __name__ == "__main__":
    main()
