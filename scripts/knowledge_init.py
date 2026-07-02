from jamesos.services.knowledge_engine import build_all_knowledge


def main() -> None:
    result = build_all_knowledge()
    print(result)


if __name__ == "__main__":
    main()
